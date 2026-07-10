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
from scipy.sparse import csr_matrix
from sklearn.metrics.pairwise import cosine_similarity
from tqdm import tqdm
import logging
from typing import Dict, List, Tuple

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



def search(query, db, limit=10, tfidf_threshold=0.1, sbert_min_score=0.3):
    """Поиск по запросу с 3 сценариями ранжирования: 
    1) Еслм ни одного токена текста запроса нет в нашем словаре, т.е. tf-idf-вектор запроса будет состоять из нулей. 
       В этом случае tf-idf-фильтрация будет неинформативной и мы её скипаем.   
    2) Если часть токенов текста запроса есть в словаре, а части токенов текста запроса в словаре нет. 
       Мы ребём результат ранжирование tf-idf'ом с весом 0.3, и результат ранжирования сбертом с весом 0.7. 
       Почему вовсе не убираем tf-idf? Чтобы подтащить наверх страницы с ключевыми словами! 
       Потому что SBERT ловит смысл и синонимы, но нет гарантии, что страницы с попаданием по ключевым словам попадут в топ.
    3) Если все токены запроса есть в словаре, то сначала ранжируем tf-idf'ом, а потом доранжируем сбертом. 
       Здесь в tf-idf возможны 2 сценария (выбираем сами при запуске): 
       *добавлен tfidf_threshold = 0.1 - это порог релевантности tf-idf'ом. 
    """

    #Инициализация глобальных параметров, если забыли инициализировать ранее: 
    if not GLOBAL_VOCABULARY:
        calculate_tfidf(db)

    #Токенизация запроса: 
    query_tokens = tokenize_text(query)
    if not query_tokens:
        return []
    
    #Построение TF‑IDF вектора запроса: 
    query_vector = np.zeros(len(GLOBAL_VOCABULARY), dtype=np.float32)
    counts = Counter(query_tokens)
    total = len(query_tokens)
    
    for word, vocab_idx in GLOBAL_VOCABULARY.items():
        tf = counts.get(word, 0) / total
        n_cur = GLOBAL_WORD_DOC_COUNTS.get(word, 0)
        idf = math.log(GLOBAL_N_DOC / n_cur) if n_cur > 0 else 0
        query_vector[vocab_idx] = tf * idf
    
    #Определяем, какие токены отсутствуют в словаре: 
    missing_tokens = [t for t in query_tokens if t not in GLOBAL_VOCABULARY]
    #Флаг, что есть слова не из словаря: 
    has_missing = len(missing_tokens) > 0
    #Флаг, что в тексте запроса нет слов из словаря, т.е. вектор tf-idf запроса состоит из нулей: 
    is_zero_vector = np.all(query_vector == 0)
    
    pages = db.query(Page).filter(Page.tf_idf.isnot(None)).all()
    if not pages:
        return []

    page_ids = [p.id for p in pages]
    
    #Вспомогательная функция для расчёта TF‑IDF схожести: 
    def calc_tfidf_similarities(q_vec, page_list):
        sims = []
        q_norm = np.linalg.norm(q_vec)
        for page in page_list:
            p_vec = np.array(page.tf_idf, dtype=np.float32)
            p_norm = np.linalg.norm(p_vec)
            if q_norm == 0 or p_norm == 0:
                sim = 0.0
            else:
                sim = 1 - cosine(q_vec, p_vec)
            sims.append((sim, page.id))
        return sims
    
    candidate_ids = []
    tfidf_scores = []
    
    #Сценарий 1: вектор TF‑IDF состоит только из нулей --> сразу все кандидаты (без порога)
    if is_zero_vector:
        candidate_ids = page_ids[:]  #все страницы с tf_idf
    
    else:
        #Считаем TF‑IDF схожесть один раз для всех страниц: 
        tfidf_scores = calc_tfidf_similarities(query_vector, pages)
        
        #Сценарий 2: не все токены в словаре --> смешанное взвешивание (берём всех для весов): 
        if has_missing:
            #Для взвешивания нужны оценки по всем кандидатам, поэтому берём все страницы: 
            candidate_ids = page_ids[:]
        
        #Сценарий 3: все токены есть в словаре --> отбор по порогу + добивка до limit. 
        #Иногда порог релевантности 0.1 отсекает почти всё, SBERT'ом можно найти синонимы. 
        #Добивка позволяет вернуть хоть какие‑то дополнительные страницы, даже если их TF‑IDF‑оценка ниже порога.
        else:
            filtered = [(s, pid) for s, pid in tfidf_scores if s > tfidf_threshold]
            if len(filtered) < limit:
                remaining = [(s, pid) for s, pid in tfidf_scores if s <= tfidf_threshold]
                remaining.sort(reverse=True, key=lambda x: x[0])
                needed = limit - len(filtered)
                filtered += remaining[:needed]
            candidate_ids = [pid for _, pid in filtered[:limit]]
    
    if not candidate_ids:
        return []
    
    #Загрузка страниц одним запросом (оптимизация SQLAlchemy): 
    pages_by_id = {p.id: p for p in db.query(Page).filter(Page.id.in_(candidate_ids)).all()}
    
    #Доранжирование через SBERT
    sbert_model = get_sbert_model()
    query_embedding = sbert_model.encode(query)
    q_emb_norm = np.linalg.norm(query_embedding)
    
    sbert_scores = []
    for page_id in candidate_ids:
        page = pages_by_id.get(page_id)
        if page and page.embedding:
            page_embedding = np.frombuffer(page.embedding, dtype=np.float32)
            p_emb_norm = np.linalg.norm(page_embedding)
            if q_emb_norm == 0 or p_emb_norm == 0:
                sim = 0.0
            else:
                sim = 1 - cosine(query_embedding, page_embedding)
            sbert_scores.append((sim, page_id))
        else:
            sbert_scores.append((0.0, page_id))
    
    #Если сработал сценарий 2 (не все токены в словаре), применяем веса:
    if not is_zero_vector and has_missing:
        tf_map = {pid: score for score, pid in tfidf_scores}
        weighted_scores = []
        for sbert_sim, page_id in sbert_scores:
            tf_sim = tf_map.get(page_id, 0.0)
            final_score = 0.3 * tf_sim + 0.7 * sbert_sim
            weighted_scores.append((final_score, page_id))
        sbert_scores = weighted_scores
    
    #Финальная сортировка: 
    #Оставляем только кандидатов с score >= порога
    filtered_sbert = [(score, page_id) for score, page_id in sbert_scores if score >= sbert_min_score]
    #Сортируем отфильтрованных кандидатов по убыванию score
    filtered_sbert.sort(reverse=True, key=lambda x: x[0])
    final_ids = [page_id for _, page_id in filtered_sbert[:20]]
    
    #Сохранение оценок релевантности в БД
    for score, page_id in filtered_sbert:
        page = pages_by_id.get(page_id)
        if page:
            page.relevantnost = score
    db.commit()
    
    return final_ids





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


# ============================================================
# ФУНКЦИЯ ДЛЯ ПОИСКА ПОХОЖИХ СТРАНИЦ
# ============================================================

def find_similar_pages(db_url: str, ranked_page_ids: List[int], top_n_per_page: int = 10, use_tfidf_stage: bool = True) -> Dict[int, List[int]]:
    """
    Входные параметры:
      db_url - строка подключения к PostgreSQL;
      ranked_page_ids - список айдишников страниц;
      top_n_per_page - количество похожих страниц, которые надо вывести;
      use_tfidf_stage - переключатель режимов (True or False):
        1 режим: Если use_tfidf_stage == True: пайплайн TF-IDF (топ‑50 кандидатов) + SBERT (доранжирование).
        2 режим: Если use_tfidf_stage == False: сразу SBERT по всем документам.
    Выходные параметры:
      словарь, в котором ключи - page_ids из списка ranked_page_ids, а значения - список индексов похожих страниц, т.е.
      dict: { page_id: [список похожих page_id] }
    Что делает функция?
      Для каждого page_id из ranked_page_ids находит top_n_per_page похожих страниц.
    """

    # Инициализируем SBERT модель если нужно
    if GLOBAL_SBERT_MODEL is None:
        logger.info("SBERT модель не инициализирована, инициализируем...")
        get_sbert_model()

    # Если используем TF-IDF, проверяем и инициализируем глобальные параметры
    if use_tfidf_stage and (not GLOBAL_VOCABULARY or GLOBAL_N_DOC == 0):
        logger.info("Глобальные параметры TF-IDF не инициализированы, инициализируем...")
        engine = create_engine(db_url)
        Session = sessionmaker(bind=engine)
        session = Session()
        try:
            calculate_tfidf(session)
        finally:
            session.close()

    # С помощью функции SQLAlchemy создаём движок engine для подключения к БД:
    engine = create_engine(db_url)
    # Создаём класс Session для создания сессий, которые будут привязаны к движку engine:
    Session = sessionmaker(bind=engine)
    # Получаем экземпляр сессии:
    session = Session()

    # Загружаем из БД эмбеддинги текстов, построенные с помощью SBERT (нужно в обоих режимах):
    emb_rows = session.query(Page.id, Page.embedding).filter(Page.embedding.isnot(None)).all()
    # Закрываем сессию:
    session.close()

    # Если в БД нет эмбедингов, выводим пустые списки для каждой страницы в результате функции
    # (вообще эту проверку можно удалить):
    if len(emb_rows) == 0:
        return {pid: [] for pid in ranked_page_ids}

    # Создаём таблицы соответствия.
    # page_id --> индекс в матрице (чтобы быстро найти вектор нужной страницы):
    emb_id_to_idx = {pid: i for i, (pid, _) in enumerate(emb_rows)}
    # индекс в матрице --> page_id (чтобы после вычислений вернуть обратно понятные ID страниц):
    emb_idx_to_id = {i: pid for i, (pid, _) in enumerate(emb_rows)}

    emb_dim = 384
    # Создаётся матрица эмбеддингов SBERT'а размера [N_страниц × 384]:
    emb_matrix = np.zeros((len(emb_rows), emb_dim), dtype=np.float32)
    # Заполняем матрицу значениями, переводя байты в вещественные числа:
    for i, (_, emb_bytes) in enumerate(emb_rows):
        emb_matrix[i] = np.frombuffer(emb_bytes, dtype=np.float32)
        # Для схожести достаточно float32.

    # Нормализация строк матрицы.
    # Зачем? Чтобы после нормализации скалярное произведение двух векторов стало равно их косинусному сходству:
    # Считаем длины каждого вектора:
    norms = np.linalg.norm(emb_matrix, axis=1, keepdims=True)
    # Замена нулевых норм на 1.0 нужна, чтобы не получить деление на ноль, если вдруг встретится нулевой вектор:
    norms[norms == 0] = 1.0
    # Деление на длину делает все векторы единичной длины:
    emb_matrix /= norms

    # Создаём результирующий словарь:
    results: Dict[int, List[int]] = {}

    if use_tfidf_stage:
        # Режим с TF‑IDF этапом.
        # Проверяем ещё раз (на случай если calculate_tfidf не сработал)
        if not GLOBAL_VOCABULARY or GLOBAL_N_DOC == 0:
            raise ValueError("Глобальные параметры TF‑IDF не инициализированы. Вызовите функцию calculate_tfidf().")

        # Создаём новую сессию для выгрузки TF-IDF
        session = Session()
        # Выгружаем из БД страницы, у которых есть tf-idf-вектор:
        rows = session.query(Page.id, Page.tf_idf).filter(Page.tf_idf.isnot(None)).all()
        session.close()

        if len(rows) == 0:
            return {pid: [] for pid in ranked_page_ids}

        id_to_idx = {pid: i for i, (pid, _) in enumerate(rows)}
        idx_to_id = {i: pid for i, (pid, _) in enumerate(rows)}

        # Инициализируем переменные:
        data, row_indices, col_indices = [], [], []  # значения, индексы строк, индексы колонок
        vocab_size = len(GLOBAL_VOCABULARY)
        # Из векторов TF‑IDF строим разреженную матрицу csr_matrix:
        for i, (_, vec_list) in enumerate(rows):
            if vec_list:
                for vocab_idx, value in enumerate(vec_list):
                    if value != 0.0:
                        data.append(value)
                        row_indices.append(i)
                        col_indices.append(vocab_idx)
        # Заполняем разреженную матрицу:
        tfidf_matrix = csr_matrix((data, (row_indices, col_indices)), shape=(len(rows), vocab_size))

        # Для каждой страницы ищем похожие страницы через TF‑IDF:
        for page_id in tqdm(ranked_page_ids, desc="TF‑IDF --> SBERT поиск"):
            # Если нет векторов tf-idf, возвращаем пустые списки словаря:
            if page_id not in id_to_idx:
                results[page_id] = []
                continue

            # Через словарь id_to_idx[page_id] находим индекс (номер строки) в матрице, соответствующий page_id текущей страницы:
            q_tfidf_row = id_to_idx[page_id]
            # Вытаскиваем из разреженной матрицы tf-idf строку, соответствующую индексу q_tfidf_row (берём срез из таблицы):
            query_tfidf = tfidf_matrix[q_tfidf_row:q_tfidf_row + 1]
            # Вычисляем косинусное сходство текущей страницы со всеми страницами:
            sims_tfidf = cosine_similarity(query_tfidf, tfidf_matrix).ravel()
            # Косинусное сходство с самим собой обозначаем -1:
            sims_tfidf[q_tfidf_row] = -1.0

            # Берём либо топ-50, либо столько, сколько есть страниц:
            k_tfidf = min(50, len(sims_tfidf))
            if k_tfidf > 0:
                # argpartition требует kth < len(array)
                kth_param = min(k_tfidf - 1, len(sims_tfidf) - 1)
                top_k_idx = np.argpartition(-sims_tfidf, kth_param)[:k_tfidf]
                top_k_scores = sims_tfidf[top_k_idx]
                order = np.argsort(-top_k_scores)
                top_k_idx = top_k_idx[order]
                candidate_ids = [idx_to_id[i] for i in top_k_idx]
            else:
                candidate_ids = []

            # SBERT доранжирование кандидатов
            cand_emb_indices = [emb_id_to_idx[pid] for pid in candidate_ids if pid in emb_id_to_idx]
            if len(cand_emb_indices) == 0 or page_id not in emb_id_to_idx:
                # Если нет эмбеддингов — возвращаем топ по TF‑IDF:
                results[page_id] = candidate_ids[:top_n_per_page]
                continue

            # Вырезаем подматрицу эмбеддингов для отобранных индексов страниц после tf-idf:
            cand_emb_sub = emb_matrix[cand_emb_indices]
            # вектор-эмбеддинг SBERT'а для текущей страницы:
            q_emb = emb_matrix[emb_id_to_idx[page_id]].reshape(1, -1)
            # Считаем косинусные сходства текущей страницы с остальными из отобранных через скалярное произведение:
            sims_sbert = (q_emb @ cand_emb_sub.T).ravel()

            # Отбираем топ-N индексов страниц по релевантности относительно текущей страницы:
            k_sbert = min(top_n_per_page, len(sims_sbert))
            if k_sbert > 0:
                kth_param = min(k_sbert - 1, len(sims_sbert) - 1)
                final_top_idx = np.argpartition(-sims_sbert, kth_param)[:k_sbert]
                final_order = np.argsort(-sims_sbert[final_top_idx])
                final_top_idx = final_top_idx[final_order]
                results[page_id] = [candidate_ids[i] for i in final_top_idx]
            else:
                results[page_id] = []

    else:
        # Режим только SBERT.
        for page_id in tqdm(ranked_page_ids, desc="только SBERT поиск"):
            if page_id not in emb_id_to_idx:
                results[page_id] = []
                continue

            q_emb = emb_matrix[emb_id_to_idx[page_id]].reshape(1, -1)
            sims = (q_emb @ emb_matrix.T).ravel()
            sims[emb_id_to_idx[page_id]] = -1.0

            k = min(top_n_per_page, len(sims))
            if k > 0:
                kth_param = min(k - 1, len(sims) - 1)
                top_idx = np.argpartition(-sims, kth_param)[:k]
                order = np.argsort(-sims[top_idx])
                final_ids = [emb_idx_to_id[i] for i in top_idx[order]]
            else:
                final_ids = []
            results[page_id] = final_ids

    return results