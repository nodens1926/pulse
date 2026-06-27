import os
import logging
from typing import Dict, Any
from pydantic_settings import BaseSettings
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import redis
import numpy as np
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)


# --- НАСТРОЙКИ ПРИЛОЖЕНИЯ ---
class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+psycopg2://user:password@localhost:5432/pulse_search"

    REDIS_URL: str = "redis://localhost:6379/0"

    SBERT_MODEL_NAME: str = "all-MiniLM-L6-v2"
    SBERT_VECTOR_SIZE: int = 384
    SBERT_BATCH_SIZE: int = 1000

    ETL_BATCH_SIZE: int = 1000
    TFIDF_BATCH_SIZE: int = 1000
    INDEX_BATCH_SIZE: int = 1000

    DEFAULT_TOP_K: int = 50
    DEFAULT_FINAL_K: int = 10

    CRAWL_TIMEOUT: int = 10
    CRAWL_USER_AGENT: str = "PulseBot/1.0 (+https://pulse-search.com/bot)"
    CRAWL_MAX_REDIRECTS: int = 5

    SPACY_MODEL: str = "en_core_web_sm"
    PYMORPHY3_ENABLED: bool = True

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()

# --- ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ ---
engine = create_engine(
    settings.DATABASE_URL,
    pool_size=20,
    max_overflow=40,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=False
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# --- ИНИЦИАЛИЗАЦИЯ REDIS ---
try:
    redis_client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
    redis_client.ping()
    logger.info("✅ Redis подключен")
except Exception as e:
    logger.error(f"❌ Ошибка подключения к Redis: {e}")
    redis_client = None

# --- ИНИЦИАЛИЗАЦИЯ SBERT МОДЕЛИ (ГЛОБАЛЬНО) ---
try:
    sbert_model = SentenceTransformer(settings.SBERT_MODEL_NAME)
    logger.info(f"✅ SBERT модель загружена: {settings.SBERT_MODEL_NAME}")
except Exception as e:
    logger.error(f"❌ Ошибка загрузки SBERT модели: {e}")
    sbert_model = None

# --- ГЛОБАЛЬНЫЕ ПАРАМЕТРЫ ПОИСКА (ИНИЦИАЛИЗИРУЮТСЯ ПРИ СТАРТЕ) ---
GLOBAL_N_DOC = 0
GLOBAL_VOCABULARY_LIST = []
GLOBAL_VOCABULARY_TO_IDX = {}
GLOBAL_WORD_DOC_COUNTS = {}
GLOBAL_SEARCH_INITIALIZED = False


# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
from sqlalchemy import text  # <--- ДОБАВИТЬ ВВЕРХУ ФАЙЛА


def check_connections() -> Dict[str, bool]:
    status = {
        "database": False,
        "redis": False
    }

    # Проверка БД
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))  # <--- ИСПРАВЛЕНО
        db.close()
        status["database"] = True
    except Exception as e:
        logger.error(f"❌ Ошибка подключения к БД: {e}")

    # Проверка Redis
    if redis_client:
        try:
            redis_client.ping()
            status["redis"] = True
        except Exception:
            pass

    return status


def get_sbert_model():
    return sbert_model


def get_vector_size() -> int:
    return settings.SBERT_VECTOR_SIZE


# --- ФУНКЦИИ ДЛЯ РАБОТЫ С ЭМБЕДДИНГАМИ ---
def get_embedding(text: str, max_length: int = 1000) -> bytes:
    if not text or not isinstance(text, str) or sbert_model is None:
        return np.zeros(settings.SBERT_VECTOR_SIZE, dtype=np.float32).tobytes()

    if len(text) > max_length:
        text = text[:max_length]

    try:
        embedding = sbert_model.encode(text, convert_to_numpy=True)
        embedding = embedding.astype(np.float32)
        return embedding.tobytes()
    except Exception as e:
        logger.error(f"❌ Ошибка при генерации эмбеддинга: {e}")
        return np.zeros(settings.SBERT_VECTOR_SIZE, dtype=np.float32).tobytes()


def get_embeddings_batch(texts: list, max_length: int = 1000) -> list:
    if not texts or sbert_model is None:
        return [np.zeros(settings.SBERT_VECTOR_SIZE, dtype=np.float32).tobytes() for _ in texts]

    valid_texts = []
    for text in texts:
        if text and isinstance(text, str):
            if len(text) > max_length:
                text = text[:max_length]
            valid_texts.append(text)
        else:
            valid_texts.append("")

    try:
        embeddings = sbert_model.encode(valid_texts, convert_to_numpy=True)
        embeddings = embeddings.astype(np.float32)
        return [emb.tobytes() for emb in embeddings]
    except Exception as e:
        logger.error(f"❌ Ошибка при генерации эмбеддингов: {e}")
        return [np.zeros(settings.SBERT_VECTOR_SIZE, dtype=np.float32).tobytes() for _ in texts]


def bytes_to_array(embedding_bytes: bytes) -> np.ndarray:
    if not embedding_bytes:
        return np.zeros(settings.SBERT_VECTOR_SIZE, dtype=np.float32)
    try:
        arr = np.frombuffer(embedding_bytes, dtype=np.float32)
        if len(arr) != settings.SBERT_VECTOR_SIZE:
            logger.warning(f"Неверный размер эмбеддинга: {len(arr)}, ожидалось {settings.SBERT_VECTOR_SIZE}")
            return np.zeros(settings.SBERT_VECTOR_SIZE, dtype=np.float32)
        return arr
    except Exception as e:
        logger.error(f"❌ Ошибка при конвертации байтов в массив: {e}")
        return np.zeros(settings.SBERT_VECTOR_SIZE, dtype=np.float32)


def cosine_similarity_bytes(vec1_bytes: bytes, vec2_bytes: bytes) -> float:
    if not vec1_bytes or not vec2_bytes:
        return 0.0

    vec1 = bytes_to_array(vec1_bytes)
    vec2 = bytes_to_array(vec2_bytes)

    norm1 = np.linalg.norm(vec1)
    norm2 = np.linalg.norm(vec2)

    if norm1 == 0 or norm2 == 0:
        return 0.0

    return float(np.dot(vec1, vec2) / (norm1 * norm2))


def cosine_similarity_array(vec1: np.ndarray, vec2: np.ndarray) -> float:
    if vec1 is None or vec2 is None:
        return 0.0

    norm1 = np.linalg.norm(vec1)
    norm2 = np.linalg.norm(vec2)

    if norm1 == 0 or norm2 == 0:
        return 0.0

    return float(np.dot(vec1, vec2) / (norm1 * norm2))


def get_model_info() -> Dict[str, Any]:
    return {
        "model_name": settings.SBERT_MODEL_NAME,
        "vector_size": settings.SBERT_VECTOR_SIZE,
        "max_tokens": 256,
        "max_chars_approx": 1000,
        "is_loaded": sbert_model is not None
    }