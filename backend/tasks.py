from celery import Celery
from sqlalchemy.orm import Session
import requests
from bs4 import BeautifulSoup
import logging

from config import REDIS_URL, DATABASE_URL
from database import SessionLocal
from models import Site, Page
from ml import process_content, build_inverted_index, calculate_tfidf, compute_embeddings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Celery приложение
celery_app = Celery('tasks', broker=REDIS_URL, backend=REDIS_URL)

@celery_app.task
def index_site(site_id):
    """Индексация сайта"""
    db = SessionLocal()
    
    try:
        site = db.query(Site).filter(Site.id == site_id).first()
        if not site:
            return {"error": "Site not found"}
        
        site.status = "processing"
        db.commit()
        
        # Скачиваем HTML
        try:
            response = requests.get(site.url, timeout=10)
            response.raise_for_status()
        except Exception as e:
            site.status = "error"
            db.commit()
            return {"error": str(e)}
        
        # Парсим HTML
        soup = BeautifulSoup(response.content, 'html.parser')
        title = soup.title.string if soup.title else site.url
        
        # Извлекаем текст
        for script in soup(["script", "style"]):
            script.decompose()
        text = ' '.join(soup.stripped_strings)
        
        if not text:
            site.status = "error"
            db.commit()
            return {"error": "No text content"}
        
        # Создаем страницу
        page = Page(
            site_id=site.id,
            url=site.url,
            title=title,
            content=text,
            token_text=process_content(text)
        )
        db.add(page)
        db.commit()
        
        # Строим инвертированный индекс
        entries = build_inverted_index(db, page.id, page.token_text)
        if entries:
            db.bulk_save_objects(entries)
        
        # Вычисляем эмбеддинг
        compute_embeddings(db, batch_size=1)
        
        # Пересчитываем TF-IDF
        calculate_tfidf(db)
        
        site.status = "indexed"
        db.commit()
        
        logger.info(f"Сайт {site.url} проиндексирован, страниц: 1")
        return {"status": "success", "page_id": page.id}
        
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
