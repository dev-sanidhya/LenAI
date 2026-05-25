import asyncio
import uuid
from pathlib import Path
from app.workers.celery_app import celery_app
from app.core.logging import get_logger

logger = get_logger(__name__)


def _run_async(coro):
    """Run a coroutine in a new event loop (Celery workers are sync)."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(bind=True, name="app.workers.tasks.ingest_pdf_task", max_retries=2)
def ingest_pdf_task(self, document_id: str, file_path: str, tenant_id: str):
    """Process a PDF: extract, chunk, embed, store in ChromaDB. Update document status in PG."""
    from app.services.ingestion.pdf_ingester import extract_and_chunk
    from app.services.reasoning.rag_retriever import store_chunks, delete_chunks_for_document
    from app.db.session import AsyncSessionLocal
    from app.models.document import Document
    from sqlalchemy import select

    async def _run():
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Document).where(Document.id == uuid.UUID(document_id)))
            doc = result.scalar_one_or_none()
            if not doc:
                logger.error("document_not_found", document_id=document_id)
                return

            doc.upload_status = "processing"
            await db.commit()

        try:
            path = Path(file_path)
            chunks, ocr_used = extract_and_chunk(path, document_id, tenant_id)

            # Delete stale chunks before re-inserting (idempotent)
            await delete_chunks_for_document(document_id)
            await store_chunks(chunks)

            async with AsyncSessionLocal() as db:
                result = await db.execute(select(Document).where(Document.id == uuid.UUID(document_id)))
                doc = result.scalar_one_or_none()
                if doc:
                    doc.upload_status = "ready"
                    doc.chunk_count = len(chunks)
                    doc.ocr_used = ocr_used
                    await db.commit()

            logger.info("pdf_ingestion_complete", document_id=document_id, chunks=len(chunks))

        except Exception as e:
            logger.error("pdf_ingestion_failed", document_id=document_id, error=str(e))
            async with AsyncSessionLocal() as db:
                result = await db.execute(select(Document).where(Document.id == uuid.UUID(document_id)))
                doc = result.scalar_one_or_none()
                if doc:
                    doc.upload_status = "failed"
                    await db.commit()
            raise

    _run_async(_run())


@celery_app.task(bind=True, name="app.workers.tasks.ingest_csv_task", max_retries=2)
def ingest_csv_task(self, dataset_id: str, file_path: str, tenant_id: str):
    """Process a CSV/Excel: ingest into PostgreSQL, compute statistics."""
    from app.services.ingestion.csv_ingester import ingest_csv
    from app.db.session import AsyncSessionLocal
    from app.models.dataset import Dataset
    from sqlalchemy import select

    async def _run():
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Dataset).where(Dataset.id == uuid.UUID(dataset_id)))
            ds = result.scalar_one_or_none()
            if not ds:
                return

            ds.upload_status = "processing"
            await db.commit()

        try:
            path = Path(file_path)
            async with AsyncSessionLocal() as db:
                info = await ingest_csv(path, tenant_id, dataset_id, db)

                result = await db.execute(select(Dataset).where(Dataset.id == uuid.UUID(dataset_id)))
                ds = result.scalar_one_or_none()
                if ds:
                    ds.upload_status = "ready"
                    ds.table_name = info["table_name"]
                    ds.row_count = info["row_count"]
                    ds.column_count = info["column_count"]
                    ds.schema_info = info["schema_info"]
                    await db.commit()

            logger.info("csv_ingestion_complete", dataset_id=dataset_id, rows=info["row_count"])

        except Exception as e:
            logger.error("csv_ingestion_failed", dataset_id=dataset_id, error=str(e))
            async with AsyncSessionLocal() as db:
                result = await db.execute(select(Dataset).where(Dataset.id == uuid.UUID(dataset_id)))
                ds = result.scalar_one_or_none()
                if ds:
                    ds.upload_status = "failed"
                    await db.commit()
            raise

    _run_async(_run())
