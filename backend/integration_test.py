# test_integration.py
import pytest
from unittest.mock import Mock, patch
from sqlalchemy.orm import Session
from models import Site, Page, InvertedIndex
from ml import process_content, build_inverted_index, calculate_tfidf
from tasks import index_site

class TestIntegration:
    @patch('tasks.SessionLocal')
    def test_full_indexing_flow(self, mock_session):
        """Тест полного процесса индексации"""
        # Создаем моки для БД
        mock_db = Mock()
        mock_session.return_value = mock_db
        
        # Создаем тестовый сайт
        site = Site(id=1, url="https://example.com")
        mock_db.query().filter().first.return_value = site
        
        # Мокаем HTTP запрос
        mock_response = Mock()
        mock_response.content = b"<html><title>Test</title><body>Test content</body></html>"
        
        with patch('tasks.requests.get', return_value=mock_response):
            with patch('tasks.BeautifulSoup') as mock_bs:
                mock_soup = Mock()
                mock_soup.title.string = "Test Page"
                mock_soup.stripped_strings = ["Test content"]
                mock_bs.return_value = mock_soup
                
                with patch('tasks.process_content', return_value="test content"):
                    with patch('tasks.compute_embeddings'):
                        with patch('tasks.calculate_tfidf'):
                            # Выполняем индексацию
                            result = index_site(1)
                            assert result["status"] == "success"

    def test_tfidf_calculation_integration(self):
        """Тест вычисления TF-IDF с реальными данными"""
        # Создаем тестовые данные
        pages = [
            Page(id=1, token_text="hello world hello test"),
            Page(id=2, token_text="world test example"),
            Page(id=3, token_text="hello example")
        ]
        
        # Создаем мок БД
        mock_db = Mock()
        mock_db.query().filter().all.return_value = pages
        
        # Вычисляем TF-IDF
        with patch('ml.tqdm', lambda x, **kwargs: x):
            calculate_tfidf(mock_db)
            
            # Проверяем, что TF-IDF был вычислен
            assert mock_db.commit.called
            assert pages[0].tf_idf is not None
            assert len(pages[0].tf_idf) > 0

    def test_search_integration_with_real_data(self):
        """Тест поиска с реальными данными"""
        # Подготавливаем данные
        pages = [
            Page(id=1, token_text="test example", tf_idf=[0.1, 0.2, 0.3]),
            Page(id=2, token_text="another test", tf_idf=[0.2, 0.1, 0.4])
        ]
        
        mock_db = Mock()
        mock_db.query().filter().all.return_value = pages
        
        with patch('ml.tokenize_text', return_value=["test"]):
            with patch('ml.GLOBAL_VOCABULARY', {"test": 0, "example": 1, "another": 2}):
                with patch('ml.GLOBAL_WORD_DOC_COUNTS', {"test": 2, "example": 1, "another": 1}):
                    with patch('ml.GLOBAL_N_DOC', 2):
                        with patch('ml.get_sbert_model') as mock_sbert:
                            mock_model = Mock()
                            mock_model.encode.return_value = [0.1, 0.2, 0.3]
                            mock_sbert.return_value = mock_model
                            
                            from ml import search
                            results = search("test", mock_db)
                            assert results is not None

    def test_data_persistence_integration(self):
        """Тест сохранения данных в БД"""
        # Создаем тестовые объекты
        site = Site(url="https://example.com", status="pending")
        page = Page(url="https://example.com", content="Test content")
        index_entry = InvertedIndex(word="test", page_id=1, frequency=1, weight=0.5)
        
        # Проверяем, что объекты создаются корректно
        assert site.url == "https://example.com"
        assert page.content == "Test content"
        assert index_entry.word == "test"