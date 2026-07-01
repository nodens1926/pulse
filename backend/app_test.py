# test_app.py
import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch
from app import app
from models import Site, Page

client = TestClient(app)

class TestApp:
    def test_root_endpoint(self):
        """Проверка корневого эндпоинта"""
        response = client.get("/")
        assert response.status_code == 200
        assert response.json()["message"] == "Pulse Search API"
        assert response.json()["version"] == "1.0"

    @patch('app.index_site')
    @patch('app.get_db')
    def test_add_site_success(self, mock_get_db, mock_index_site):
        """Проверка добавления сайта"""
        mock_db = Mock()
        site = Site(id=1, url="https://example.com", name="Example", status="pending")
        mock_db.query().filter().first.return_value = None
        mock_db.add.return_value = None
        mock_db.commit.return_value = None
        mock_db.refresh.return_value = None
        mock_get_db.return_value = mock_db
        
        response = client.post(
            "/api/sites",
            json={"url": "https://example.com", "name": "Example"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["url"] == "https://example.com"
        assert data["name"] == "Example"
        assert data["status"] == "pending"

    @patch('app.get_db')
    def test_add_site_duplicate(self, mock_get_db):
        """Проверка добавления дублирующегося сайта"""
        mock_db = Mock()
        mock_db.query().filter().first.return_value = Site(id=1)
        mock_get_db.return_value = mock_db
        
        response = client.post(
            "/api/sites",
            json={"url": "https://example.com"}
        )
        
        assert response.status_code == 400
        assert response.json()["detail"] == "Site already exists"

    @patch('app.search')
    @patch('app.get_db')
    def test_search_endpoint_success(self, mock_get_db, mock_search):
        """Проверка успешного поиска"""
        mock_db = Mock()
        mock_get_db.return_value = mock_db
        
        page = Page(id=1, url="https://example.com", title="Test", content="Content")
        mock_db.query().filter().first.return_value = page
        
        mock_search.return_value = [1]
        
        response = client.get("/api/search?q=test&limit=5")
        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert "total" in data

    def test_search_empty_query(self):
        """Проверка поиска с пустым запросом"""
        response = client.get("/api/search?q=")
        assert response.status_code == 200
        data = response.json()
        assert data["results"] == []
        assert data["total"] == 0

    @patch('app.get_db')
    def test_get_status_success(self, mock_get_db):
        """Проверка получения статуса"""
        mock_db = Mock()
        site = Site(id=1, url="https://example.com", status="indexed")
        mock_db.query().filter().first.return_value = site
        mock_db.query().filter().count.return_value = 10
        mock_get_db.return_value = mock_db
        
        response = client.get("/api/status/1")
        assert response.status_code == 200
        data = response.json()
        assert data["site_id"] == 1
        assert data["status"] == "indexed"
        assert data["pages_indexed"] == 10

    @patch('app.get_db')
    def test_get_status_not_found(self, mock_get_db):
        """Проверка получения статуса несуществующего сайта"""
        mock_db = Mock()
        mock_db.query().filter().first.return_value = None
        mock_get_db.return_value = mock_db
        
        response = client.get("/api/status/999")
        assert response.status_code == 404

    @patch('app.get_db')
    def test_get_all_status(self, mock_get_db):
        """Проверка получения статуса всех сайтов"""
        mock_db = Mock()
        sites = [
            Site(id=1, url="https://example1.com", status="indexed"),
            Site(id=2, url="https://example2.com", status="pending")
        ]
        mock_db.query().all.return_value = sites
        mock_db.query().filter().count.return_value = 5
        mock_get_db.return_value = mock_db
        
        response = client.get("/api/status")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["url"] == "https://example1.com"

    @patch('app.recalculate_all')
    def test_reindex_all(self, mock_recalculate):
        """Проверка переиндексации"""
        response = client.post("/api/reindex")
        assert response.status_code == 200
        assert response.json()["status"] == "reindexing started"
        mock_recalculate.delay.assert_called_once()

    def test_cors_headers(self):
        """Проверка CORS заголовков"""
        response = client.options(
            "/api/search",
            headers={"Origin": "http://localhost"}
        )
        assert response.status_code == 200
        assert "access-control-allow-origin" in response.headers