import hashlib
import shutil
import uuid
from pathlib import Path
from fastapi import APIRouter, Depends, File, UploadFile, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import verify_token, get_tenant_id
from app.core.config import get_settings
from app.db.session import get_db
from app.models.dataset import Dataset
from app.models.document import Document
from app.workers.tasks import ingest_csv_task, ingest_pdf_task
from app.core.logging import get_logger

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


@router.post("/csv")
async def upload_csv(
    file: UploadFile = File(...),
    tenant_id: str = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_token),
):
    content = await file.read()
    _validate_upload(file.filename, len(content))

    file_hash = _file_hash(content)

    # Idempotency: check if same file already uploaded
    existing = await db.execute(
        select(Dataset).where(Dataset.tenant_id == tenant_id, Dataset.file_hash == file_hash, Dataset.is_active == True)
    )
    existing_ds = existing.scalar_one_or_none()
    if existing_ds and existing_ds.upload_status == "ready":
        return {
            "dataset_id": str(existing_ds.id),
            "status": "already_exists",
            "message": "Identical file already uploaded and processed",
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

    # Queue the ingestion job
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
    file: UploadFile = File(...),
    tenant_id: str = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_token),
):
    content = await file.read()
    _validate_upload(file.filename, len(content))

    file_hash = _file_hash(content)

    existing = await db.execute(
        select(Document).where(Document.tenant_id == tenant_id, Document.file_hash == file_hash, Document.is_active == True)
    )
    existing_doc = existing.scalar_one_or_none()
    if existing_doc and existing_doc.upload_status == "ready":
        return {
            "document_id": str(existing_doc.id),
            "status": "already_exists",
            "message": "Identical document already uploaded and processed",
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
