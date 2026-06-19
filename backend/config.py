import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://pulse:pulse123@postgres:5432/pulse")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")