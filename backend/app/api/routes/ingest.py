import asyncio
import hashlib
import os
import shutil
import uuid
from pathlib import Path
from fastapi import APIRouter, BackgroundTasks, Depends, File, UploadFile, HTTPException, status
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import verify_token, get_tenant_id
from app.core.config import get_settings
from app.db.session import get_db
from app.models.dataset import Dataset
from app.models.document import Document
from app.workers.tasks import ingest_csv_task, ingest_pdf_task
from app.core.logging import get_logger

# INGEST_INLINE=true runs ingestion inside the FastAPI process via
# BackgroundTasks instead of dispatching to Celery. Useful when the
# Celery worker is unreliable on a particular host (e.g. WSL2
# memory pressure that intermittently kills the worker mid-task).
# Trade-off: jobs do NOT survive a backend restart in this mode;
# a startup recovery routine would be needed. Off by default.
INGEST_INLINE = os.getenv("INGEST_INLINE", "false").lower() in ("1", "true", "yes")

router = APIRouter(prefix="/ingest", tags=["ingestion"])
logger = get_logger(__name__)
settings = get_settings()

UPLOAD_DIR = Path("/app/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _file_hash(file_bytes: bytes) -> str:
    return hashlib.sha256(file_bytes).hexdigest()


def _validate_upload(filename: str, size: int) -> None:
    ext = Path(filename).suffix.lstrip(".").lower()
    if ext not in settings.allowed_extensions_list:
        raise HTTPException(status_code=400, detail=f"File type '{ext}' not allowed. Allowed: {settings.allowed_extensions_list}")
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    if size > max_bytes:
        raise HTTPException(status_code=413, detail=f"File too large. Max: {settings.max_upload_size_mb}MB")


# ---------------------------------------------------------------------------
# Inline ingestion runners. These do the same work as workers/tasks.py but
# stay inside the FastAPI event loop via BackgroundTasks.
# Activated when INGEST_INLINE=true; falls back to Celery otherwise.
# ---------------------------------------------------------------------------

async def _run_pdf_ingest(document_id: str, file_path: str, tenant_id: str) -> None:
    import fitz as _fitz
    from app.services.ingestion.pdf_ingester import extract_and_chunk
    from app.services.reasoning.rag_retriever import store_chunks, delete_chunks_for_document
    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        res = await db.execute(select(Document).where(Document.id == uuid.UUID(document_id)))
        d = res.scalar_one_or_none()
        if not d:
            return
        d.upload_status = "processing"
        await db.commit()

    try:
        path = Path(file_path)
        _fd = _fitz.open(str(path))
        page_count = len(_fd)
        _fd.close()
        chunks, ocr_used = extract_and_chunk(path, document_id, tenant_id)
        await delete_chunks_for_document(document_id)
        await store_chunks(chunks)

        async with AsyncSessionLocal() as db:
            res = await db.execute(select(Document).where(Document.id == uuid.UUID(document_id)))
            d = res.scalar_one_or_none()
            if d:
                d.upload_status = "ready"
                d.chunk_count = len(chunks)
                d.page_count = page_count
                d.ocr_used = ocr_used
                await db.commit()
        logger.info("pdf_ingest_inline_complete", document_id=document_id, chunks=len(chunks), pages=page_count)
    except Exception as e:
        logger.error("pdf_ingest_inline_failed", document_id=document_id, error=str(e), exc_info=True)
        async with AsyncSessionLocal() as db:
            res = await db.execute(select(Document).where(Document.id == uuid.UUID(document_id)))
            d = res.scalar_one_or_none()
            if d:
                d.upload_status = "failed"
                await db.commit()


async def _run_csv_ingest(dataset_id: str, file_path: str, tenant_id: str) -> None:
    from app.services.ingestion.csv_ingester import ingest_csv
    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        res = await db.execute(select(Dataset).where(Dataset.id == uuid.UUID(dataset_id)))
        ds = res.scalar_one_or_none()
        if not ds:
            return
        ds.upload_status = "processing"
        await db.commit()

    try:
        path = Path(file_path)
        async with AsyncSessionLocal() as db:
            info = await ingest_csv(path, tenant_id, dataset_id, db)
            res = await db.execute(select(Dataset).where(Dataset.id == uuid.UUID(dataset_id)))
            ds = res.scalar_one_or_none()
            if ds:
                ds.upload_status = "ready"
                ds.table_name = info["table_name"]
                ds.row_count = info["row_count"]
                ds.column_count = info["column_count"]
                ds.schema_info = info["schema_info"]
                await db.commit()
        logger.info("csv_ingest_inline_complete", dataset_id=dataset_id, rows=info["row_count"])
    except Exception as e:
        logger.error("csv_ingest_inline_failed", dataset_id=dataset_id, error=str(e), exc_info=True)
        async with AsyncSessionLocal() as db:
            res = await db.execute(select(Dataset).where(Dataset.id == uuid.UUID(dataset_id)))
            ds = res.scalar_one_or_none()
            if ds:
                ds.upload_status = "failed"
                await db.commit()


@router.post("/csv")
async def upload_csv(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    tenant_id: str = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_token),
):
    content = await file.read()
    _validate_upload(file.filename, len(content))

    file_hash = _file_hash(content)

    # Idempotency: if the same file hash exists in any non-failed state,
    # return the existing record. Multiple rows can exist if uploads raced
    # before the first one finished, so we pick the newest.
    existing = await db.execute(
        select(Dataset)
        .where(
            Dataset.tenant_id == tenant_id,
            Dataset.file_hash == file_hash,
            Dataset.is_active == True,
            Dataset.upload_status != "failed",
        )
        .order_by(desc(Dataset.created_at))
        .limit(1)
    )
    existing_ds = existing.scalars().first()
    if existing_ds:
        if INGEST_INLINE and existing_ds.upload_status != "ready":
            existing_path = UPLOAD_DIR / existing_ds.filename
            if existing_path.exists():
                existing_ds.job_id = f"inline-{existing_ds.id}"
                existing_ds.upload_status = "pending"
                await db.commit()
                background_tasks.add_task(_run_csv_ingest, str(existing_ds.id), str(existing_path), tenant_id)
                logger.info("csv_upload_requeued_inline", dataset_id=str(existing_ds.id))
                return {"dataset_id": str(existing_ds.id), "status": "queued", "job_id": existing_ds.job_id}
        return {
            "dataset_id": str(existing_ds.id),
            "status": "already_exists" if existing_ds.upload_status == "ready" else existing_ds.upload_status,
            "message": f"Identical file already uploaded (status: {existing_ds.upload_status})",
            "job_id": existing_ds.job_id,
        }

    dataset_id = uuid.uuid4()
    save_path = UPLOAD_DIR / f"{tenant_id}_{dataset_id}{Path(file.filename).suffix}"
    with open(save_path, "wb") as f:
        f.write(content)

    ds = Dataset(
        id=dataset_id,
        tenant_id=tenant_id,
        filename=str(save_path.name),
        original_filename=file.filename,
        file_hash=file_hash,
        file_size_bytes=len(content),
        upload_status="pending",
    )
    db.add(ds)
    await db.flush()

    # Dispatch ingestion: inline via FastAPI BackgroundTasks if enabled,
    # otherwise queue to Celery worker.
    if INGEST_INLINE:
        ds.job_id = f"inline-{dataset_id}"
        await db.commit()
        background_tasks.add_task(_run_csv_ingest, str(dataset_id), str(save_path), tenant_id)
        logger.info("csv_upload_inline", dataset_id=str(dataset_id))
        return {"dataset_id": str(dataset_id), "status": "queued", "job_id": ds.job_id}

    job = ingest_csv_task.apply_async(
        args=[str(dataset_id), str(save_path), tenant_id],
        queue="ingestion",
    )
    ds.job_id = job.id
    await db.commit()
    logger.info("csv_upload_queued", dataset_id=str(dataset_id), job_id=job.id)
    return {"dataset_id": str(dataset_id), "status": "queued", "job_id": job.id}


@router.post("/pdf")
async def upload_pdf(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    tenant_id: str = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_token),
):
    content = await file.read()
    _validate_upload(file.filename, len(content))

    file_hash = _file_hash(content)

    # Same idempotency pattern as CSV: newest non-failed match wins.
    existing = await db.execute(
        select(Document)
        .where(
            Document.tenant_id == tenant_id,
            Document.file_hash == file_hash,
            Document.is_active == True,
            Document.upload_status != "failed",
        )
        .order_by(desc(Document.created_at))
        .limit(1)
    )
    existing_doc = existing.scalars().first()
    if existing_doc:
        if INGEST_INLINE and existing_doc.upload_status != "ready":
            existing_path = UPLOAD_DIR / existing_doc.filename
            if existing_path.exists():
                existing_doc.job_id = f"inline-{existing_doc.id}"
                existing_doc.upload_status = "pending"
                await db.commit()
                background_tasks.add_task(_run_pdf_ingest, str(existing_doc.id), str(existing_path), tenant_id)
                logger.info("pdf_upload_requeued_inline", document_id=str(existing_doc.id))
                return {"document_id": str(existing_doc.id), "status": "queued", "job_id": existing_doc.job_id}
        return {
            "document_id": str(existing_doc.id),
            "status": "already_exists" if existing_doc.upload_status == "ready" else existing_doc.upload_status,
            "message": f"Identical document already uploaded (status: {existing_doc.upload_status})",
        }

    document_id = uuid.uuid4()
    save_path = UPLOAD_DIR / f"{tenant_id}_{document_id}.pdf"
    with open(save_path, "wb") as f:
        f.write(content)

    doc = Document(
        id=document_id,
        tenant_id=tenant_id,
        filename=str(save_path.name),
        original_filename=file.filename,
        file_hash=file_hash,
        file_size_bytes=len(content),
        upload_status="pending",
        embedding_model=settings.ollama_embed_model,
    )
    db.add(doc)
    await db.flush()

    if INGEST_INLINE:
        doc.job_id = f"inline-{document_id}"
        await db.commit()
        background_tasks.add_task(_run_pdf_ingest, str(document_id), str(save_path), tenant_id)
        logger.info("pdf_upload_inline", document_id=str(document_id))
        return {"document_id": str(document_id), "status": "queued", "job_id": doc.job_id}

    job = ingest_pdf_task.apply_async(
        args=[str(document_id), str(save_path), tenant_id],
        queue="ingestion",
    )
    doc.job_id = job.id
    await db.commit()
    logger.info("pdf_upload_queued", document_id=str(document_id), job_id=job.id)
    return {"document_id": str(document_id), "status": "queued", "job_id": job.id}


@router.get("/status/csv/{dataset_id}")
async def csv_status(
    dataset_id: str,
    tenant_id: str = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_token),
):
    result = await db.execute(
        select(Dataset).where(Dataset.id == uuid.UUID(dataset_id), Dataset.tenant_id == tenant_id)
    )
    ds = result.scalar_one_or_none()
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return {
        "dataset_id": str(ds.id),
        "status": ds.upload_status,
        "row_count": ds.row_count,
        "column_count": ds.column_count,
        "schema_info": ds.schema_info,
        "column_tags": ds.column_tags,
    }


@router.patch("/csv/{dataset_id}/tags")
async def update_column_tags(
    dataset_id: str,
    tags: dict,
    tenant_id: str = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_token),
):
    """Let the user tag columns as 'feature', 'target', or 'ignore'."""
    result = await db.execute(
        select(Dataset).where(Dataset.id == uuid.UUID(dataset_id), Dataset.tenant_id == tenant_id)
    )
    ds = result.scalar_one_or_none()
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found")
    ds.column_tags = tags
    await db.commit()
    return {"dataset_id": dataset_id, "column_tags": tags}


@router.get("/status/pdf/{document_id}")
async def pdf_status(
    document_id: str,
    tenant_id: str = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_token),
):
    result = await db.execute(
        select(Document).where(Document.id == uuid.UUID(document_id), Document.tenant_id == tenant_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return {
        "document_id": str(doc.id),
        "status": doc.upload_status,
        "chunk_count": doc.chunk_count,
        "page_count": doc.page_count,
        "ocr_used": doc.ocr_used,
    }


@router.get("/datasets")
async def list_datasets(
    tenant_id: str = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_token),
):
    result = await db.execute(
        select(Dataset).where(Dataset.tenant_id == tenant_id, Dataset.is_active == True)
    )
    datasets = result.scalars().all()
    return [
        {
            "dataset_id": str(ds.id),
            "original_filename": ds.original_filename,
            "status": ds.upload_status,
            "row_count": ds.row_count,
            "column_count": ds.column_count,
            "created_at": ds.created_at.isoformat(),
        }
        for ds in datasets
    ]


@router.get("/documents")
async def list_documents(
    tenant_id: str = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_token),
):
    result = await db.execute(
        select(Document).where(Document.tenant_id == tenant_id, Document.is_active == True)
    )
    docs = result.scalars().all()
    return [
        {
            "document_id": str(doc.id),
            "original_filename": doc.original_filename,
            "status": doc.upload_status,
            "chunk_count": doc.chunk_count,
            "page_count": doc.page_count,
            "created_at": doc.created_at.isoformat(),
        }
        for doc in docs
    ]
