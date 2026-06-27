import math
import logging
import numpy as np
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func
from scipy.spatial.distance import cosine
from collections import Counter
import re

from models import Page, InvertedIndex
from config import (
    settings,
    GLOBAL_N_DOC,
    GLOBAL_VOCABULARY_LIST,
    GLOBAL_VOCABULARY_TO_IDX,
    GLOBAL_WORD_DOC_COUNTS,
    GLOBAL_SEARCH_INITIALIZED,
    get_sbert_model,
    bytes_to_array
)
from nlp_utils import tokenize_and_lemmatize

logger = logging.getLogger(__name__)


# 1. TF-IDF ЗАПРОСА

def tf_idf_query(query_text: str) -> np.ndarray:
    from config import GLOBAL_SEARCH_INITIALIZED, GLOBAL_VOCABULARY_LIST, GLOBAL_VOCABULARY_TO_IDX, GLOBAL_WORD_DOC_COUNTS, GLOBAL_N_DOC
    
    if not GLOBAL_SEARCH_INITIALIZED:
        raise ValueError("Глобальные параметры для TF-IDF не инициализированы")
    
    if not query_text or not isinstance(query_text, str):
        return np.zeros(len(GLOBAL_VOCABULARY_LIST), dtype=np.float32)

    processed_tokens = tokenize_and_lemmatize(query_text)
    
    if not processed_tokens:
        logger.warning(f"Запрос после токенизации оказался пустым: {query_text}")
        return np.zeros(len(GLOBAL_VOCABULARY_LIST), dtype=np.float32)

    query_tf_idf_vector = np.zeros(len(GLOBAL_VOCABULARY_LIST), dtype=np.float32)
    query_token_counts = Counter(processed_tokens)
    total_query_tokens = len(processed_tokens)
    
    for word, vocab_idx in GLOBAL_VOCABULARY_TO_IDX.items():
        tf_current_word = query_token_counts.get(word, 0) / total_query_tokens
        if tf_current_word == 0.0:
            continue
        
        n_cur = GLOBAL_WORD_DOC_COUNTS.get(word, 0)
        if n_cur > 0 and GLOBAL_N_DOC > 0:
            idf = math.log(GLOBAL_N_DOC / n_cur)
            query_tf_idf_vector[vocab_idx] = tf_current_word * idf
    
    return query_tf_idf_vector
def rank_by_tf_idf(
        db: Session,
        query_tf_idf_vector: np.ndarray,
        top_n_results: int = 50,
        batch_size: int = None
) -> List[int]:

    if batch_size is None:
        batch_size = settings.TFIDF_BATCH_SIZE

    logger.info("📊 Расчет косинусного сходства TF-IDF и ранжирование страниц...")

    all_pages = db.query(Page.id, Page.tf_idf).filter(
        Page.tf_idf.isnot(None)
    ).order_by(Page.id).all()

    if not all_pages:
        logger.warning("⚠️ В базе данных нет TF-IDF векторов для сравнения")
        return []

    total_pages = len(all_pages)
    logger.info(f"📊 Найдено {total_pages} страниц с TF-IDF векторами")

    relevance_scores = []
    pages_to_update = []

    for i in range(0, total_pages, batch_size):
        batch_pages = all_pages[i:i + batch_size]

        for page_id, page_tf_idf_list in batch_pages:
            if not page_tf_idf_list:
                continue

            page_tf_idf_vector = np.array(page_tf_idf_list, dtype=np.float32)

            try:
                similarity = 1 - cosine(query_tf_idf_vector, page_tf_idf_vector)
                if np.isnan(similarity):
                    similarity = 0.0
            except Exception as e:
                logger.error(f"❌ Ошибка при вычислении косинусного сходства: {e}")
                similarity = 0.0

            relevance_scores.append((similarity, page_id))

            page_obj = db.query(Page).get(page_id)
            if page_obj:
                page_obj.relevantnost = similarity
                pages_to_update.append(page_obj)

        if pages_to_update:
            db.bulk_save_objects(pages_to_update)
            db.commit()
            pages_to_update = []

    relevance_scores.sort(key=lambda x: x[0], reverse=True)
    logger.info(f"✅ TF-IDF ранжирование завершено. Обновлено {total_pages} страниц")

    top_ids = [page_id for score, page_id in relevance_scores[:top_n_results]]
    logger.info(f"📊 Топ-{top_n_results} ID страниц по TF-IDF: {top_ids[:5]}...")

    return top_ids


# 3. ДОРАНЖИРОВАНИЕ С SBERT

def rerank_with_sbert(
        db: Session,
        query_text: str,
        tf_idf_list_50: List[int]
) -> List[int]:
    if not tf_idf_list_50:
        logger.warning("⚠️ Список ID для доранжирования пуст")
        return []

    sbert_model = get_sbert_model()
    if sbert_model is None:
        logger.error("❌ SBERT модель не загружена")
        return tf_idf_list_50

    logger.info("🔬 Вычисление SBERT эмбеддинга запроса...")

    try:
        query_embedding = sbert_model.encode(query_text, convert_to_numpy=True)
        query_embedding = query_embedding.astype(np.float32)
    except Exception as e:
        logger.error(f"❌ Ошибка при генерации эмбеддинга запроса: {e}")
        return tf_idf_list_50

    logger.info(f"📊 Доранжирование {len(tf_idf_list_50)} страниц с помощью SBERT...")

    pages_embeddings = db.query(Page.id, Page.embedding).filter(
        Page.id.in_(tf_idf_list_50),
        Page.embedding.isnot(None)
    ).all()

    if not pages_embeddings:
        logger.warning("⚠️ Нет SBERT эмбеддингов для доранжирования")
        return tf_idf_list_50

    sbert_relevance_scores = []

    for page_id, embedding_bytes in pages_embeddings:
        if embedding_bytes is None:
            continue

        try:
            page_embedding = bytes_to_array(embedding_bytes)

            similarity = 1 - cosine(query_embedding, page_embedding)
            if np.isnan(similarity):
                similarity = 0.0

            sbert_relevance_scores.append((similarity, page_id))

        except Exception as e:
            logger.error(f"❌ Ошибка при вычислении SBERT сходства для страницы {page_id}: {e}")
            sbert_relevance_scores.append((0.0, page_id))

    sbert_relevance_scores.sort(key=lambda x: x[0], reverse=True)

    reranked_ids = [page_id for score, page_id in sbert_relevance_scores]

    logger.info(f"✅ SBERT доранжирование завершено. Результатов: {len(reranked_ids)}")

    missing_ids = [pid for pid in tf_idf_list_50 if pid not in reranked_ids]
    if missing_ids:
        logger.warning(f"⚠️ {len(missing_ids)} страниц не имеют SBERT эмбеддингов, добавлены в конец")
        reranked_ids.extend(missing_ids)

    return reranked_ids


# 4. ОСНОВНАЯ ФУНКЦИЯ ПОИСКА

def search(
        db: Session,
        query: str,
        top_k: int = 50,
        final_k: int = 10
) -> List[Dict[str, Any]]:

    from config import GLOBAL_SEARCH_INITIALIZED
    
    if not query or not query.strip():
        logger.warning("⚠️ Пустой поисковый запрос")
        return []

    if len(query.strip()) < 2:
        logger.warning(f"⚠️ Слишком короткий запрос: {query}")
        return []

    if not GLOBAL_SEARCH_INITIALIZED:
        logger.error("❌ Глобальные параметры поиска не инициализированы")
        return []

    logger.info(f"🔍 Поиск: '{query}' (top_k={top_k}, final_k={final_k})")

    try:
        # ЭТАП 1: Вычисляем TF-IDF вектор запроса
        query_tf_idf_vector = tf_idf_query(query)

        if np.all(query_tf_idf_vector == 0):
            logger.warning("⚠️ TF-IDF вектор запроса нулевой")
            return []

        # ЭТАП 2: Ранжируем по TF-IDF (получаем топ-50)
        tf_idf_top_ids = rank_by_tf_idf(db, query_tf_idf_vector, top_k)

        if not tf_idf_top_ids:
            logger.info(f"ℹ️ Нет результатов для запроса: {query}")
            return []

        # ЭТАП 3: Доранжируем с SBERT
        final_ranked_ids = rerank_with_sbert(db, query, tf_idf_top_ids)

        # ЭТАП 4: Берем только final_k результатов
        final_ids = final_ranked_ids[:final_k]

        # ЭТАП 5: Получаем полные данные страниц
        results = []
        for page_id in final_ids:
            page = db.query(Page).filter(Page.id == page_id).first()
            if page:
                sbert_score = 0.0
                if page.embedding:
                    try:
                        sbert_model = get_sbert_model()
                        if sbert_model:
                            query_embedding = sbert_model.encode(query, convert_to_numpy=True)
                            page_embedding = bytes_to_array(page.embedding)
                            sbert_score = 1 - cosine(query_embedding, page_embedding)
                            if np.isnan(sbert_score):
                                sbert_score = 0.0
                    except Exception as e:
                        logger.error(f"Ошибка при вычислении SBERT оценки: {e}")

                results.append({
                    "id": page.id,
                    "url": page.url,
                    "title": page.title or page.url,
                    "relevantnost": page.relevantnost or 0.0,
                    "sbert_score": round(sbert_score, 4),
                })

        logger.info(f"✅ Найдено {len(results)} результатов")
        return results

    except Exception as e:
        logger.error(f"❌ Ошибка при поиске: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return []


# 5. ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ

def get_explanation(
        db: Session,
        page_id: int,
        query: str
) -> Dict[str, Any]:

    page = db.query(Page).filter(Page.id == page_id).first()
    if not page:
        return {"error": "Page not found"}

    query_words = tokenize_and_lemmatize(query)

    frequencies = db.query(InvertedIndex).filter(
        InvertedIndex.page_id == page_id,
        InvertedIndex.word.in_(query_words)
    ).all()

    word_info = []
    total_freq = 0
    total_tf = 0.0

    for entry in frequencies:
        word_info.append({
            "word": entry.word,
            "frequency": entry.frequency,
            "tf": entry.weight,  # TF
            "tf_idf": entry.weight * math.log(
                GLOBAL_N_DOC / GLOBAL_WORD_DOC_COUNTS.get(entry.word, 1)
            ) if GLOBAL_N_DOC > 0 else 0.0
        })
        total_freq += entry.frequency
        total_tf += entry.weight or 0.0

    sbert_similarity = 0.0
    if page.embedding:
        try:
            sbert_model = get_sbert_model()
            if sbert_model:
                query_embedding = sbert_model.encode(query, convert_to_numpy=True)
                page_embedding = bytes_to_array(page.embedding)
                sbert_similarity = 1 - cosine(query_embedding, page_embedding)
                if np.isnan(sbert_similarity):
                    sbert_similarity = 0.0
        except Exception as e:
            logger.error(f"Ошибка при вычислении SBERT сходства: {e}")

    return {
        "page_id": page_id,
        "title": page.title,
        "url": page.url,
        "query_words": query_words,
        "word_frequencies": word_info,
        "total_frequency": total_freq,
        "total_tf": round(total_tf, 4),
        "relevantnost": page.relevantnost or 0.0,
        "sbert_similarity": round(sbert_similarity, 4),
        "has_embedding": bool(page.embedding),
        "has_tf_idf": bool(page.tf_idf),
    }


def get_search_stats() -> Dict[str, Any]:

    from config import GLOBAL_N_DOC, GLOBAL_VOCABULARY_LIST, GLOBAL_WORD_DOC_COUNTS, GLOBAL_SEARCH_INITIALIZED

    return {
        "initialized": GLOBAL_SEARCH_INITIALIZED,
        "total_documents": GLOBAL_N_DOC,
        "vocabulary_size": len(GLOBAL_VOCABULARY_LIST),
        "unique_words_count": len(GLOBAL_WORD_DOC_COUNTS),
        "sbert_model_loaded": get_sbert_model() is not None,
    }


# 6. ТЕСТОВАЯ ФУНКЦИЯ

if __name__ == "__main__":
    from config import SessionLocal

    print("🧪 Тестирование ml.py...")

    db = SessionLocal()
    try:
        from indexer import initialize_global_search_params

        initialize_global_search_params(db)

        test_query = "машинное обучение"
        results = search(db, test_query, top_k=10, final_k=5)

        print(f"\n📊 Результаты для '{test_query}':")
        for i, result in enumerate(results, 1):
            print(f"  {i}. {result['title']} (релевантность: {result['relevantnost']:.4f})")

    except Exception as e:
        logger.error(f"Ошибка при тестировании: {e}")
    finally:
        db.close()