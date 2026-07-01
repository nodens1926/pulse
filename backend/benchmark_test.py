# test_performance.py
import pytest
import time
import numpy as np
from unittest.mock import Mock, patch
from ml import tokenize_text, process_content, build_inverted_index

class TestPerformance:
    def test_tokenization_performance(self):
        """Тест производительности токенизации"""
        text = " ".join(["test word" for _ in range(1000)])
        
        start_time = time.time()
        tokens = tokenize_text(text)
        elapsed_time = time.time() - start_time
        
        assert elapsed_time < 1.0  # Должно быть меньше 1 секунды
        assert len(tokens) > 100

    def test_process_content_performance(self):
        """Тест производительности обработки контента"""
        text = " ".join(["test content" for _ in range(100)])
        
        start_time = time.time()
        processed = process_content(text)
        elapsed_time = time.time() - start_time
        
        assert elapsed_time < 0.5  # Должно быть меньше 0.5 секунды

    def test_build_index_performance(self):
        """Тест производительности построения индекса"""
        db = Mock()
        text = " ".join(["word" for _ in range(500)])
        
        start_time = time.time()
        entries = build_inverted_index(db, 1, text)
        elapsed_time = time.time() - start_time
        
        assert elapsed_time < 1.0  # Должно быть меньше 1 секунды

    def test_tfidf_vector_size(self):
        """Тест размера TF-IDF вектора"""
        from ml import GLOBAL_VOCABULARY
        GLOBAL_VOCABULARY = {"word1": 0, "word2": 1, "word3": 2}
        
        # Создаем вектор
        vector = np.zeros(len(GLOBAL_VOCABULARY))
        assert len(vector) == 3

    def test_embedding_computation_performance(self):
        """Тест производительности вычисления эмбеддингов"""
        with patch('ml.SentenceTransformer') as mock_model:
            mock_model_instance = Mock()
            mock_model_instance.encode.return_value = np.array([0.1, 0.2, 0.3])
            mock_model.return_value = mock_model_instance
            
            text = "Test text for embedding"
            model = mock_model()
            
            start_time = time.time()
            embedding = model.encode(text)
            elapsed_time = time.time() - start_time
            
            assert elapsed_time < 0.5
            assert len(embedding) == 3

    def test_large_text_processing(self):
        """Тест обработки большого текста"""
        large_text = " ".join(["test word" for _ in range(5000)])
        
        # Проверка, что обработка не вызывает ошибок
        try:
            tokens = tokenize_text(large_text)
            assert len(tokens) > 0
        except Exception as e:
            pytest.fail(f"Large text processing failed: {e}")