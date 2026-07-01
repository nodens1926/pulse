# test_config.py
import os
import pytest
from unittest.mock import patch
from config import DATABASE_URL, REDIS_URL

class TestConfig:
    def test_database_url_default(self):
        """Проверка значения DATABASE_URL по умолчанию"""
        with patch.dict(os.environ, {}, clear=True):
            # Перезагружаем модуль для применения изменений
            import importlib
            import config
            importlib.reload(config)
            assert config.DATABASE_URL == "postgresql://pulse:pulse123@postgres:5432/pulse"

    def test_database_url_from_env(self):
        """Проверка чтения DATABASE_URL из переменных окружения"""
        test_url = "postgresql://test:test@localhost:5432/testdb"
        with patch.dict(os.environ, {"DATABASE_URL": test_url}, clear=True):
            import importlib
            import config
            importlib.reload(config)
            assert config.DATABASE_URL == test_url

    def test_redis_url_default(self):
        """Проверка значения REDIS_URL по умолчанию"""
        with patch.dict(os.environ, {}, clear=True):
            import importlib
            import config
            importlib.reload(config)
            assert config.REDIS_URL == "redis://redis:6379/0"

    def test_redis_url_from_env(self):
        """Проверка чтения REDIS_URL из переменных окружения"""
        test_url = "redis://localhost:6379/1"
        with patch.dict(os.environ, {"REDIS_URL": test_url}, clear=True):
            import importlib
            import config
            importlib.reload(config)
            assert config.REDIS_URL == test_url

    def test_dotenv_loading(self):
        """Проверка, что dotenv загружается"""
        with patch('config.load_dotenv') as mock_load:
            import importlib
            import config
            importlib.reload(config)
            mock_load.assert_called_once()

    def test_environment_variables_priority(self):
        """Проверка приоритета переменных окружения над .env"""
        with patch.dict(os.environ, {"DATABASE_URL": "env_value"}):
            with patch('config.load_dotenv'):
                import importlib
                import config
                importlib.reload(config)
                assert config.DATABASE_URL == "env_value"