import io
import json
import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Preformatted
from app.api.deps import verify_api_key, get_tenant_id
from app.db.session import get_db
from app.models.audit import AuditRecord
from app.core.logging import get_logger

router = APIRouter(prefix="/audit", tags=["audit"])
logger = get_logger(__name__)


@router.get("")
async def list_audit_records(
    tenant_id: str = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_api_key),
    limit: int = 50,
    offset: int = 0,
):
    result = await db.execute(
        select(AuditRecord)
        .where(AuditRecord.tenant_id == tenant_id)
        .order_by(desc(AuditRecord.created_at))
        .limit(limit)
        .offset(offset)
    )
    records = result.scalars().all()
    return [_serialize_record(r) for r in records]


@router.get("/{audit_record_id}")
async def get_audit_record(
    audit_record_id: str,
    tenant_id: str = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_api_key),
):
    result = await db.execute(
        select(AuditRecord).where(
            AuditRecord.id == uuid.UUID(audit_record_id),
            AuditRecord.tenant_id == tenant_id,
        )
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Audit record not found")
    return _serialize_record(record)


@router.get("/{audit_record_id}/export/json")
async def export_json(
    audit_record_id: str,
    tenant_id: str = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_api_key),
):
    result = await db.execute(
        select(AuditRecord).where(
            AuditRecord.id == uuid.UUID(audit_record_id),
            AuditRecord.tenant_id == tenant_id,
        )
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Not found")

    data = _serialize_record(record)
    content = json.dumps(data, indent=2, default=str)
    return StreamingResponse(
        io.BytesIO(content.encode()),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename=audit_{audit_record_id[:8]}.json"},
    )


@router.get("/{audit_record_id}/export/pdf")
async def export_pdf(
    audit_record_id: str,
    tenant_id: str = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_api_key),
):
    result = await db.execute(
        select(AuditRecord).where(
            AuditRecord.id == uuid.UUID(audit_record_id),
            AuditRecord.tenant_id == tenant_id,
        )
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Not found")

    pdf_bytes = _build_pdf(record)
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=recommendation_{audit_record_id[:8]}.pdf"},
    )


def _serialize_record(r: AuditRecord) -> dict:
    return {
        "id": str(r.id),
        "tenant_id": r.tenant_id,
        "session_id": str(r.session_id) if r.session_id else None,
        "recommendation_id": str(r.recommendation_id) if r.recommendation_id else None,
        "query_text": r.query_text,
        "active_dataset_ids": r.active_dataset_ids,
        "active_document_ids": r.active_document_ids,
        "llm_model": r.llm_model,
        "embed_model": r.embed_model,
        "prompt_version": r.prompt_version,
        "sql_queries": r.sql_queries,
        "retrieved_chunks": r.retrieved_chunks,
        "raw_model_output": r.raw_model_output,
        "recommendation": r.recommendation,
        "user_action": r.user_action,
        "user_comment": r.user_comment,
        "action_at": r.action_at.isoformat() if r.action_at else None,
        "scenario_label": r.scenario_label,
        "scenario_assumptions": r.scenario_assumptions,
        "created_at": r.created_at.isoformat(),
    }


def _build_pdf(record: AuditRecord) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=50, leftMargin=50, topMargin=60, bottomMargin=40)
    styles = getSampleStyleSheet()
    story = []

    def h1(text): return Paragraph(f"<b>{text}</b>", styles["Heading1"])
    def h2(text): return Paragraph(f"<b>{text}</b>", styles["Heading2"])
    def body(text): return Paragraph(str(text)[:2000], styles["BodyText"])
    def pre(text): return Preformatted(str(text)[:1000], styles["Code"])
    def gap(): return Spacer(1, 12)

    rec = record.recommendation or {}
    story += [
        h1("LenAI Pricing Recommendation"),
        body(f"Generated: {record.created_at.strftime('%Y-%m-%d %H:%M UTC')}"),
        body(f"Audit Record: {record.id}"),
        gap(),
        h2("Recommendation"),
        body(rec.get("action", "N/A")),
        body(f"Confidence: {rec.get('confidence', 'N/A')}"),
        body(f"Confidence Rationale: {rec.get('confidence_rationale', 'N/A')}"),
        gap(),
        h2("Query"),
        body(record.query_text),
        gap(),
        h2("Model Provenance"),
        body(f"LLM: {record.llm_model}  |  Embeddings: {record.embed_model}  |  Prompt: {record.prompt_version}"),
        gap(),
    ]

    if record.sql_queries:
        story.append(h2("SQL Evidence"))
        for q in record.sql_queries[:3]:
            story.append(pre(q.get("sql", "")))
            story.append(body(f"Rows returned: {q.get('row_count', 0)}"))
            story.append(gap())

    if record.retrieved_chunks:
        story.append(h2("Document Evidence"))
        for chunk in record.retrieved_chunks[:5]:
            meta = chunk.get("metadata", {})
            story.append(body(f"[Doc {str(meta.get('document_id','?'))[:8]}, p.{meta.get('page','?')}]"))
            story.append(body(chunk.get("text", "")[:400]))
            story.append(gap())

    if rec.get("conflicts"):
        story.append(h2("Conflicts Detected"))
        for conflict in rec["conflicts"]:
            story.append(body(f"- {conflict}"))
        story.append(gap())

    if record.user_action:
        story.append(h2("Decision"))
        story.append(body(f"Action: {record.user_action.upper()}"))
        if record.user_comment:
            story.append(body(f"Comment: {record.user_comment}"))

    doc.build(story)
    return buffer.getvalue()
