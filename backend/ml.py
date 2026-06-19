def clean_html(html: str) -> str:
    return "cleaned text stub"

def tokenize_and_count(text: str) -> dict:
    return {"word": 1}

def calculate_tfidf(freq: int, total_words: int, total_pages: int, pages_with_word: int) -> float:
    return 0.85

def rank_results(raw_results: list, query: str) -> list:
    return sorted(raw_results, key=lambda x: x.get("score", 0), reverse=True)