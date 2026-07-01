# test_schemas.py
import pytest
from datetime import datetime
from pydantic import ValidationError
from schemas import (
    SiteCreate, SiteResponse, SearchRequest, 
    SearchResult, SearchResponse, StatusResponse
)

class TestSchemas:
    def test_site_create_valid_url(self):
        """Проверка валидного URL в SiteCreate"""
        site = SiteCreate(url="https://example.com")
        assert str(site.url) == "https://example.com/"

    def test_site_create_invalid_url(self):
        """Проверка невалидного URL в SiteCreate"""
        with pytest.raises(ValidationError):
            SiteCreate(url="not_a_url")

    def test_site_create_with_name(self):
        """Проверка SiteCreate с именем"""
        site = SiteCreate(url="https://example.com", name="Test Site")
        assert site.name == "Test Site"

    def test_site_create_without_name(self):
        """Проверка SiteCreate без имени"""
        site = SiteCreate(url="https://example.com")
        assert site.name is None

    def test_site_response_model(self):
        """Проверка SiteResponse"""
        site = SiteResponse(
            id=1,
            url="https://example.com",
            name="Test",
            status="indexed",
            date_added=datetime.now()
        )
        assert site.id == 1
        assert site.url == "https://example.com"
        assert site.status == "indexed"

    def test_search_request_valid(self):
        """Проверка SearchRequest"""
        req = SearchRequest(query="test query", limit=5)
        assert req.query == "test query"
        assert req.limit == 5

    def test_search_request_default_limit(self):
        """Проверка значения limit по умолчанию"""
        req = SearchRequest(query="test")
        assert req.limit == 10

    def test_search_result_model(self):
        """Проверка SearchResult"""
        result = SearchResult(
            page_id=1,
            url="https://example.com",
            title="Test Page",
            score=0.95,
            snippet="Test snippet"
        )
        assert result.score == 0.95
        assert result.snippet == "Test snippet"

    def test_search_response_model(self):
        """Проверка SearchResponse"""
        results = [
            SearchResult(page_id=1, url="https://example.com", score=0.9),
            SearchResult(page_id=2, url="https://test.com", score=0.8)
        ]
        response = SearchResponse(results=results, total=2)
        assert len(response.results) == 2
        assert response.total == 2

    def test_status_response_model(self):
        """Проверка StatusResponse"""
        status = StatusResponse(
            site_id=1,
            url="https://example.com",
            status="indexed",
            pages_indexed=10
        )
        assert status.site_id == 1
        assert status.pages_indexed == 10