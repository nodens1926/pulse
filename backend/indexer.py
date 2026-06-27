import math
import logging
import numpy as np
from typing import List, Dict, Any, Optional, Set
from sqlalchemy.orm import Session
from sqlalchemy import func, text
from collections import Counter, defaultdict
from tqdm import tqdm

from models import Page, InvertedIndex
from config import settings, get_sbert_model
from nlp_utils import tokenize_and_lemmatize, get_nlp_info

logger = logging.getLogger(__name__)


# 1. SBERT EMBEDDING - ГЕНЕРАЦИЯ ЭМБЕДДИНГОВ

def sbert_embedding(db: Session, batch_size: int = None) -> Dict[str, Any]:
    if batch_size is None:
        batch_size = settings.SBERT_BATCH_SIZE

    logger.info("🚀 Начало генерации SBERT эмбеддингов...")

    model = get_sbert_model()
    if model is None:
        logger.error("❌ SBERT модель не загружена")
        return {"success": False, "error": "SBERT model not loaded"}

    all_ids = db.query(Page.id).filter(
        Page.content.isnot(None),
        Page.content != ''
    ).order_by(Page.id).all()

    all_ids = [row[0] for row in all_ids]
    total_records = len(all_ids)

    if total_records == 0:
        logger.warning("⚠️ Нет текстов для обработки эмбеддингов")
        return {"success": True, "processed": 0, "message": "No texts to process"}

    logger.info(f"📊 Найдено {total_records} страниц для обработки")

    processed_count = 0
    vector_size = settings.SBERT_VECTOR_SIZE

    with tqdm(total=total_records, desc="Генерация SBERT эмбеддингов") as pbar:
        for i in range(0, total_records, batch_size):
            batch_ids = all_ids[i:i + batch_size]

            pages_batch = db.query(Page).filter(
                Page.id.in_(batch_ids)
            ).order_by(Page.id).all()

            texts_to_encode = []
            pages_to_update = []

            for page in pages_batch:
                if page.content:
                    texts_to_encode.append(page.content[:1000])  # Ограничиваем длину
                    pages_to_update.append(page)
                else:
                    page.embedding = np.zeros(vector_size, dtype=np.float32).tobytes()
                    pages_to_update.append(page)

            if texts_to_encode:
                try:
                    embeddings = model.encode(texts_to_encode, convert_to_numpy=True)
                    embeddings = embeddings.astype(np.float32)

                    for j, page in enumerate(pages_to_update):
                        if page.content:
                            page.embedding = embeddings[j].tobytes()
                except Exception as e:
                    logger.error(f"❌ Ошибка при кодировании батча: {e}")
                    for page in pages_to_update:
                        if page.content:
                            page.embedding = np.zeros(vector_size, dtype=np.float32).tobytes()

            db.bulk_save_objects(pages_to_update)
            db.commit()

            processed_count += len(batch_ids)
            pbar.update(len(batch_ids))

    logger.info(f"✅ SBERT эмбеддинги сохранены для {processed_count} страниц")
    return {
        "success": True,
        "processed": processed_count,
        "total": total_records,
        "message": f"SBERT embeddings generated for {processed_count} pages"
    }


# 2. CREATE TOKENS - ТОКЕНИЗАЦИЯ И ЛЕММАТИЗАЦИЯ

def create_tokens(db: Session, batch_size: int = None) -> Dict[str, Any]:

    if batch_size is None:
        batch_size = settings.ETL_BATCH_SIZE

    logger.info("🚀 Начало токенизации и лемматизации текстов...")

    all_ids = db.query(Page.id).filter(
        Page.content.isnot(None),
        Page.content != ''
    ).order_by(Page.id).all()

    all_ids = [row[0] for row in all_ids]
    total_records = len(all_ids)

    if total_records == 0:
        logger.warning("⚠️ Нет текстов для токенизации")
        return {"success": True, "processed": 0, "message": "No texts to process"}

    logger.info(f"📊 Найдено {total_records} страниц для токенизации")

    processed_count = 0

    with tqdm(total=total_records, desc="Токенизация и лемматизация") as pbar:
        for i in range(0, total_records, batch_size):
            batch_ids = all_ids[i:i + batch_size]

            pages_batch = db.query(Page).filter(
                Page.id.in_(batch_ids)
            ).order_by(Page.id).all()

            pages_to_update = []

            for page in pages_batch:
                if not page.content:
                    continue

                try:
                    tokens = tokenize_and_lemmatize(page.content)
                    page.token_text = " ".join(tokens)
                    pages_to_update.append(page)
                except Exception as e:
                    logger.error(f"❌ Ошибка при токенизации страницы {page.id}: {e}")
                    page.token_text = ""
                    pages_to_update.append(page)

            if pages_to_update:
                db.bulk_save_objects(pages_to_update)
                db.commit()

            processed_count += len(batch_ids)
            pbar.update(len(batch_ids))

    logger.info(f"✅ Токенизация завершена для {processed_count} страниц")
    return {
        "success": True,
        "processed": processed_count,
        "total": total_records,
        "message": f"Tokens created for {processed_count} pages"
    }


# 3. CREATE DICT - СОЗДАНИЕ СЛОВАРЯ (ВСПОМОГАТЕЛЬНАЯ)

def create_dict(db: Session) -> Set[str]:

    logger.info("📚 Формирование словаря уникальных слов...")

    unique_words = set()

    # Получаем все token_text батчами
    query = db.query(Page.token_text).filter(
        Page.token_text.isnot(None),
        Page.token_text != ''
    ).yield_per(1000)

    for (token_text,) in query:
        if token_text:
            words = token_text.split()
            unique_words.update(words)

    logger.info(f"📚 Собрано {len(unique_words)} уникальных слов")
    return unique_words


# 4. INVERTED INDEX - ПОСТРОЕНИЕ ИНВЕРТИРОВАННОГО ИНДЕКСА

def func_inverted_index(
        db: Session,
        unique_words_set: Optional[Set[str]] = None,
        batch_size: int = None
) -> Dict[str, Any]:

    if batch_size is None:
        batch_size = settings.INDEX_BATCH_SIZE

    logger.info("🚀 Начало построения инвертированного индекса...")

    # Собираем уникальные слова, если не переданы
    if unique_words_set is None:
        unique_words_set = create_dict(db)
        if not unique_words_set:
            logger.warning("⚠️ Нет слов для создания инвертированного индекса")
            return {"success": True, "processed": 0, "message": "No words found"}

    logger.info(f"📊 Используется {len(unique_words_set)} уникальных слов")

    all_ids = db.query(Page.id).filter(
        Page.token_text.isnot(None),
        Page.token_text != ''
    ).order_by(Page.id).all()

    all_ids = [row[0] for row in all_ids]
    total_records = len(all_ids)

    if total_records == 0:
        logger.warning("⚠️ Нет токенизированных текстов для индексации")
        return {"success": True, "processed": 0, "message": "No tokenized texts"}

    logger.info(f"📊 Найдено {total_records} страниц для индексации")

    logger.info("🧹 Очистка старых записей из inverted_index...")
    db.query(InvertedIndex).filter(InvertedIndex.page_id.in_(all_ids)).delete(synchronize_session=False)
    db.commit()

    new_entries = []
    processed_count = 0

    with tqdm(total=total_records, desc="Построение инвертированного индекса") as pbar:
        for i in range(0, total_records, batch_size):
            batch_ids = all_ids[i:i + batch_size]

            pages_batch = db.query(Page).filter(
                Page.id.in_(batch_ids)
            ).order_by(Page.id).all()

            for page in pages_batch:
                if not page.token_text:
                    continue

                tokens = page.token_text.split()
                if not tokens:
                    continue

                total_tokens = len(tokens)
                token_counts = Counter(tokens)

                for word, freq in token_counts.items():
                    if word not in unique_words_set:
                        continue

                    tf = freq / total_tokens if total_tokens > 0 else 0.0

                    new_entries.append(
                        InvertedIndex(
                            word=word,
                            page_id=page.id,
                            frequency=freq,
                            weight=tf  # TF, а не TF-IDF!
                        )
                    )

            if new_entries:
                db.bulk_save_objects(new_entries)
                db.commit()
                new_entries = []

            processed_count += len(batch_ids)
            pbar.update(len(batch_ids))

    if new_entries:
        db.bulk_save_objects(new_entries)
        db.commit()

    logger.info(f"✅ Инвертированный индекс построен для {processed_count} страниц")
    return {
        "success": True,
        "processed": processed_count,
        "total": total_records,
        "unique_words": len(unique_words_set),
        "message": f"Inverted index built for {processed_count} pages"
    }


# 5. TF-IDF - ВЫЧИСЛЕНИЕ TF-IDF ВЕКТОРОВ

def tf_idf_func(db: Session, batch_size: int = None) -> Dict[str, Any]:
    if batch_size is None:
        batch_size = settings.TFIDF_BATCH_SIZE

    logger.info("🚀 Начало вычисления TF-IDF векторов...")

    n_doc = db.query(Page).filter(
        Page.token_text.isnot(None),
        Page.token_text != ''
    ).count()

    if n_doc == 0:
        logger.warning("⚠️ Нет документов для вычисления TF-IDF")
        return {"success": True, "processed": 0, "message": "No documents found"}

    logger.info(f"📊 Общее количество документов (n_doc): {n_doc}")

    vocabulary_query = db.query(InvertedIndex.word.distinct()).order_by(InvertedIndex.word)
    vocabulary_list = [row[0] for row in vocabulary_query.all()]
    vocabulary_size = len(vocabulary_list)
    vocabulary_to_idx = {word: idx for idx, word in enumerate(vocabulary_list)}

    if vocabulary_size == 0:
        logger.warning("⚠️ Словарь пуст")
        return {"success": True, "processed": 0, "message": "Vocabulary is empty"}

    logger.info(f"📚 Размер словаря: {vocabulary_size}")

    word_doc_counts = {}
    doc_counts_query = db.query(
        InvertedIndex.word,
        func.count(InvertedIndex.page_id.distinct())
    ).group_by(InvertedIndex.word).all()

    for word, count in doc_counts_query:
        word_doc_counts[word] = count

    logger.info("📊 IDF рассчитаны для каждого слова")

    all_ids = db.query(Page.id).filter(
        Page.token_text.isnot(None),
        Page.token_text != ''
    ).order_by(Page.id).all()

    all_ids = [row[0] for row in all_ids]
    total_records = len(all_ids)

    if total_records == 0:
        logger.warning("⚠️ Нет страниц для вычисления TF-IDF")
        return {"success": True, "processed": 0, "message": "No pages with tokens"}

    logger.info(f"📊 Вычисление TF-IDF для {total_records} страниц")

    processed_count = 0

    with tqdm(total=total_records, desc="Вычисление TF-IDF векторов") as pbar:
        for i in range(0, total_records, batch_size):
            batch_ids = all_ids[i:i + batch_size]

            pages_batch = db.query(Page).filter(
                Page.id.in_(batch_ids)
            ).order_by(Page.id).all()

            inverted_entries = db.query(InvertedIndex).filter(
                InvertedIndex.page_id.in_(batch_ids)
            ).all()

            page_tf_data = defaultdict(dict)
            for entry in inverted_entries:
                page_tf_data[entry.page_id][entry.word] = entry.weight

            pages_to_update = []

            for page in pages_batch:
                if not page.token_text:
                    continue

                tf_idf_vector = np.zeros(vocabulary_size, dtype=np.float32)

                page_tf = page_tf_data.get(page.id, {})

                for word, vocab_idx in vocabulary_to_idx.items():
                    tf = page_tf.get(word, 0.0)

                    if tf == 0.0:
                        continue

                    n_cur = word_doc_counts.get(word, 0)
                    if n_cur > 0 and n_doc > 0:
                        idf = math.log(n_doc / n_cur)
                        tf_idf_vector[vocab_idx] = tf * idf

                page.tf_idf = tf_idf_vector.tolist()
                pages_to_update.append(page)

            if pages_to_update:
                db.bulk_save_objects(pages_to_update)
                db.commit()

            processed_count += len(batch_ids)
            pbar.update(len(batch_ids))

    logger.info(f"✅ TF-IDF векторы вычислены для {processed_count} страниц")
    return {
        "success": True,
        "processed": processed_count,
        "total": total_records,
        "vocabulary_size": vocabulary_size,
        "message": f"TF-IDF vectors computed for {processed_count} pages"
    }


# 6. ИНИЦИАЛИЗАЦИЯ ГЛОБАЛЬНЫХ ПАРАМЕТРОВ ПОИСКА

def initialize_global_search_params(db: Session) -> Dict[str, Any]:

    from config import GLOBAL_N_DOC, GLOBAL_VOCABULARY_LIST, GLOBAL_VOCABULARY_TO_IDX, GLOBAL_WORD_DOC_COUNTS, \
        GLOBAL_SEARCH_INITIALIZED
    import config

    logger.info("🔧 Инициализация глобальных параметров поиска...")

    try:
        n_doc = db.query(Page).filter(
            Page.token_text.isnot(None),
            Page.token_text != ''
        ).count()
        config.GLOBAL_N_DOC = n_doc
        logger.info(f"📊 Глобальное n_doc: {n_doc}")

        vocabulary_query = db.query(InvertedIndex.word.distinct()).order_by(InvertedIndex.word)
        vocabulary_list = [row[0] for row in vocabulary_query.all()]
        config.GLOBAL_VOCABULARY_LIST = vocabulary_list
        config.GLOBAL_VOCABULARY_TO_IDX = {word: idx for idx, word in enumerate(vocabulary_list)}
        logger.info(f"📚 Размер глобального словаря: {len(vocabulary_list)}")

        doc_counts_query = db.query(
            InvertedIndex.word,
            func.count(InvertedIndex.page_id.distinct())
        ).group_by(InvertedIndex.word).all()

        word_doc_counts = {}
        for word, count in doc_counts_query:
            word_doc_counts[word] = count
        config.GLOBAL_WORD_DOC_COUNTS = word_doc_counts

        config.GLOBAL_SEARCH_INITIALIZED = True

        logger.info("✅ Глобальные параметры поиска инициализированы")

        return {
            "success": True,
            "n_doc": n_doc,
            "vocabulary_size": len(vocabulary_list),
            "unique_words_count": len(word_doc_counts)
        }

    except Exception as e:
        logger.error(f"❌ Ошибка при инициализации глобальных параметров: {e}")
        config.GLOBAL_SEARCH_INITIALIZED = False
        return {"success": False, "error": str(e)}


# 7. ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ

def get_global_stats() -> Dict[str, Any]:
    from config import GLOBAL_N_DOC, GLOBAL_VOCABULARY_LIST, GLOBAL_WORD_DOC_COUNTS, GLOBAL_SEARCH_INITIALIZED

    return {
        "initialized": GLOBAL_SEARCH_INITIALIZED,
        "total_documents": GLOBAL_N_DOC,
        "vocabulary_size": len(GLOBAL_VOCABULARY_LIST),
        "unique_words_count": len(GLOBAL_WORD_DOC_COUNTS),
    }


def get_nlp_info() -> Dict[str, Any]:
    from nlp_utils import get_nlp_info as get_nlp_info_utils
    return get_nlp_info_utils()


if __name__ == "__main__":
    print("✅ indexer.py загружен")
    print(f"   - SBERT_BATCH_SIZE: {settings.SBERT_BATCH_SIZE}")
    print(f"   - ETL_BATCH_SIZE: {settings.ETL_BATCH_SIZE}")
    print(f"   - TFIDF_BATCH_SIZE: {settings.TFIDF_BATCH_SIZE}")