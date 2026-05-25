import hashlib
import uuid
from pathlib import Path
from celery import Celery
from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "lenai",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_routes={
        "app.workers.tasks.ingest_pdf_task": {"queue": "ingestion"},
        "app.workers.tasks.ingest_csv_task": {"queue": "ingestion"},
    },
)
