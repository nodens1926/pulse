import re
import math
import numpy as np
from collections import Counter, defaultdict
from sentence_transformers import SentenceTransformer
import pymorphy3
import spacy
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker
from scipy.spatial.distance import cosine
from tqdm import tqdm
import logging

from models import Page, InvertedIndex
from database import SessionLocal

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Глобальные переменные для поиска
GLOBAL_SBERT_MODEL = None
GLOBAL_N_DOC = 0
GLOBAL_VOCABULARY = {}
GLOBAL_WORD_DOC_COUNTS = {}

# Загружаем NLP модели
morph = pymorphy3.MorphAnalyzer()
try:
    nlp_en = spacy.load('en_core_web_sm')
except OSError:
    logger.info("Загрузка модели spaCy...")
    spacy.cli.download('en_core_web_sm')
    nlp_en = spacy.load('en_core_web_sm')

def get_sbert_model():
    """Ленивая загрузка SBERT модели"""
    global GLOBAL_SBERT_MODEL
    if GLOBAL_SBERT_MODEL is None:
        logger.info("Загрузка SBERT модели...")
        GLOBAL_SBERT_MODEL = SentenceTransformer('all-MiniLM-L6-v2')
    return GLOBAL_SBERT_MODEL

def tokenize_text(text):
    """Токенизация текста (русский + английский)"""
    if not text:
        return []
    
    processed_tokens = []
    words = re.findall(r'\b\w+\b', text.lower())
    doc_en = nlp_en(" ".join(words))
    entities = {ent.text.lower() for ent in doc_en.ents}
    
    for token in doc_en:
        if token.text in entities:
            processed_tokens.append(token.text)
        elif re.fullmatch(r'[a-zA-Z]+', token.text):
            processed_tokens.append(token.lemma_)
        elif re.fullmatch(r'[а-яА-ЯёЁ]+', token.text):
            parsed = morph.parse(token.text)
            if parsed:
                processed_tokens.append(parsed[0].normal_form)
    
    return processed_tokens

def process_content(text):
    """Обработка контента страницы"""
    tokens = tokenize_text(text)
    return " ".join(tokens) if tokens else ""

def build_inverted_index(db, page_id, token_text):
    """Строит инвертированный индекс для страницы"""
    if not token_text:
        return []
    
    tokens = token_text.split()
    total = len(tokens)
    counts = Counter(tokens)
    
    entries = []
    for word, freq in counts.items():
        entries.append(InvertedIndex(
            word=word,
            page_id=page_id,
            frequency=freq,
            weight=freq / total  # TF
        ))
    return entries

def calculate_tfidf(db, batch_size=100):
    """Вычисляет TF-IDF для всех страниц"""
    # Получаем все страницы с токенами
    pages = db.query(Page).filter(Page.token_text.isnot(None)).all()
    n_doc = len(pages)
    
    if n_doc == 0:
        return
    
    # Строим словарь
    all_words = set()
    for page in pages:
        if page.token_text:
            all_words.update(page.token_text.split())
    
    vocab = {word: idx for idx, word in enumerate(sorted(all_words))}
    
    # Считаем документную частоту
    word_doc_counts = defaultdict(int)
    for page in pages:
        if page.token_text:
            words = set(page.token_text.split())
            for word in words:
                word_doc_counts[word] += 1
    
    # Вычисляем TF-IDF для каждой страницы
    for page in tqdm(pages, desc="TF-IDF"):
        if not page.token_text:
            continue
        
        tfidf_vector = np.zeros(len(vocab), dtype=np.float32)
        tokens = page.token_text.split()
        total = len(tokens)
        counts = Counter(tokens)
        
        for word, vocab_idx in vocab.items():
            tf = counts.get(word, 0) / total if total > 0 else 0
            n_cur = word_doc_counts.get(word, 0)
            idf = math.log(n_doc / n_cur) if n_cur > 0 else 0
            tfidf_vector[vocab_idx] = tf * idf
        
        page.tf_idf = tfidf_vector.tolist()
    
    db.commit()
    
    # Сохраняем глобальные параметры
    global GLOBAL_N_DOC, GLOBAL_VOCABULARY, GLOBAL_WORD_DOC_COUNTS
    GLOBAL_N_DOC = n_doc
    GLOBAL_VOCABULARY = vocab
    GLOBAL_WORD_DOC_COUNTS = dict(word_doc_counts)
    
    logger.info(f"TF-IDF рассчитан для {len(pages)} страниц, словарь: {len(vocab)} слов")

def search(query, db, limit=10):
    """Поиск по запросу"""
    # Инициализация глобальных параметров если нужно
    if not GLOBAL_VOCABULARY:
        calculate_tfidf(db)
    
    # Токенизация запроса
    query_tokens = tokenize_text(query)
    if not query_tokens:
        return []
    
    # TF-IDF вектора запроса
    query_vector = np.zeros(len(GLOBAL_VOCABULARY), dtype=np.float32)
    counts = Counter(query_tokens)
    total = len(query_tokens)
    
    for word, vocab_idx in GLOBAL_VOCABULARY.items():
        tf = counts.get(word, 0) / total
        n_cur = GLOBAL_WORD_DOC_COUNTS.get(word, 0)
        idf = math.log(GLOBAL_N_DOC / n_cur) if n_cur > 0 else 0
        query_vector[vocab_idx] = tf * idf
    
    # Поиск похожих страниц по TF-IDF
    pages = db.query(Page).filter(Page.tf_idf.isnot(None)).all()
    
    scores = []
    for page in pages:
        page_vector = np.array(page.tf_idf, dtype=np.float32)
        similarity = 1 - cosine(query_vector, page_vector)
        scores.append((similarity, page.id))
    
    scores.sort(reverse=True, key=lambda x: x[0])
    top_ids = [page_id for _, page_id in scores[:limit]]
    
    # Доражирование SBERT
    if top_ids:
        sbert_model = get_sbert_model()
        query_embedding = sbert_model.encode(query)
        
        sbert_scores = []
        for page_id in top_ids:
            page = db.query(Page).filter(Page.id == page_id).first()
            if page and page.embedding:
                page_embedding = np.frombuffer(page.embedding, dtype=np.float32)
                similarity = 1 - cosine(query_embedding, page_embedding)
                sbert_scores.append((similarity, page_id))
            else:
                sbert_scores.append((0, page_id))
        
        sbert_scores.sort(reverse=True, key=lambda x: x[0])
        final_ids = [page_id for _, page_id in sbert_scores]
        
        # Обновляем релевантность
        for idx, (score, page_id) in enumerate(sbert_scores):
            page = db.query(Page).filter(Page.id == page_id).first()
            if page:
                page.relevantnost = score
        db.commit()
        
        return final_ids
    
    return top_ids

def compute_embeddings(db, batch_size=50):
    """Вычисляет SBERT эмбеддинги для всех страниц"""
    pages = db.query(Page).filter(
        Page.content.isnot(None),
        Page.content != '',
        Page.embedding.is_(None)
    ).all()
    
    if not pages:
        return
    
    model = get_sbert_model()
    
    for i in tqdm(range(0, len(pages), batch_size), desc="SBERT эмбеддинги"):
        batch = pages[i:i+batch_size]
        texts = [p.content for p in batch]
        embeddings = model.encode(texts)
        
        for page, embedding in zip(batch, embeddings):
            page.embedding = embedding.tobytes()
        
        db.commit()
    
    logger.info(f"Вычислено {len(pages)} эмбеддингов")
