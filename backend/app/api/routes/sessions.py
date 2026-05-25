import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import verify_token, get_tenant_id
from app.db.session import get_db
from app.models.session_model import ChatSession
from app.core.logging import get_logger

router = APIRouter(prefix="/sessions", tags=["sessions"])
logger = get_logger(__name__)


@router.get("")
async def list_sessions(
    tenant_id: str = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_token),
):
    result = await db.execute(
        select(ChatSession)
        .where(ChatSession.tenant_id == tenant_id)
        .order_by(desc(ChatSession.last_active_at))
        .limit(20)
    )
    sessions = result.scalars().all()
    return [
        {
            "session_id": str(s.id),
            "title": s.title,
            "turn_count": s.turn_count,
            "active_dataset_ids": s.active_dataset_ids,
            "active_document_ids": s.active_document_ids,
            "last_active_at": s.last_active_at.isoformat(),
            "created_at": s.created_at.isoformat(),
        }
        for s in sessions
    ]


@router.get("/{session_id}")
async def get_session(
    session_id: str,
    tenant_id: str = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_token),
):
    result = await db.execute(
        select(ChatSession).where(
            ChatSession.id == uuid.UUID(session_id),
            ChatSession.tenant_id == tenant_id,
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {
        "session_id": str(session.id),
        "title": session.title,
        "turn_count": session.turn_count,
        "context_summary": session.context_summary,
        "messages": session.messages,
        "active_dataset_ids": session.active_dataset_ids,
        "active_document_ids": session.active_document_ids,
        "last_active_at": session.last_active_at.isoformat(),
        "created_at": session.created_at.isoformat(),
    }
