from celery import Celery
from sqlalchemy.orm import Session
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import logging
from collections import deque
import time

from config import REDIS_URL, DATABASE_URL
from database import SessionLocal
from models import Site, Page
from ml import process_content, build_inverted_index, calculate_tfidf, compute_embeddings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Celery приложение
celery_app = Celery('tasks', broker=REDIS_URL, backend=REDIS_URL)

def is_valid_url(url, base_domain):
    """Проверяет, является ли URL валидным и принадлежит ли он тому же домену"""
    try:
        parsed = urlparse(url)
        # Проверяем, что URL принадлежит тому же домену
        if parsed.netloc != base_domain:
            return False
        # Исключаем файлы и якоря
        if parsed.fragment:
            return False
        # Исключаем медиа-файлы
        excluded_extensions = ['.pdf', '.jpg', '.jpeg', '.png', '.gif', '.svg', '.mp4', '.mp3', '.zip', '.rar']
        if any(url.lower().endswith(ext) for ext in excluded_extensions):
            return False
        return True
    except:
        return False

def extract_links(soup, base_url, base_domain):
    """Извлекает все ссылки со страницы"""
    links = set()
    for a_tag in soup.find_all('a', href=True):
        href = a_tag['href']
        full_url = urljoin(base_url, href)
        if is_valid_url(full_url, base_domain):
            links.add(full_url)
    return links

def crawl_page(url, max_pages=10):
    """Сканирует страницу и возвращает контент и найденные ссылки"""
    try:
        response = requests.get(url, timeout=10, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Извлекаем заголовок
        title = soup.title.string if soup.title and soup.title.string else url
        
        # Извлекаем текст
        for script in soup(["script", "style", "nav", "footer", "header"]):
            script.decompose()
        text = ' '.join(soup.stripped_strings)
        
        if not text:
            return None, set()
        
        # Извлекаем ссылки
        parsed_url = urlparse(url)
        base_domain = parsed_url.netloc
        links = extract_links(soup, url, base_domain)
        
        return {
            'url': url,
            'title': title,
            'content': text
        }, links
        
    except Exception as e:
        logger.error(f"Ошибка при сканировании {url}: {e}")
        return None, set()

@celery_app.task
def index_site(site_id, max_pages=10):
    """Индексация сайта с обходом нескольких страниц"""
    db = SessionLocal()
    
    try:
        site = db.query(Site).filter(Site.id == site_id).first()
        if not site:
            return {"error": "Site not found"}
        
        site.status = "processing"
        db.commit()
        
        # Парсим домен
        parsed_url = urlparse(site.url)
        base_domain = parsed_url.netloc
        
        # Очередь для обхода страниц
        to_visit = deque([site.url])
        visited = set()
        pages_data = []
        page_count = 0
        
        while to_visit and page_count < max_pages:
            current_url = to_visit.popleft()
            
            if current_url in visited:
                continue
            
            logger.info(f"Сканирование страницы {page_count + 1}/{max_pages}: {current_url}")
            
            # Сканируем страницу
            page_info, links = crawl_page(current_url)
            
            if page_info:
                # Сохраняем страницу в БД
                page = Page(
                    site_id=site.id,
                    url=page_info['url'],
                    title=page_info['title'],
                    content=page_info['content'],
                    token_text=process_content(page_info['content'])
                )
                db.add(page)
                db.commit()
                db.refresh(page)
                
                # Строим инвертированный индекс
                entries = build_inverted_index(db, page.id, page.token_text)
                if entries:
                    db.bulk_save_objects(entries)
                    db.commit()
                
                pages_data.append(page)
                page_count += 1
                visited.add(current_url)
                
                # Добавляем новые ссылки в очередь
                for link in links:
                    if link not in visited and link not in to_visit:
                        to_visit.append(link)
            else:
                visited.add(current_url)
            
            # Небольшая задержка, чтобы не перегружать сервер
            time.sleep(0.5)
        
        if page_count == 0:
            site.status = "error"
            db.commit()
            return {"error": "No pages could be indexed"}
        
        # Вычисляем эмбеддинги для всех страниц
        logger.info(f"Вычисление эмбеддингов для {len(pages_data)} страниц...")
        compute_embeddings(db, batch_size=5)
        
        # Пересчитываем TF-IDF для всех страниц
        logger.info("Пересчет TF-IDF...")
        calculate_tfidf(db)
        
        site.status = "indexed"
        db.commit()
        
        logger.info(f"Сайт {site.url} проиндексирован, страниц: {page_count}")
        return {
            "status": "success", 
            "pages_indexed": page_count,
            "pages": [p.id for p in pages_data]
        }
        
    except Exception as e:
        logger.error(f"Ошибка индексации: {e}")
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