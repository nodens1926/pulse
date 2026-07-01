from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from datetime import datetime
import logging

from database import get_db, engine
from models import Site, Page
from schemas import SiteCreate, SiteResponse, SearchRequest, SearchResponse, SearchResult, StatusResponse
from tasks import index_site, recalculate_all
from ml import search, find_similar_pages
from config import DATABASE_URL

# СОЗДАЁМ ТАБЛИЦЫ ПРИ ЗАПУСКЕ
from database import Base
Base.metadata.create_all(bind=engine)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Pulse Search API", version="1.0")

# CORS для фронтенда
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost", "http://localhost:80", "http://127.0.0.1"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/api/sites", response_model=SiteResponse)
def add_site(site: SiteCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Добавляет сайт в очередь на индексацию"""
    # Проверяем, существует ли сайт
    existing = db.query(Site).filter(Site.url == str(site.url)).first()
    if existing:
        raise HTTPException(status_code=400, detail="Site already exists")
    
    # Создаем запись
    db_site = Site(
        url=str(site.url),
        name=site.name or str(site.url),
        status="pending"
    )
    db.add(db_site)
    db.commit()
    db.refresh(db_site)
    
    # Запускаем индексацию в фоне
    index_site.delay(db_site.id)
    
    return db_site

@app.get("/api/search", response_model=SearchResponse)
def search_pages(q: str, limit: int = 10, db: Session = Depends(get_db)):
    """Поиск по запросу"""
    if not q.strip():
        return SearchResponse(results=[], total=0)
    
    # Поиск через ML
    page_ids = search(q.strip(), db, limit)
    
    results = []
    for page_id in page_ids:
        page = db.query(Page).filter(Page.id == page_id).first()
        if page:
            # ВЫРЕЗАЕМ СНИППЕТ (первые 200 символов текста)
            snippet = None
            if page.content:
                # Очищаем от лишних пробелов и берём первые 200 символов
                clean_text = ' '.join(page.content.split())
                snippet = clean_text[:200] + ("..." if len(clean_text) > 200 else "")
            
            results.append(SearchResult(
                page_id=page.id,
                url=page.url,
                title=page.title,
                score=page.relevantnost or 0.0,
                snippet=snippet
            ))
    
    return SearchResponse(results=results, total=len(results))

@app.get("/api/status/{site_id}", response_model=StatusResponse)
def get_status(site_id: int, db: Session = Depends(get_db)):
    """Проверяет статус индексации сайта"""
    site = db.query(Site).filter(Site.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    
    pages_count = db.query(Page).filter(Page.site_id == site_id).count()
    
    return StatusResponse(
        site_id=site.id,
        url=site.url,
        status=site.status,
        pages_indexed=pages_count
    )

@app.get("/api/status")
def get_all_status(db: Session = Depends(get_db)):
    """Получает статус всех сайтов"""
    sites = db.query(Site).all()
    result = []
    for site in sites:
        pages_count = db.query(Page).filter(Page.site_id == site.id).count()
        result.append({
            "site_id": site.id,
            "url": site.url,
            "status": site.status,
            "pages_indexed": pages_count
        })
    return result

@app.post("/api/reindex")
def reindex_all(background_tasks: BackgroundTasks):
    """Переиндексация всех данных"""
    recalculate_all.delay()
    return {"status": "reindexing started"}

@app.get("/")
def root():
    return {"message": "Pulse Search API", "version": "1.0"}


# ============================================================
# НОВЫЙ ЭНДПОИНТ ДЛЯ ПОХОЖИХ СТРАНИЦ
# ============================================================

@app.get("/api/similar/{page_id}")
def get_similar_pages(page_id: int, limit: int = 10, db: Session = Depends(get_db)):
    """
    Возвращает похожие страницы для указанной страницы.
    
    Args:
        page_id: ID страницы
        limit: количество похожих страниц (по умолчанию 10)
    
    Returns:
        {
            "page_id": int,
            "similar": [
                {
                    "id": int,
                    "url": str,
                    "title": str,
                    "score": float
                }
            ]
        }
    """
    # Проверяем, существует ли страница
    page = db.query(Page).filter(Page.id == page_id).first()
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    
    # Проверяем, есть ли у страницы эмбеддинг
    if not page.embedding:
        raise HTTPException(
            status_code=400, 
            detail="Page has no embedding. Please reindex the site."
        )
    
    try:
        # Ищем похожие страницы
        # use_tfidf_stage=True — используем TF-IDF + SBERT для скорости
        similar = find_similar_pages(
            db_url=DATABASE_URL,
            ranked_page_ids=[page_id],
            top_n_per_page=limit,
            use_tfidf_stage=True
        )
        
        similar_ids = similar.get(page_id, [])
        
        # Загружаем данные страниц
        results = []
        for pid in similar_ids:
            p = db.query(Page).filter(Page.id == pid).first()
            if p:
                results.append({
                    "id": p.id,
                    "url": p.url,
                    "title": p.title,
                    "score": p.relevantnost or 0.0
                })
        
        return {
            "page_id": page_id,
            "similar": results,
            "total": len(results)
        }
        
    except ValueError as e:
        # Если глобальные параметры не инициализированы
        logger.error(f"Ошибка при поиске похожих страниц: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"ML models not initialized: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Ошибка при поиске похожих страниц: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error finding similar pages: {str(e)}"
        )


@app.get("/api/similar/batch")
def get_similar_pages_batch(page_ids: str, limit: int = 5, db: Session = Depends(get_db)):
    """
    Возвращает похожие страницы для нескольких страниц одновременно.
    
    Args:
        page_ids: список ID через запятую (например: "1,2,3")
        limit: количество похожих страниц для каждой (по умолчанию 5)
    
    Returns:
        {
            "results": {
                "1": [similar_pages],
                "2": [similar_pages]
            }
        }
    """
    try:
        # Парсим список ID
        ids = [int(pid.strip()) for pid in page_ids.split(',') if pid.strip()]
        if not ids:
            raise HTTPException(status_code=400, detail="No valid page IDs provided")
        
        # Проверяем, что все страницы существуют
        pages = db.query(Page).filter(Page.id.in_(ids)).all()
        existing_ids = [p.id for p in pages]
        
        if not existing_ids:
            raise HTTPException(status_code=404, detail="No valid pages found")
        
        # Ищем похожие страницы
        similar = find_similar_pages(
            db_url=DATABASE_URL,
            ranked_page_ids=existing_ids,
            top_n_per_page=limit,
            use_tfidf_stage=True
        )
        
        # Формируем ответ
        result = {}
        for pid in existing_ids:
            similar_ids = similar.get(pid, [])
            pages_data = []
            for sid in similar_ids:
                p = db.query(Page).filter(Page.id == sid).first()
                if p:
                    pages_data.append({
                        "id": p.id,
                        "url": p.url,
                        "title": p.title,
                        "score": p.relevantnost or 0.0
                    })
            result[str(pid)] = pages_data
        
        return {"results": result}
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid page IDs: {str(e)}")
    except Exception as e:
        logger.error(f"Ошибка в batch поиске похожих страниц: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/reload")
def reload_globals(db: Session = Depends(get_db)):
    """Перезагружает глобальные переменные из БД"""
    from ml import calculate_tfidf
    calculate_tfidf(db)
    logger.info("Глобальные переменные перезагружены")
    return {"status": "success"}
