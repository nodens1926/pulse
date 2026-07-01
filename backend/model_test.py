# test_models.py
import pytest
from sqlalchemy import inspect, Column
from models import Site, Page, InvertedIndex
from database import Base

class TestModels:
    def test_site_model_columns(self):
        """Проверка колонок модели Site"""
        columns = {c.name for c in Site.__table__.columns}
        expected = {'id', 'url', 'name', 'status', 'date_added', 'last_crawled'}
        assert columns == expected

    def test_page_model_columns(self):
        """Проверка колонок модели Page"""
        columns = {c.name for c in Page.__table__.columns}
        expected = {'id', 'site_id', 'url', 'title', 'content', 'crawled_at',
                   'embedding', 'tf_idf', 'token_text', 'relevantnost'}
        assert columns == expected

    def test_inverted_index_model_columns(self):
        """Проверка колонок модели InvertedIndex"""
        columns = {c.name for c in InvertedIndex.__table__.columns}
        expected = {'word', 'page_id', 'frequency', 'weight'}
        assert columns == expected

    def test_site_primary_key(self):
        """Проверка первичного ключа Site"""
        pk = Site.__table__.primary_key
        assert len(pk.columns) == 1
        assert 'id' in pk.columns

    def test_page_foreign_key(self):
        """Проверка внешнего ключа Page"""
        fk = Page.__table__.foreign_keys
        assert any(fk.column.name == 'site_id' for fk in fk)

    def test_inverted_index_primary_key(self):
        """Проверка составного первичного ключа InvertedIndex"""
        pk = InvertedIndex.__table__.primary_key
        assert len(pk.columns) == 2
        assert 'word' in pk.columns
        assert 'page_id' in pk.columns

    def test_cascade_delete(self):
        """Проверка каскадного удаления"""
        page_fk = next(fk for fk in Page.__table__.foreign_keys 
                      if fk.column.name == 'site_id')
        assert page_fk.ondelete == 'CASCADE'
        
        index_fk = next(fk for fk in InvertedIndex.__table__.foreign_keys 
                       if fk.column.name == 'page_id')
        assert index_fk.ondelete == 'CASCADE'

    def test_site_page_relationship(self):
        """Проверка отношения Site -> Page"""
        rel = Site.pages
        assert rel.argument == 'Page'
        assert rel.back_populates == 'site'

    def test_page_site_relationship(self):
        """Проверка отношения Page -> Site"""
        rel = Page.site
        assert rel.argument == 'Site'
        assert rel.back_populates == 'pages'

    def test_page_inverted_index_relationship(self):
        """Проверка отношения Page -> InvertedIndex"""
        rel = Page.inverted_index_entries
        assert rel.argument == 'InvertedIndex'
        assert rel.back_populates == 'page'

    def test_column_types(self):
        """Проверка типов колонок"""
        assert isinstance(Site.__table__.c.id.type, Column)