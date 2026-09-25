"""Celery scheduler entry points. Run with: celery -A app.tasks worker -B"""
from celery import Celery
from app.config import get_settings
from app.db import SessionLocal
from app.demos.service import expire_demos, retry_pending_demos

settings = get_settings()
celery = Celery("sitespark", broker=settings.redis_url, backend=settings.redis_url)
celery.conf.beat_schedule = {
    "retry-demo-generation": {"task": "sitespark.retry_demos", "schedule": 60.0},
    "expire-unpaid-demos": {"task": "sitespark.expire_demos", "schedule": 3600.0},
}


@celery.task(name="sitespark.retry_demos")
def retry_demos_task():
    db = SessionLocal()
    try: return retry_pending_demos(db, get_settings())
    finally: db.close()


@celery.task(name="sitespark.expire_demos")
def expire_demos_task():
    db = SessionLocal()
    try: return expire_demos(db, get_settings())
    finally: db.close()
