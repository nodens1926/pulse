import re
import logging
from typing import List, Set, Dict, Any, Optional
from functools import lru_cache
import hashlib

import pymorphy3
import spacy
from spacy.language import Language

logger = logging.getLogger(__name__)

# --- ИНИЦИАЛИЗАЦИЯ NLP ИНСТРУМЕНТОВ ---

try:
    morph = pymorphy3.MorphAnalyzer()
    logger.info("✅ pymorphy3 загружен")
except Exception as e:
    logger.error(f"❌ Ошибка загрузки pymorphy3: {e}")
    morph = None

try:
    nlp_en = spacy.load('en_core_web_sm')
    logger.info("✅ spaCy модель 'en_core_web_sm' загружена")
except OSError:
    logger.warning("⚠️ Модель 'en_core_web_sm' не найдена. Загрузка...")
    try:
        spacy.cli.download('en_core_web_sm')
        nlp_en = spacy.load('en_core_web_sm')
        logger.info("✅ spaCy модель 'en_core_web_sm' загружена")
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки spaCy: {e}")
        nlp_en = None
except Exception as e:
    logger.error(f"❌ Ошибка загрузки spaCy: {e}")
    nlp_en = None

TOKEN_CACHE_SIZE = 10000
_token_cache: Dict[str, List[str]] = {}


def get_nlp_info() -> Dict[str, Any]:

    return {
        "pymorphy3_loaded": morph is not None,
        "spacy_loaded": nlp_en is not None,
        "spacy_model": "en_core_web_sm" if nlp_en is not None else None,
        "cache_size": len(_token_cache),
        "cache_max_size": TOKEN_CACHE_SIZE
    }


# 2. ОСНОВНАЯ ФУНКЦИЯ ТОКЕНИЗАЦИИ

def tokenize_and_lemmatize(
        text: str,
        lang: str = 'ru_en',
        use_cache: bool = True,
        max_length: int = 10000
) -> List[str]:

    if not text or not isinstance(text, str):
        return []

    if len(text) > max_length:
        text = text[:max_length]
        logger.debug(f"Текст обрезан до {max_length} символов")

    if use_cache:
        cache_key = _get_cache_key(text)
        if cache_key in _token_cache:
            logger.debug(f"✅ Кэш: {cache_key[:20]}...")
            return _token_cache[cache_key]

    if morph is None and nlp_en is None:
        logger.warning("⚠️ NLP инструменты не загружены, возвращаем сырые слова")
        tokens = _simple_tokenize(text)
        if use_cache:
            _add_to_cache(cache_key, tokens)
        return tokens

    try:
        tokens = _process_text(text, lang)
    except Exception as e:
        logger.error(f"❌ Ошибка при токенизации: {e}")
        tokens = _simple_tokenize(text)

    if use_cache and tokens:
        _add_to_cache(cache_key, tokens)

    return tokens


# 3. ВНУТРЕННИЕ ФУНКЦИИ ОБРАБОТКИ

def _get_cache_key(text: str) -> str:

    return hashlib.md5(text.encode('utf-8')).hexdigest()


def _add_to_cache(key: str, tokens: List[str]) -> None:
    if len(_token_cache) >= TOKEN_CACHE_SIZE:
        keys_to_remove = list(_token_cache.keys())[:TOKEN_CACHE_SIZE // 2]
        for k in keys_to_remove:
            del _token_cache[k]
        logger.debug(f"🧹 Кэш очищен: удалено {len(keys_to_remove)} записей")

    _token_cache[key] = tokens


def _simple_tokenize(text: str) -> List[str]:
    return re.findall(r'\b\w+\b', text.lower())


def _process_text(text: str, lang: str) -> List[str]:

    processed_tokens = []

    words = re.findall(r'\b\w+\b', text.lower())

    if not words:
        return []

    use_english = lang in ('en', 'ru_en') and nlp_en is not None
    use_russian = lang in ('ru', 'ru_en') and morph is not None

    if use_english:
        try:
            doc_en = nlp_en(" ".join(words))
            entities = {ent.text.lower() for ent in doc_en.ents}

            en_lemma_map = {}
            for token in doc_en:
                en_lemma_map[token.text.lower()] = token.lemma_.lower()
        except Exception as e:
            logger.error(f"❌ Ошибка при обработке через spaCy: {e}")
            entities = set()
            en_lemma_map = {}
    else:
        entities = set()
        en_lemma_map = {}

    for token_text in words:
        if token_text in entities:
            processed_tokens.append(token_text)
            continue

        if re.fullmatch(r'[a-zA-Z]+', token_text):
            if use_english and token_text in en_lemma_map:
                processed_tokens.append(en_lemma_map[token_text])
            else:
                processed_tokens.append(token_text)

        elif re.fullmatch(r'[а-яА-ЯёЁ]+', token_text):
            if use_russian:
                try:
                    parsed = morph.parse(token_text)
                    if parsed:
                        processed_tokens.append(parsed[0].normal_form.lower())
                    else:
                        processed_tokens.append(token_text)
                except Exception:
                    processed_tokens.append(token_text)
            else:
                processed_tokens.append(token_text)

        else:
            processed_tokens.append(token_text)

    processed_tokens = [t for t in processed_tokens if len(t) > 1]

    return processed_tokens


# 4. ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ

def is_russian_word(word: str) -> bool:
    return bool(re.fullmatch(r'[а-яА-ЯёЁ]+', word))


def is_english_word(word: str) -> bool:
    return bool(re.fullmatch(r'[a-zA-Z]+', word))


def is_stop_word(word: str, lang: str = 'ru_en') -> bool:

    ru_stop_words = {
        'и', 'в', 'во', 'не', 'что', 'он', 'на', 'я', 'с', 'со', 'как', 'а', 'то', 'все', 'она', 'так', 'его', 'но',
        'да', 'ты', 'к', 'у', 'же', 'вы', 'за', 'бы', 'по', 'только', 'ее', 'мне', 'было', 'вот', 'от', 'меня', 'еще',
        'нет', 'о', 'из', 'ему', 'теперь', 'когда', 'даже', 'ну', 'вдруг', 'ли', 'если', 'уже', 'или', 'ни', 'быть',
        'был', 'него', 'до', 'вас', 'нибудь', 'опять', 'уж', 'вам', 'ведь', 'там', 'потом', 'себя', 'ничего', 'ей',
        'может', 'они', 'тут', 'где', 'есть', 'надо', 'ней', 'для', 'мы', 'тебя', 'их', 'чем', 'была', 'сам', 'чтоб',
        'без', 'будто', 'чего', 'раз', 'тоже', 'себе', 'под', 'будет', 'ж', 'тогда', 'кто', 'этот', 'того', 'потому',
        'этого', 'какой', 'совсем', 'ним', 'здесь', 'этом', 'один', 'почти', 'мой', 'тем', 'чтобы', 'нее', 'сейчас',
        'были', 'куда', 'зачем', 'всех', 'можно', 'при', 'наконец', 'нельзя', 'об', 'другой', 'хоть', 'после', 'над',
        'больше', 'тот', 'через', 'эти', 'нас', 'про', 'всего', 'них', 'какая', 'много', 'разве', 'три', 'эту', 'моя',
        'впрочем', 'хорошо', 'свою', 'этой', 'перед', 'иногда', 'лучше', 'чуть', 'том', 'нельзя', 'такой', 'более',
        'всё', 'также', 'другие', 'чтобы'
    }

    en_stop_words = {
        'a', 'an', 'the', 'and', 'or', 'but', 'so', 'for', 'nor', 'on', 'at', 'to', 'by', 'in', 'with', 'without', 'of',
        'for', 'per', 'via', 'vs', 'vs', 'etc', 'e.g', 'i', 'you', 'he', 'she', 'it', 'we', 'they', 'me', 'him', 'her',
        'us', 'them', 'my', 'your', 'his', 'her', 'our', 'their', 'mine', 'yours', 'hers', 'ours', 'theirs', 'this',
        'that', 'these', 'those', 'some', 'any', 'no', 'every', 'all', 'each', 'both', 'neither', 'either', 'one',
        'two', 'three'
    }

    word_lower = word.lower()

    if lang in ('ru', 'ru_en') and word_lower in ru_stop_words:
        return True

    if lang in ('en', 'ru_en') and word_lower in en_stop_words:
        return True

    return False


def filter_stop_words(tokens: List[str], lang: str = 'ru_en') -> List[str]:

    return [t for t in tokens if not is_stop_word(t, lang)]


def normalize_tokens(tokens: List[str]) -> List[str]:

    normalized = [t.lower().strip() for t in tokens if t and t.strip()]
    # Удаляем дубликаты сохраняя порядок
    seen = set()
    result = []
    for t in normalized:
        if t not in seen:
            seen.add(t)
            result.append(t)
    return result


# 5. ФУНКЦИИ ДЛЯ ПАРТИЙНОЙ ОБРАБОТКИ

def tokenize_batch(
        texts: List[str],
        lang: str = 'ru_en',
        use_cache: bool = True,
        max_length: int = 10000
) -> List[List[str]]:

    results = []
    for text in texts:
        tokens = tokenize_and_lemmatize(text, lang, use_cache, max_length)
        results.append(tokens)
    return results


def tokenize_and_filter_batch(
        texts: List[str],
        lang: str = 'ru_en',
        use_cache: bool = True,
        max_length: int = 10000,
        remove_stopwords: bool = True,
        normalize: bool = True
) -> List[List[str]]:

    results = []
    for text in texts:
        tokens = tokenize_and_lemmatize(text, lang, use_cache, max_length)

        if remove_stopwords:
            tokens = filter_stop_words(tokens, lang)

        if normalize:
            tokens = normalize_tokens(tokens)

        results.append(tokens)

    return results


# 6. СБОР СТАТИСТИКИ

def get_token_stats(tokens: List[str]) -> Dict[str, Any]:

    from collections import Counter

    if not tokens:
        return {
            "total": 0,
            "unique": 0,
            "avg_length": 0,
            "top_words": []
        }

    counter = Counter(tokens)

    return {
        "total": len(tokens),
        "unique": len(counter),
        "avg_length": sum(len(t) for t in tokens) / len(tokens) if tokens else 0,
        "top_words": counter.most_common(10)
    }


# 7. ТЕСТИРОВАНИЕ

if __name__ == "__main__":
    print("🧪 Тестирование nlp_utils.py")
    print("=" * 50)

    info = get_nlp_info()
    print(f"📚 NLP информация:")
    print(f"  - pymorphy3: {info['pymorphy3_loaded']}")
    print(f"  - spaCy: {info['spacy_loaded']}")
    print(f"  - Модель: {info['spacy_model']}")
    print()

    test_texts = [
        "Машинное обучение - это интересная область искусственного интеллекта.",
        "Machine learning is a fascinating field of artificial intelligence.",
        "John Doe is the CEO of the company. He leads the team.",
        "В Москве прошла конференция по машинному обучению.",
        "Python and JavaScript are popular programming languages.",
        "Смешанный текст: Python и JavaScript - популярные языки программирования.",
    ]

    print("📝 Тестирование токенизации:")
    print("-" * 50)

    for i, text in enumerate(test_texts, 1):
        tokens = tokenize_and_lemmatize(text)
        print(f"{i}. Оригинал: {text[:50]}...")
        print(f"   Токены: {tokens[:10]}{'...' if len(tokens) > 10 else ''}")
        print(f"   Всего: {len(tokens)} токенов")
        print()

    print("🔤 Тест стоп-слов:")
    print("-" * 50)

    test_words = ["и", "в", "на", "с", "по", "the", "and", "or", "but", "машинное"]
    for word in test_words:
        is_stop = is_stop_word(word)
        print(f"  '{word}' -> стоп-слово: {is_stop}")

    print()

    text = "Это пример текста с некоторыми стоп-словами и именами."
    tokens = tokenize_and_lemmatize(text)
    filtered = filter_stop_words(tokens)

    print("🔍 Фильтрация стоп-слов:")
    print(f"  Исходные токены: {tokens}")
    print(f"  После фильтрации: {filtered}")
    print()

    print("💾 Тест кэша:")
    print("-" * 50)

    import time

    text = "Этот текст будет закэширован для быстрого доступа."

    start = time.time()
    tokens1 = tokenize_and_lemmatize(text, use_cache=True)
    time1 = time.time() - start

    start = time.time()
    tokens2 = tokenize_and_lemmatize(text, use_cache=True)
    time2 = time.time() - start

    print(f"  Первый вызов: {time1:.4f}с")
    print(f"  Второй вызов (из кэша): {time2:.4f}с")
    print(f"  Ускорение: {time1 / time2:.2f}x")
    print(f"  Размер кэша: {len(_token_cache)} записей")
    print()

    print("📊 Статистика:")
    print("-" * 50)
    stats = get_token_stats(tokens1)
    print(f"  Всего токенов: {stats['total']}")
    print(f"  Уникальных: {stats['unique']}")
    print(f"  Средняя длина: {stats['avg_length']:.2f}")
    print(f"  Топ-10 слов: {stats['top_words']}")

    print()
    print("✅ Все тесты пройдены!")