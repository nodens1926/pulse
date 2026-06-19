from celery import Celery
from config import REDIS_URL

celery = Celery("pulse", broker=REDIS_URL, backend=REDIS_URL)

@celery.task
def index_site(url: str):
    return {"status": "indexed", "url": url}