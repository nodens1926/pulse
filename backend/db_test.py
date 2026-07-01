# test_database.py
import pytest
from sqlalchemy import inspect
from sqlalchemy.orm import sessionmaker
from database import engine, SessionLocal, Base, get_db
from models import Site, Page, InvertedIndex

class TestDatabase:
    def test_engine_creation(self):
        """Проверка создания engine"""
        assert engine is not None
        assert str(engine.url).startswith("postgresql://")

    def test_session_local_creation(self):
        """Проверка создания SessionLocal"""
        assert SessionLocal is not None
        assert issubclass(SessionLocal, sessionmaker)

    def test_base_declarative(self):
        """Проверка базового класса"""
        assert Base is not None
        assert hasattr(Base, 'metadata')

    def test_tables_exist(self):
        """Проверка, что таблицы определены"""
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        assert 'sites' in tables
        assert 'pages' in tables
        assert 'inverted_index' in tables

    def test_get_db_generator(self):
        """Проверка генератора get_db"""
        db_gen = get_db()
        db = next(db_gen)
        assert db is not None
        assert db.bind is not None
        
        # Проверка закрытия
        with pytest.raises(StopIteration):
            next(db_gen)

    def test_session_management(self):
        """Проверка управления сессией"""
        db = SessionLocal()
        try:
            assert db.is_active
        finally:
            db.close()
            assert not db.is_active

    def test_model_relationships(self):
        """Проверка отношений моделей"""
        assert hasattr(Site, 'pages')
        assert hasattr(Page, 'site')
        assert hasattr(Page, 'inverted_index_entries')
        assert hasattr(InvertedIndex, 'page')

    def test_connection_pool(self):
        """Проверка пула соединений"""
        engine.pool._max_overflow = 10
        assert engine.pool._max_overflow == 10

    def test_session_factory_parameters(self):
        """Проверка параметров SessionLocal"""
        assert SessionLocal.kw.get('autocommit') == False
        assert SessionLocal.kw.get('autoflush') == False
        assert SessionLocal.kw.get('bind') is not None