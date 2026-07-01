from celery import Celery
from sqlalchemy.orm import Session
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin
import logging
import time  # <-- ДОБАВЛЯЕМ
from datetime import datetime

from config import REDIS_URL, DATABASE_URL
from database import SessionLocal
from models import Site, Page
from ml import process_content, build_inverted_index, calculate_tfidf, compute_embeddings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Celery приложение
celery_app = Celery('tasks', broker=REDIS_URL, backend=REDIS_URL)

# Максимальное количество страниц для индексации с одного сайта
MAX_PAGES_PER_SITE = 10

# Интервал автопереиндексации (в секундах)
# 24 часа = 86400 секунд
REINDEX_INTERVAL = 86400  # 24 часа
# Для теста можно поставить 60 секунд
# REINDEX_INTERVAL = 60


def get_domain(url):
    """Возвращает домен из URL"""
    parsed = urlparse(url)
    return parsed.netloc


def is_internal_link(base_url, link):
    """Проверяет, ведёт ли ссылка на тот же домен"""
    if not link:
        return False
    if link.startswith('#') or link.startswith('javascript:'):
        return False
    if link.startswith('mailto:') or link.startswith('tel:'):
        return False
    
    full_url = urljoin(base_url, link)
    parsed_link = urlparse(full_url)
    parsed_base = urlparse(base_url)
    
    return parsed_link.netloc == parsed_base.netloc


def extract_links(soup, base_url):
    """Извлекает все внутренние ссылки со страницы"""
    links = set()
    for a_tag in soup.find_all('a', href=True):
        href = a_tag['href']
        if is_internal_link(base_url, href):
            full_url = urljoin(base_url, href)
            # Убираем якоря и параметры для уникальности
            parsed = urlparse(full_url)
            clean_url = parsed._replace(fragment='').geturl()
            links.add(clean_url)
    return links


@celery_app.task
def index_page(url, site_id):
    """Индексация одной страницы"""
    db = SessionLocal()
    
    try:
        # Проверяем, не проиндексирована ли уже эта страница
        existing = db.query(Page).filter(Page.url == url, Page.site_id == site_id).first()
        if existing:
            logger.info(f"Страница уже проиндексирована: {url}")
            return {"status": "skipped", "url": url, "reason": "already indexed"}
        
        # Скачиваем HTML
        try:
            response = requests.get(url, timeout=10, headers={
                'User-Agent': 'Mozilla/5.0 (compatible; PulseBot/1.0)'
            })
            response.raise_for_status()
        except Exception as e:
            logger.error(f"Ошибка скачивания {url}: {e}")
            return {"error": str(e), "url": url}
        
        # Парсим HTML
        soup = BeautifulSoup(response.content, 'html.parser')
        title = soup.title.string if soup.title else url
        
        # Извлекаем текст
        for script in soup(["script", "style"]):
            script.decompose()
        text = ' '.join(soup.stripped_strings)
        
        if not text or len(text) < 50:
            logger.info(f"Слишком мало текста на {url}, пропускаем")
            return {"status": "skipped", "url": url, "reason": "no content"}
        
        # Создаём страницу
        page = Page(
            site_id=site_id,
            url=url,
            title=title[:500],  # ограничиваем длину
            content=text[:10000],  # ограничиваем длину текста
            token_text=process_content(text),
            crawled_at=datetime.now()
        )
        db.add(page)
        db.commit()
        
        # Строим инвертированный индекс
        entries = build_inverted_index(db, page.id, page.token_text)
        if entries:
            db.bulk_save_objects(entries)
            db.commit()
        
        logger.info(f"Страница проиндексирована: {url}")
        return {"status": "success", "page_id": page.id, "url": url}
        
    except Exception as e:
        logger.error(f"Ошибка индексации {url}: {e}")
        return {"error": str(e), "url": url}
    finally:
        db.close()


@celery_app.task
def index_site(site_id):
    """Индексация сайта (главная + до MAX_PAGES_PER_SITE страниц)"""
    db = SessionLocal()
    
    try:
        site = db.query(Site).filter(Site.id == site_id).first()
        if not site:
            return {"error": "Site not found"}
        
        site.status = "processing"
        db.commit()
        
        # Скачиваем главную страницу
        try:
            response = requests.get(site.url, timeout=10, headers={
                'User-Agent': 'Mozilla/5.0 (compatible; PulseBot/1.0)'
            })
            response.raise_for_status()
        except Exception as e:
            site.status = "error"
            db.commit()
            return {"error": str(e)}
        
        # Парсим главную страницу
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Индексируем главную страницу
        main_result = index_page.delay(site.url, site_id)
        
        # Извлекаем ссылки для дальнейшей индексации
        links = extract_links(soup, site.url)
        logger.info(f"Найдено {len(links)} внутренних ссылок на {site.url}")
        
        # Индексируем найденные страницы (ограничиваем количество)
        page_tasks = []
        for link in list(links)[:MAX_PAGES_PER_SITE - 1]:  # -1 потому что главная уже индексируется
            task = index_page.delay(link, site_id)
            page_tasks.append(task)
            logger.info(f"Поставлена в очередь: {link}")
        
        # Обновляем статус сайта
        pages_count = db.query(Page).filter(Page.site_id == site_id).count()
        
        # Пересчитываем TF-IDF после индексации всех страниц
        calculate_tfidf(db)
        compute_embeddings(db)
        
        site.status = "indexed"
        site.last_crawled = datetime.now()
        db.commit()
        
        logger.info(f"Сайт {site.url} проиндексирован, страниц: {pages_count}")
        return {"status": "success", "pages_indexed": pages_count}
        
    except Exception as e:
        logger.error(f"Ошибка индексации сайта {site_id}: {e}")
        if site:
            site.status = "error"
            db.commit()
        return {"error": str(e)}
    finally:
        db.close()


@celery_app.task
def recalculate_all():
    """Пересчет всех индексов"""
    db = SessionLocal()
    try:
        calculate_tfidf(db)
        compute_embeddings(db)
        return {"status": "success"}
    finally:
        db.close()


# ============================================================
# АВТОМАТИЧЕСКАЯ ПЕРЕИНДЕКСАЦИЯ (цикл внутри воркера)
# ============================================================

def start_auto_reindex():
    """
    Запускает бесконечный цикл автопереиндексации.
    Вызывается при старте воркера.
    """
    logger.info(f"Автопереиндексация запущена. Интервал: {REINDEX_INTERVAL} секунд (~{REINDEX_INTERVAL // 3600} часов)")
    
    while True:
        try:
            # Ждём указанный интервал
            time.sleep(REINDEX_INTERVAL)
            
            # Запускаем переиндексацию
            logger.info("Запуск автоматической переиндексации...")
            result = recalculate_all.delay()
            logger.info(f"Задача переиндексации поставлена в очередь (task_id: {result.id})")
            
        except Exception as e:
            logger.error(f"Ошибка в цикле автопереиндексации: {e}")
            # Ждём 60 секунд перед повторной попыткой
            time.sleep(60)


# Запускаем автопереиндексацию при старте воркера
# Это сработает, когда модуль будет импортирован
import threading
auto_reindex_thread = threading.Thread(target=start_auto_reindex, daemon=True)
auto_reindex_thread.start()
logger.info("Поток автопереиндексации запущен")
