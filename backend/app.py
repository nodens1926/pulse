from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
import logging
from datetime import datetime

from config import (
    get_db,
    settings,
    check_connections,
    redis_client,
    get_model_info
)

from models import Site, Page
from tasks import (
    add_to_queue,
    index_site,
    get_queue_status,
    recalculate_all_etl,
    update_global_params,
    collect_stats,
    cleanup_old_data,
    recover_queue
)
from ml import search, get_search_stats, get_explanation
from indexer import initialize_global_search_params, get_global_stats
from crawler import check_site_health
from nlp_utils import get_nlp_info

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- СОЗДАНИЕ ПРИЛОЖЕНИЯ ---
app = FastAPI(
    title="Pulse Search API",
    description="Поисковая система с автоматической индексацией сайтов (ML + ETL)",
    version="3.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# --- CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 1. STARTUP / SHUTDOWN СОБЫТИЯ

@app.on_event("startup")
async def startup_event():
    """Инициализация при старте"""
    logger.info("🚀 Запуск Pulse Search API v3.0.0")

    connections = check_connections()
    logger.info(f"📊 Подключения: БД={connections['database']}, Redis={connections['redis']}")

    if not connections["database"]:
        logger.error("❌ База данных недоступна!")
        return

    logger.info("🔧 Инициализация глобальных параметров поиска...")
    db = next(get_db())
    try:
        result = initialize_global_search_params(db)
        if result.get("success"):
            logger.info(f"✅ Глобальные параметры поиска инициализированы: "
                        f"n_doc={result.get('n_doc', 0)}, "
                        f"vocab_size={result.get('vocabulary_size', 0)}")
        else:
            logger.error(f"❌ Ошибка инициализации: {result.get('error')}")
    except Exception as e:
        logger.error(f"❌ Ошибка при инициализации параметров поиска: {e}")
    finally:
        db.close()

    nlp_info = get_nlp_info()
    logger.info(f"📚 NLP инструменты: pymorphy3={nlp_info.get('pymorphy3_loaded')}, "
                f"spaCy={nlp_info.get('spacy_loaded')}")

    model_info = get_model_info()
    logger.info(f"🧠 SBERT модель: {model_info.get('model_name')}, "
                f"загружена={model_info.get('is_loaded')}")

    try:
        recover_result = recover_queue.delay()
        logger.info(f"🔄 Запущено восстановление очереди (task_id={recover_result.id})")
    except Exception as e:
        logger.error(f"❌ Ошибка при восстановлении очереди: {e}")

    logger.info("✅ Приложение успешно запущено!")


@app.on_event("shutdown")
async def shutdown_event():
    """Завершение работы"""
    logger.info("🛑 Завершение работы Pulse Search API")


# 2. HEALTH CHECK

@app.get("/health", tags=["System"])
def health_check():
    from config import GLOBAL_SEARCH_INITIALIZED

    connections = check_connections()
    queue_status = get_queue_status()
    global_stats = get_global_stats()
    search_stats = get_search_stats()
    nlp_info = get_nlp_info()
    model_info = get_model_info()

    is_healthy = (
            connections["database"] and
            connections["redis"] and
            GLOBAL_SEARCH_INITIALIZED
    )

    return {
        "status": "ok" if is_healthy else "degraded",
        # ...
        "initialized": GLOBAL_SEARCH_INITIALIZED
    }


# 3. SITES ENDPOINTS

@app.post("/api/sites", tags=["Sites"], response_model=Dict[str, Any])
def add_site(
        url: str = Query(..., description="URL сайта для индексации"),
        db: Session = Depends(get_db)
):

    if not url or not url.strip():
        raise HTTPException(status_code=400, detail="URL не может быть пустым")

    url = url.strip()
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url

    existing_site = db.query(Site).filter(Site.url == url).first()
    if existing_site:
        return {
            "id": existing_site.id,
            "url": existing_site.url,
            "status": existing_site.status,
            "message": f"Сайт уже добавлен (статус: {existing_site.status})"
        }

    site = Site(
        url=url,
        status="pending",
        date_added=datetime.utcnow()
    )
    db.add(site)
    db.commit()
    db.refresh(site)

    try:
        add_to_queue(url)
        index_site.delay(site.id)
        logger.info(f"✅ Сайт добавлен в очередь: {url} (ID: {site.id})")
        return {
            "id": site.id,
            "url": site.url,
            "status": "pending",
            "message": "Сайт добавлен в очередь на индексацию"
        }
    except Exception as e:
        site.status = "error"
        db.commit()
        logger.error(f"❌ Ошибка при добавлении в очередь: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка при добавлении в очередь: {str(e)}")


@app.get("/api/sites", tags=["Sites"], response_model=Dict[str, Any])
def list_sites(
        limit: int = Query(20, ge=1, le=100, description="Количество записей"),
        offset: int = Query(0, ge=0, description="Смещение"),
        status_filter: Optional[str] = Query(None, description="Фильтр по статусу"),
        db: Session = Depends(get_db)
):
    query = db.query(Site)
    if status_filter:
        query = query.filter(Site.status == status_filter)

    total = query.count()
    sites = query.order_by(Site.date_added.desc()).offset(offset).limit(limit).all()

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "sites": [
            {
                "id": site.id,
                "url": site.url,
                "status": site.status,
                "date_added": site.date_added.isoformat() if site.date_added else None,
                "last_crawled": site.last_crawled.isoformat() if site.last_crawled else None,
            }
            for site in sites
        ]
    }


@app.get("/api/sites/{site_id}", tags=["Sites"], response_model=Dict[str, Any])
def get_site_status(site_id: int, db: Session = Depends(get_db)):
    site = db.query(Site).filter(Site.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Сайт не найден")

    pages_count = db.query(Page).filter(Page.site_id == site_id).count()

    return {
        "id": site.id,
        "url": site.url,
        "status": site.status,
        "pages_indexed": pages_count,
        "date_added": site.date_added.isoformat() if site.date_added else None,
        "last_crawled": site.last_crawled.isoformat() if site.last_crawled else None,
        "message": _get_status_message(site.status)
    }


def _get_status_message(status: str) -> str:
    messages = {
        "pending": "Сайт ожидает индексации",
        "processing": "Идёт индексация сайта",
        "indexed": "Сайт успешно проиндексирован",
        "error": "Произошла ошибка при индексации"
    }
    return messages.get(status, "Неизвестный статус")


@app.delete("/api/sites/{site_id}", tags=["Sites"])
def delete_site(site_id: int, db: Session = Depends(get_db)):
    site = db.query(Site).filter(Site.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Сайт не найден")

    db.delete(site)
    db.commit()
    logger.info(f"🗑️ Удалён сайт: {site.url} (ID: {site_id})")
    return {"message": f"Сайт {site.url} удалён", "id": site_id}


@app.post("/api/sites/{site_id}/reindex", tags=["Sites"])
def reindex_site(site_id: int, db: Session = Depends(get_db)):
    site = db.query(Site).filter(Site.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Сайт не найден")

    db.query(Page).filter(Page.site_id == site_id).delete()
    site.status = "pending"
    site.last_crawled = None
    db.commit()

    # Добавляем в очередь
    add_to_queue(site.url)
    index_site.delay(site.id)

    logger.info(f"🔄 Переиндексация сайта: {site.url} (ID: {site_id})")
    return {
        "message": f"Сайт {site.url} поставлен в очередь на переиндексацию",
        "id": site_id,
        "status": "pending"
    }


# 4. SEARCH ENDPOINTS

@app.get("/api/search", tags=["Search"], response_model=Dict[str, Any])
def search_endpoint(
        q: str = Query(..., description="Поисковый запрос", min_length=1),
        top_k: int = Query(50, ge=1, le=200, description="Количество кандидатов из TF-IDF"),
        final_k: int = Query(10, ge=1, le=50, description="Количество финальных результатов"),
        db: Session = Depends(get_db)
):

    if not q or len(q.strip()) < 2:
        return {
            "query": q,
            "total": 0,
            "results": [],
            "message": "Запрос должен содержать минимум 2 символа"
        }

    from config import GLOBAL_SEARCH_INITIALIZED
    if not GLOBAL_SEARCH_INITIALIZED:
        return {
            "query": q,
            "total": 0,
            "results": [],
            "message": "Поисковая система еще не инициализирована. Попробуйте позже."
        }

    try:
        start_time = datetime.utcnow()

        results = search(
            db=db,
            query=q,
            top_k=top_k,
            final_k=final_k
        )

        elapsed = (datetime.utcnow() - start_time).total_seconds()

        return {
            "query": q,
            "total": len(results),
            "results": results,
            "top_k": top_k,
            "final_k": final_k,
            "search_time": round(elapsed, 3),
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"❌ Ошибка при поиске: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Ошибка при поиске: {str(e)}")


@app.get("/api/search/explain/{page_id}", tags=["Search"])
def explain_result(
        page_id: int,
        q: str = Query(..., description="Поисковый запрос", min_length=1),
        db: Session = Depends(get_db)
):

    if not q or len(q.strip()) < 2:
        raise HTTPException(status_code=400, detail="Запрос должен содержать минимум 2 символа")

    try:
        explanation = get_explanation(db, page_id, q)
        if "error" in explanation:
            raise HTTPException(status_code=404, detail=explanation["error"])
        return explanation
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Ошибка при получении объяснения: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# 5. PAGES ENDPOINTS

@app.get("/api/pages/{page_id}", tags=["Pages"], response_model=Dict[str, Any])
def get_page_info(page_id: int, db: Session = Depends(get_db)):

    page = db.query(Page).filter(Page.id == page_id).first()
    if not page:
        raise HTTPException(status_code=404, detail="Страница не найдена")

    token_count = len(page.token_text.split()) if page.token_text else 0
    tfidf_size = len(page.tf_idf) if page.tf_idf else 0

    return {
        "id": page.id,
        "site_id": page.site_id,
        "url": page.url,
        "title": page.title,
        "content_preview": page.content[:500] + "..." if page.content and len(page.content) > 500 else page.content,
        "content_length": len(page.content) if page.content else 0,
        "token_count": token_count,
        "tfidf_size": tfidf_size,
        "relevantnost": page.relevantnost,
        "has_embedding": bool(page.embedding),
        "has_tfidf": bool(page.tf_idf),
        "has_tokens": bool(page.token_text),
        "crawled_at": page.crawled_at.isoformat() if page.crawled_at else None,
    }


# 6. QUEUE ENDPOINTS

@app.get("/api/queue/status", tags=["System"])
def queue_status():
    status = get_queue_status()
    return {
        "queue_size": status.get("queue_size", 0),
        "processing_size": status.get("processing_size", 0),
        "total": status.get("total", 0),
        "timestamp": datetime.utcnow().isoformat()
    }


@app.post("/api/queue/recover", tags=["System"])
def recover_queue_endpoint():
    try:
        task = recover_queue.delay()
        return {
            "message": "Задача на восстановление очереди отправлена",
            "task_id": task.id,
            "status": "processing"
        }
    except Exception as e:
        logger.error(f"❌ Ошибка при восстановлении очереди: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# 7. ADMIN ENDPOINTS

@app.post("/api/admin/recalculate-all", tags=["Admin"])
def recalculate_all_etl_endpoint(
        batch_size: Optional[int] = Query(None, description="Размер батча")
):

    try:
        task = recalculate_all_etl.delay(batch_size)
        return {
            "message": "Задача на полный пересчет ETL отправлена",
            "task_id": task.id,
            "status": "processing",
            "steps": [
                "SBERT эмбеддинги",
                "Токенизация",
                "Инвертированный индекс",
                "TF-IDF векторы",
                "Инициализация глобальных параметров"
            ]
        }
    except Exception as e:
        logger.error(f"❌ Ошибка при запуске ETL: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка: {str(e)}")


@app.post("/api/admin/update-params", tags=["Admin"])
def update_global_params_endpoint():

    try:
        task = update_global_params.delay()
        return {
            "message": "Задача на обновление глобальных параметров отправлена",
            "task_id": task.id,
            "status": "processing"
        }
    except Exception as e:
        logger.error(f"❌ Ошибка при обновлении параметров: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/admin/collect-stats", tags=["Admin"])
def collect_stats_endpoint():

    try:
        task = collect_stats.delay()
        return {
            "message": "Задача на сбор статистики отправлена",
            "task_id": task.id,
            "status": "processing"
        }
    except Exception as e:
        logger.error(f"❌ Ошибка при сборе статистики: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/admin/cleanup", tags=["Admin"])
def cleanup_old_data_endpoint(
        days_old: int = Query(30, ge=1, description="Возраст данных для удаления (дни)")
):

    try:
        task = cleanup_old_data.delay(days_old)
        return {
            "message": f"Задача на очистку данных старше {days_old} дней отправлена",
            "task_id": task.id,
            "status": "processing"
        }
    except Exception as e:
        logger.error(f"❌ Ошибка при очистке данных: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/admin/status", tags=["Admin"])
def admin_status():

    from config import GLOBAL_SEARCH_INITIALIZED

    connections = check_connections()
    queue_status = get_queue_status()
    global_stats = get_global_stats()
    search_stats = get_search_stats()
    nlp_info = get_nlp_info()
    model_info = get_model_info()

    return {
        "version": "3.0.0",
        "initialized": GLOBAL_SEARCH_INITIALIZED,
        "timestamp": datetime.utcnow().isoformat(),
        "connections": connections,
        "queue": queue_status,
        "search_stats": search_stats,
        "global_stats": global_stats,
        "nlp": nlp_info,
        "model": model_info
    }


# 8. EXCEPTION HANDLERS

@app.exception_handler(HTTPException)
def http_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "status_code": exc.status_code,
            "timestamp": datetime.utcnow().isoformat()
        }
    )


@app.exception_handler(Exception)
def general_exception_handler(request, exc):
    logger.error(f"❌ Необработанная ошибка: {exc}")
    import traceback
    logger.error(traceback.format_exc())

    return JSONResponse(
        status_code=500,
        content={
            "error": "Внутренняя ошибка сервера",
            "detail": str(exc) if settings.DEBUG else "Произошла внутренняя ошибка",
            "timestamp": datetime.utcnow().isoformat()
        }
    )


# 9. ЗАПУСК ПРИЛОЖЕНИЯ

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )