from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware  # <-- ДОБАВИТЬ ЭТУ СТРОКУ
from sqlalchemy.orm import Session
from datetime import datetime
import logging

from database import get_db, engine
from models import Site, Page
from schemas import SiteCreate, SiteResponse, SearchRequest, SearchResponse, SearchResult, StatusResponse
from tasks import index_site, recalculate_all
from ml import search

# СОЗДАЁМ ТАБЛИЦЫ ПРИ ЗАПУСКЕ
from database import Base
Base.metadata.create_all(bind=engine)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Pulse Search API", version="1.0")

# ДОБАВИТЬ ЭТУ СЕКЦИЮ - CORS для фронтенда
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
