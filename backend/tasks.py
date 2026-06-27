from celery import Celery
from celery.utils.log import get_task_logger
from sqlalchemy.orm import Session
import redis
import json
import traceback
from typing import Optional, Dict, Any, List
from datetime import datetime
import time

from config import settings, SessionLocal, redis_client
from models import Site, Page, InvertedIndex
from crawler import crawl
from parser import extract_text_for_indexing, extract_links
from indexer import (
    sbert_embedding,
    create_tokens,
    func_inverted_index,
    tf_idf_func,
    initialize_global_search_params
)
from nlp_utils import tokenize_and_lemmatize

logger = get_task_logger(__name__)

# --- НАСТРОЙКА CELERY ---
app = Celery(
    'pulse_tasks',
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=['tasks']
)

app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=600,  # Увеличиваем до 10 минут
    task_soft_time_limit=540,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    result_expires=3600,
    task_default_queue='default',
    task_default_exchange='default',
    task_default_routing_key='default',
)

# --- КЛЮЧИ ДЛЯ REDIS ---
QUEUE_KEY = "indexing_queue"
PROCESSING_KEY = "processing_queue"


# 1. ФУНКЦИИ ДЛЯ РАБОТЫ С ОЧЕРЕДЬЮ

def add_to_queue(url: str) -> bool:
    try:
        if redis_client is None:
            logger.error("❌ Redis не доступен")
            return False

        queue_items = redis_client.lrange(QUEUE_KEY, 0, -1)
        processing_items = redis_client.lrange(PROCESSING_KEY, 0, -1)

        if url in queue_items or url in processing_items:
            logger.warning(f"⚠️ URL уже в очереди: {url}")
            return False

        redis_client.rpush(QUEUE_KEY, url)
        logger.info(f"✅ URL добавлен в очередь: {url}")
        return True

    except Exception as e:
        logger.error(f"❌ Ошибка при добавлении в очередь: {e}")
        return False


def get_from_queue() -> Optional[str]:
    try:
        if redis_client is None:
            logger.error("❌ Redis не доступен")
            return None

        result = redis_client.blpop(QUEUE_KEY, timeout=1)
        if result:
            url = result[1]
            redis_client.rpush(PROCESSING_KEY, url)
            logger.info(f"📥 URL взят в обработку: {url}")
            return url
        return None

    except Exception as e:
        logger.error(f"❌ Ошибка при получении из очереди: {e}")
        return None


def complete_processing(url: str) -> bool:
    try:
        if redis_client is None:
            return False

        removed = redis_client.lrem(PROCESSING_KEY, 0, url)
        if removed:
            logger.info(f"✅ URL завершён: {url}")
        return True

    except Exception as e:
        logger.error(f"❌ Ошибка при завершении обработки: {e}")
        return False


def get_queue_status() -> Dict[str, Any]:
    try:
        if redis_client is None:
            return {"queue_size": 0, "processing_size": 0, "total": 0, "error": "Redis not available"}

        queue_len = redis_client.llen(QUEUE_KEY)
        processing_len = redis_client.llen(PROCESSING_KEY)

        return {
            "queue_size": queue_len,
            "processing_size": processing_len,
            "total": queue_len + processing_len
        }

    except Exception as e:
        logger.error(f"❌ Ошибка при получении статуса: {e}")
        return {"queue_size": 0, "processing_size": 0, "total": 0, "error": str(e)}


# 2. ОСНОВНАЯ ЗАДАЧА: ИНДЕКСАЦИЯ САЙТА

@app.task(bind=True, name="tasks.index_site", max_retries=3)
def index_site(self, site_id: int) -> Dict[str, Any]:

    result = {
        "site_id": site_id,
        "success": False,
        "pages_indexed": 0,
        "error": None,
        "url": None,
        "status": "pending"
    }

    db = SessionLocal()

    try:
        site = db.query(Site).filter(Site.id == site_id).first()
        if not site:
            result["error"] = f"Site {site_id} not found"
            logger.error(result["error"])
            return result

        result["url"] = site.url
        logger.info(f"🚀 Начало индексации: {site.url} (ID: {site_id})")

        site.status = "processing"
        db.commit()

        html, final_url, error, status_code = crawl(site.url)

        if error:
            result["error"] = f"Crawl error: {error}"
            site.status = "error"
            db.commit()
            logger.error(f"❌ {result['error']}")
            return result

        title, clean_text = extract_text_for_indexing(html)

        if not clean_text:
            result["error"] = "No text extracted"
            site.status = "error"
            db.commit()
            logger.error(f"❌ {result['error']}")
            return result

        page = Page(
            site_id=site_id,
            url=final_url or site.url,
            title=title or site.url,
            content=clean_text
        )
        db.add(page)
        db.commit()
        db.refresh(page)

        logger.info(f"📄 Страница сохранена: {page.id} - {page.title}")

        etl_success = process_page_etl(db, page.id)

        if not etl_success:
            result["error"] = "ETL pipeline failed"
            site.status = "error"
            db.commit()
            logger.error(f"❌ {result['error']}")
            return result

        site.status = "indexed"
        site.last_crawled = datetime.utcnow()
        db.commit()

        # 8. АВТОМАТИЧЕСКИ ОБНОВЛЯЕМ ГЛОБАЛЬНЫЕ ПАРАМЕТРЫ
        logger.info(f"🔄 Обновление глобальных параметров после индексации {site.url}")
        try:
            from indexer import initialize_global_search_params
            update_db = SessionLocal()
            try:
                init_result = initialize_global_search_params(update_db)
                logger.info(f"✅ Глобальные параметры обновлены: {init_result}")
            finally:
                update_db.close()
        except Exception as e:
            logger.error(f"⚠️ Ошибка при обновлении глобальных параметров: {e}")

        result["success"] = True
        result["pages_indexed"] = 1
        result["status"] = "indexed"

        logger.info(f"✅ Индексация завершена: {site.url} (ID: {site_id})")
        return result

    except Exception as e:
        db.rollback()
        result["error"] = str(e)
        result["status"] = "error"
        logger.error(f"❌ Неожиданная ошибка: {e}")
        logger.error(traceback.format_exc())

        try:
            site = db.query(Site).filter(Site.id == site_id).first()
            if site:
                site.status = "error"
                db.commit()
        except:
            pass

        return result

    finally:
        db.close()


# 3. ВСПОМОГАТЕЛЬНАЯ ЗАДАЧА: ETL ДЛЯ ОДНОЙ СТРАНИЦЫ

def process_page_etl(db: Session, page_id: int) -> bool:
    try:
        logger.info(f"🔄 Запуск ETL для страницы {page_id}")

        logger.info(f"  📝 Шаг 1/4: Токенизация страницы {page_id}")
        create_tokens_for_page(db, page_id)

        logger.info(f"  📚 Шаг 2/4: Обновление инвертированного индекса для страницы {page_id}")
        update_inverted_index_for_page(db, page_id)

        logger.info(f"  📊 Шаг 3/4: Пересчет TF-IDF для страницы {page_id}")
        update_tfidf_for_page(db, page_id)

        logger.info(f"  🧠 Шаг 4/4: Генерация SBERT эмбеддинга для страницы {page_id}")
        update_sbert_for_page(db, page_id)

        logger.info(f"✅ ETL для страницы {page_id} завершен")
        return True

    except Exception as e:
        logger.error(f"❌ Ошибка в ETL для страницы {page_id}: {e}")
        logger.error(traceback.format_exc())
        return False


def create_tokens_for_page(db: Session, page_id: int) -> None:
    page = db.query(Page).filter(Page.id == page_id).first()
    if not page or not page.content:
        return

    tokens = tokenize_and_lemmatize(page.content)
    page.token_text = " ".join(tokens)
    db.commit()


def update_inverted_index_for_page(db: Session, page_id: int) -> None:
    page = db.query(Page).filter(Page.id == page_id).first()
    if not page or not page.token_text:
        return

    db.query(InvertedIndex).filter(InvertedIndex.page_id == page_id).delete()

    tokens = page.token_text.split()
    if not tokens:
        return

    from collections import Counter
    total_tokens = len(tokens)
    token_counts = Counter(tokens)

    for word, freq in token_counts.items():
        tf = freq / total_tokens
        db.add(InvertedIndex(
            word=word,
            page_id=page_id,
            frequency=freq,
            weight=tf
        ))

    db.commit()


def update_tfidf_for_page(db: Session, page_id: int) -> None:
    from indexer import tf_idf_func
    tf_idf_func(db, batch_size=settings.TFIDF_BATCH_SIZE)


def update_sbert_for_page(db: Session, page_id: int) -> None:
    from indexer import sbert_embedding
    sbert_embedding(db, batch_size=settings.SBERT_BATCH_SIZE)


# 4. ЗАДАЧА: ИНДЕКСАЦИЯ НЕСКОЛЬКИХ САЙТОВ

@app.task(name="tasks.index_multiple_sites")
def index_multiple_sites(site_ids: List[int]) -> Dict[str, Any]:

    logger.info(f"🚀 Запуск индексации {len(site_ids)} сайтов")

    results = []
    success_count = 0
    error_count = 0

    for site_id in site_ids:
        try:
            result = index_site.delay(site_id).get(timeout=600)
            if result.get("success"):
                success_count += 1
            else:
                error_count += 1
            results.append(result)

        except Exception as e:
            error_count += 1
            results.append({
                "site_id": site_id,
                "success": False,
                "error": str(e)
            })

    logger.info(f"✅ Индексация завершена: успешно {success_count}, ошибок {error_count}")

    return {
        "total": len(site_ids),
        "success": success_count,
        "errors": error_count,
        "results": results
    }


# 5. ЗАДАЧА: ПОЛНЫЙ ПЕРЕСЧЕТ ВСЕХ ДАННЫХ (ETL)

@app.task(name="tasks.recalculate_all_etl", bind=True, max_retries=2)
def recalculate_all_etl(self, batch_size: int = None) -> Dict[str, Any]:

    if batch_size is None:
        batch_size = settings.ETL_BATCH_SIZE

    logger.info("🚀 ЗАПУСК ПОЛНОГО ПЕРЕСЧЕТА ETL")

    db = SessionLocal()
    results = {
        "success": False,
        "steps": {},
        "errors": []
    }

    try:
        logger.info("📌 Шаг 1/5: Генерация SBERT эмбеддингов...")
        try:
            result = sbert_embedding(db, batch_size)
            results["steps"]["sbert_embedding"] = result
            logger.info(f"  ✅ SBERT: {result.get('processed', 0)} страниц")
        except Exception as e:
            logger.error(f"  ❌ Ошибка в SBERT: {e}")
            results["errors"].append(f"SBERT: {str(e)}")

        logger.info("📌 Шаг 2/5: Токенизация текстов...")
        try:
            result = create_tokens(db, batch_size)
            results["steps"]["create_tokens"] = result
            logger.info(f"  ✅ Токенизация: {result.get('processed', 0)} страниц")
        except Exception as e:
            logger.error(f"  ❌ Ошибка в токенизации: {e}")
            results["errors"].append(f"Tokens: {str(e)}")

        logger.info("📌 Шаг 3/5: Построение инвертированного индекса...")
        try:
            result = func_inverted_index(db, batch_size=batch_size)
            results["steps"]["inverted_index"] = result
            logger.info(f"  ✅ Инвертированный индекс: {result.get('processed', 0)} страниц")
        except Exception as e:
            logger.error(f"  ❌ Ошибка в инвертированном индексе: {e}")
            results["errors"].append(f"InvertedIndex: {str(e)}")

        logger.info("📌 Шаг 4/5: Вычисление TF-IDF векторов...")
        try:
            result = tf_idf_func(db, batch_size)
            results["steps"]["tf_idf"] = result
            logger.info(f"  ✅ TF-IDF: {result.get('processed', 0)} страниц")
        except Exception as e:
            logger.error(f"  ❌ Ошибка в TF-IDF: {e}")
            results["errors"].append(f"TF-IDF: {str(e)}")

        logger.info("📌 Шаг 5/5: Инициализация глобальных параметров поиска...")
        try:
            result = initialize_global_search_params(db)
            results["steps"]["global_params"] = result
            logger.info(f"  ✅ Глобальные параметры: {result.get('n_doc', 0)} документов")
        except Exception as e:
            logger.error(f"  ❌ Ошибка в глобальных параметрах: {e}")
            results["errors"].append(f"GlobalParams: {str(e)}")

        if not results["errors"]:
            results["success"] = True
            logger.info("✅ ПОЛНЫЙ ПЕРЕСЧЕТ ETL ЗАВЕРШЕН УСПЕШНО")
        else:
            logger.warning(f"⚠️ Пересчет завершен с {len(results['errors'])} ошибками")

        return results

    except Exception as e:
        logger.error(f"❌ Критическая ошибка в ETL: {e}")
        logger.error(traceback.format_exc())
        results["errors"].append(f"Critical: {str(e)}")
        return results

    finally:
        db.close()


# 6. ЗАДАЧА: ОБНОВЛЕНИЕ ГЛОБАЛЬНЫХ ПАРАМЕТРОВ

@app.task(name="tasks.update_global_params")
def update_global_params() -> Dict[str, Any]:

    logger.info("🔄 Обновление глобальных параметров поиска...")

    db = SessionLocal()
    try:
        result = initialize_global_search_params(db)
        logger.info(f"✅ Глобальные параметры обновлены: {result}")
        return result
    except Exception as e:
        logger.error(f"❌ Ошибка при обновлении параметров: {e}")
        return {"success": False, "error": str(e)}
    finally:
        db.close()


# 7. ЗАДАЧА: ВОССТАНОВЛЕНИЕ ОЧЕРЕДИ

@app.task(name="tasks.recover_queue")
def recover_queue() -> Dict[str, Any]:

    try:
        if redis_client is None:
            return {"success": False, "error": "Redis not available"}

        processing_items = redis_client.lrange(PROCESSING_KEY, 0, -1)

        if not processing_items:
            logger.info("✅ Очередь обработки пуста")
            return {"success": True, "recovered": 0}

        logger.info(f"🔄 Восстановление {len(processing_items)} задач")

        recovered = 0
        for url in processing_items:
            redis_client.rpush(QUEUE_KEY, url)
            redis_client.lrem(PROCESSING_KEY, 0, url)
            recovered += 1
            logger.info(f"  ✅ Восстановлен: {url}")

        logger.info(f"✅ Восстановлено {recovered} задач")
        return {"success": True, "recovered": recovered}

    except Exception as e:
        logger.error(f"❌ Ошибка при восстановлении: {e}")
        return {"success": False, "error": str(e)}


# 8. ЗАДАЧА: ОЧИСТКА СТАРЫХ ДАННЫХ

@app.task(name="tasks.cleanup_old_data")
def cleanup_old_data(days_old: int = 30) -> Dict[str, Any]:

    logger.info(f"🧹 Очистка данных старше {days_old} дней...")

    db = SessionLocal()
    try:
        from sqlalchemy import text

        result = db.execute(
            text("""
                DELETE FROM pages 
                WHERE crawled_at < NOW() - INTERVAL :days DAY
                AND id NOT IN (
                    SELECT DISTINCT page_id FROM inverted_index
                )
            """),
            {"days": days_old}
        )

        deleted = result.rowcount
        db.commit()

        logger.info(f"✅ Удалено {deleted} старых страниц")
        return {"success": True, "deleted": deleted}

    except Exception as e:
        db.rollback()
        logger.error(f"❌ Ошибка при очистке: {e}")
        return {"success": False, "error": str(e)}
    finally:
        db.close()


# 9. ЗАДАЧА: СБОР СТАТИСТИКИ

@app.task(name="tasks.collect_stats")
def collect_stats() -> Dict[str, Any]:

    db = SessionLocal()
    try:
        total_pages = db.query(Page).count()
        pages_with_embedding = db.query(Page).filter(Page.embedding.isnot(None)).count()
        pages_with_tfidf = db.query(Page).filter(Page.tf_idf.isnot(None)).count()
        pages_with_tokens = db.query(Page).filter(Page.token_text.isnot(None)).count()

        total_sites = db.query(Site).count()
        indexed_sites = db.query(Site).filter(Site.status == "indexed").count()

        total_entries = db.query(InvertedIndex).count()
        unique_words = db.query(InvertedIndex.word.distinct()).count()

        return {
            "pages": {
                "total": total_pages,
                "with_embedding": pages_with_embedding,
                "with_tfidf": pages_with_tfidf,
                "with_tokens": pages_with_tokens,
            },
            "sites": {
                "total": total_sites,
                "indexed": indexed_sites,
            },
            "inverted_index": {
                "total_entries": total_entries,
                "unique_words": unique_words,
            },
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        logger.error(f"❌ Ошибка при сборе статистики: {e}")
        return {"error": str(e)}
    finally:
        db.close()


# 10. ТЕСТОВАЯ ФУНКЦИЯ

if __name__ == "__main__":
    print("✅ tasks.py загружен")
    print(f"   - Redis URL: {settings.REDIS_URL}")
    print(f"   - Queue: {QUEUE_KEY}")
    print(f"   - Processing: {PROCESSING_KEY}")