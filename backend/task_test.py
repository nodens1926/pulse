# test_tasks.py
import pytest
from unittest.mock import Mock, patch, MagicMock
from tasks import index_site, recalculate_all
from models import Site, Page

class TestTasks:
    @patch('tasks.SessionLocal')
    def test_index_site_not_found(self, mock_session):
        """Проверка индексации несуществующего сайта"""
        mock_db = Mock()
        mock_db.query().filter().first.return_value = None
        mock_session.return_value = mock_db
        
        result = index_site(1)
        assert "error" in result
        assert result["error"] == "Site not found"

    @patch('tasks.SessionLocal')
    @patch('tasks.requests.get')
    def test_index_site_network_error(self, mock_get, mock_session):
        """Проверка обработки сетевой ошибки"""
        mock_db = Mock()
        site = Site(id=1, url="https://example.com")
        mock_db.query().filter().first.return_value = site
        mock_session.return_value = mock_db
        
        mock_get.side_effect = Exception("Network error")
        
        result = index_site(1)
        assert "error" in result
        assert mock_db.commit.called

    @patch('tasks.SessionLocal')
    @patch('tasks.requests.get')
    @patch('tasks.BeautifulSoup')
    def test_index_site_success(self, mock_bs, mock_get, mock_session):
        """Проверка успешной индексации"""
        # Создаем моки
        mock_db = Mock()
        site = Site(id=1, url="https://example.com", status="pending")
        mock_db.query().filter().first.return_value = site
        mock_session.return_value = mock_db
        
        # Мокаем HTTP ответ
        mock_response = Mock()
        mock_response.content = b"<html><title>Test</title><body>Content</body></html>"
        mock_get.return_value = mock_response
        
        # Мокаем BeautifulSoup
        mock_soup = Mock()
        mock_soup.title.string = "Test Page"
        mock_soup.stripped_strings = ["Content"]
        mock_bs.return_value = mock_soup
        
        with patch('tasks.process_content', return_value="content tokens"):
            with patch('tasks.build_inverted_index', return_value=[]):
                with patch('tasks.compute_embeddings'):
                    with patch('tasks.calculate_tfidf'):
                        result = index_site(1)
                        assert result["status"] == "success"
                        assert site.status == "indexed"

    @patch('tasks.SessionLocal')
    def test_recalculate_all_success(self, mock_session):
        """Проверка пересчета всех индексов"""
        mock_db = Mock()
        mock_session.return_value = mock_db
        
        with patch('tasks.calculate_tfidf') as mock_calc:
            with patch('tasks.compute_embeddings') as mock_compute:
                result = recalculate_all()
                assert result["status"] == "success"
                mock_calc.assert_called_once_with(mock_db)
                mock_compute.assert_called_once_with(mock_db)

    @patch('tasks.SessionLocal')
    def test_index_site_no_content(self, mock_session):
        """Проверка обработки сайта без контента"""
        mock_db = Mock()
        site = Site(id=1, url="https://example.com")
        mock_db.query().filter().first.return_value = site
        mock_session.return_value = mock_db
        
        mock_response = Mock()
        mock_response.content = b"<html></html>"
        
        with patch('tasks.requests.get', return_value=mock_response):
            with patch('tasks.BeautifulSoup') as mock_bs:
                mock_soup = Mock()
                mock_soup.stripped_strings = []
                mock_bs.return_value = mock_soup
                
                result = index_site(1)
                assert "error" in result
                assert site.status == "error"

    @patch('tasks.SessionLocal')
    def test_index_site_creates_page(self, mock_session):
        """Проверка создания страницы при индексации"""
        mock_db = Mock()
        site = Site(id=1, url="https://example.com")
        mock_db.query().filter().first.return_value = site
        mock_session.return_value = mock_db
        
        mock_response = Mock()
        mock_response.content = b"<html><body>Content</body></html>"
        
        with patch('tasks.requests.get', return_value=mock_response):
            with patch('tasks.BeautifulSoup') as mock_bs:
                mock_soup = Mock()
                mock_soup.title = None
                mock_soup.stripped_strings = ["Content"]
                mock_bs.return_value = mock_soup
                
                with patch('tasks.process_content', return_value="content"):
                    with patch('tasks.build_inverted_index', return_value=[]):
                        with patch('tasks.compute_embeddings'):
                            with patch('tasks.calculate_tfidf'):
                                result = index_site(1)
                                mock_db.add.assert_called()
                                mock_db.commit.assert_called()