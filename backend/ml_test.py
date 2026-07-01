# test_ml.py
import pytest
import numpy as np
from unittest.mock import Mock, patch, MagicMock
from collections import Counter
from ml import (
    tokenize_text, process_content, build_inverted_index,
    calculate_tfidf, search, compute_embeddings, get_sbert_model
)
from models import Page, InvertedIndex

class TestML:
    def test_tokenize_text_empty(self):
        """Проверка токенизации пустого текста"""
        assert tokenize_text("") == []
        assert tokenize_text(None) == []

    def test_tokenize_text_english(self):
        """Проверка токенизации английского текста"""
        tokens = tokenize_text("Hello world, this is a test")
        assert len(tokens) > 0
        assert "hello" in tokens

    def test_tokenize_text_russian(self):
        """Проверка токенизации русского текста"""
        tokens = tokenize_text("Привет мир, это тест")
        assert len(tokens) > 0

    def test_tokenize_text_mixed(self):
        """Проверка токенизации смешанного текста"""
        tokens = tokenize_text("Hello мир, test тест")
        assert len(tokens) > 0

    def test_process_content(self):
        """Проверка обработки контента"""
        text = "Hello world! This is a test."
        processed = process_content(text)
        assert isinstance(processed, str)
        assert len(processed) > 0

    def test_process_content_empty(self):
        """Проверка обработки пустого контента"""
        assert process_content("") == ""
        assert process_content(None) == ""

    def test_build_inverted_index(self):
        """Проверка построения инвертированного индекса"""
        db = Mock()
        entries = build_inverted_index(db, 1, "hello world hello test")
        assert len(entries) > 0
        assert all(isinstance(e, InvertedIndex) for e in entries)
        
        # Проверка весов
        hello_entry = next(e for e in entries if e.word == "hello")
        assert hello_entry.frequency == 2
        assert hello_entry.weight == 2/4  # 2/4 = 0.5

    def test_build_inverted_index_empty(self):
        """Проверка построения индекса из пустого текста"""
        db = Mock()
        entries = build_inverted_index(db, 1, "")
        assert entries == []

    def test_get_sbert_model(self):
        """Проверка ленивой загрузки SBERT модели"""
        with patch('ml.SentenceTransformer') as mock_model:
            model = get_sbert_model()
            mock_model.assert_called_with('all-MiniLM-L6-v2')
            assert model is not None

    def test_calculate_tfidf_no_pages(self):
        """Проверка TF-IDF без страниц"""
        db = Mock()
        db.query().filter().all.return_value = []
        calculate_tfidf(db)
        # Не должно быть ошибок

    @patch('ml.GLOBAL_VOCABULARY', {})
    @patch('ml.GLOBAL_WORD_DOC_COUNTS', {})
    @patch('ml.GLOBAL_N_DOC', 0)
    def test_search_empty_query(self):
        """Проверка поиска с пустым запросом"""
        db = Mock()
        result = search("", db)
        assert result == []

    @patch('ml.get_sbert_model')
    @patch('ml.calculate_tfidf')
    def test_search_with_results(self, mock_calc, mock_sbert):
        """Проверка поиска с результатами"""
        db = Mock()
        page = Mock()
        page.id = 1
        page.tf_idf = [0.1, 0.2, 0.3]
        page.embedding = np.array([0.1, 0.2, 0.3]).tobytes()
        
        db.query().filter().all.return_value = [page]
        db.query().filter().first.return_value = page
        
        mock_model = Mock()
        mock_model.encode.return_value = np.array([0.1, 0.2, 0.3])
        mock_sbert.return_value = mock_model
        
        with patch('ml.tokenize_text', return_value=["test", "query"]):
            with patch('ml.GLOBAL_VOCABULARY', {"test": 0, "query": 1}):
                with patch('ml.GLOBAL_WORD_DOC_COUNTS', {"test": 1, "query": 1}):
                    with patch('ml.GLOBAL_N_DOC', 1):
                        result = search("test query", db)
                        assert len(result) > 0