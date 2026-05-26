import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import verify_token, get_tenant_id
from app.db.session import get_db
from app.models.audit import AuditRecord
from app.models.dataset import Dataset
from app.models.document import Document
from app.models.session_model import ChatSession
from app.services.memory.memory_manager import get_or_create_session, add_turn, get_session_context
from app.services.reasoning.synthesizer import synthesize
from app.core.logging import get_logger

router = APIRouter(prefix="/query", tags=["query"])
logger = get_logger(__name__)


class QueryRequest(BaseModel):
    question: str
    session_id: str | None = None
    dataset_ids: list[str] = []
    document_ids: list[str] = []
    scenario_assumptions: dict | None = None
    scenario_label: str | None = None
    is_ephemeral: bool = False  # True for scenario runs - result is NOT persisted to session memory


class ActionRequest(BaseModel):
    action: str  # accept | reject | review
    comment: str | None = None


@router.post("")
async def query(
    req: QueryRequest,
    tenant_id: str = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_token),
):
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    # Load session (creates one if not provided)
    session = await get_or_create_session(req.session_id, tenant_id, db)

    # If no dataset_ids provided, use session's active datasets
    dataset_ids = req.dataset_ids or list(session.active_dataset_ids or [])
    document_ids = req.document_ids or list(session.active_document_ids or [])

    # Build dataset schemas for SQL agent
    dataset_schemas = []
    for ds_id in dataset_ids:
        try:
            ds_uuid = uuid.UUID(ds_id)
        except ValueError:
            logger.warning("invalid_dataset_id", dataset_id=ds_id)
            continue
        result = await db.execute(
            select(Dataset).where(Dataset.id == ds_uuid, Dataset.tenant_id == tenant_id)
        )
        ds = result.scalar_one_or_none()
        if ds and ds.upload_status == "ready" and ds.table_name and ds.schema_info:
            columns = [{"name": col, "dtype": info.get("dtype", "TEXT")} for col, info in ds.schema_info.items()]
            dataset_schemas.append({
                "table_name": ds.table_name,
                "columns": columns,
                "row_count": ds.row_count,
                "dataset_id": ds_id,
            })

    session_context = await get_session_context(session)

    # Core reasoning - hybrid RAG + SQL
    result = await synthesize(
        question=req.question,
        tenant_id=tenant_id,
        session_context=session_context,
        document_ids=document_ids,
        dataset_schemas=dataset_schemas,
        db=db,
        scenario_assumptions=req.scenario_assumptions,
    )

    recommendation_id = uuid.uuid4()

    # Write immutable audit record
    audit = AuditRecord(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        session_id=session.id,
        recommendation_id=recommendation_id,
        query_text=req.question,
        active_dataset_ids=dataset_ids,
        active_document_ids=document_ids,
        llm_model=result["llm_model"],
        embed_model=result["embed_model"],
        prompt_version=result["prompt_version"],
        sql_queries=result["sql_queries"],
        retrieved_chunks=result["retrieved_chunks"],
        raw_model_output=result["raw_model_output"],
        recommendation=result["recommendation"],
        scenario_label=req.scenario_label,
        scenario_assumptions=req.scenario_assumptions,
        is_finalized=True,
    )
    db.add(audit)

    if req.is_ephemeral:
        # Scenario run: do NOT persist to the conversational memory timeline.
        # Scenario assumptions are synthetic; writing them into session memory
        # would contaminate subsequent real queries with artificial context.
        # The audit record is still written for traceability.
        logger.info("scenario_ephemeral", session_id=str(session.id), label=req.scenario_label)
    else:
        # Normal conversational turn: persist to session memory
        assistant_text = str(result["recommendation"].get("action", ""))
        await add_turn(session, req.question, assistant_text, db)

        if dataset_ids:
            session.active_dataset_ids = dataset_ids
        if document_ids:
            session.active_document_ids = document_ids

    await db.commit()

    logger.info("query_complete", session_id=str(session.id), recommendation_id=str(recommendation_id))

    return {
        "session_id": str(session.id),
        "recommendation_id": str(recommendation_id),
        "audit_record_id": str(audit.id),
        "recommendation": result["recommendation"],
        "reasoning_trace": {
            "sql_queries": result["sql_queries"],
            "retrieved_chunks": result["retrieved_chunks"],
        },
    }


@router.post("/{audit_record_id}/action")
async def submit_action(
    audit_record_id: str,
    req: ActionRequest,
    tenant_id: str = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_token),
):
    """Accept, Reject, or Request Review for a recommendation. Reject requires a comment."""
    valid_actions = {"accept", "reject", "review"}
    if req.action not in valid_actions:
        raise HTTPException(status_code=400, detail=f"Action must be one of: {valid_actions}")
    if req.action == "reject" and not req.comment:
        raise HTTPException(status_code=400, detail="A comment is required when rejecting a recommendation")

    result = await db.execute(
        select(AuditRecord).where(
            AuditRecord.id == uuid.UUID(audit_record_id),
            AuditRecord.tenant_id == tenant_id,
        )
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Audit record not found")
    if record.user_action:
        raise HTTPException(status_code=409, detail="Action already recorded for this recommendation")

    # Audit records are immutable for their core fields - we only update action fields
    record.user_action = req.action
    record.user_comment = req.comment
    record.action_at = datetime.utcnow()
    await db.commit()

    logger.info("recommendation_action", audit_id=audit_record_id, action=req.action)
    return {"status": "recorded", "action": req.action, "audit_record_id": audit_record_id}


@router.post("/scenarios")
async def compare_scenarios(
    questions: list[QueryRequest],
    tenant_id: str = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_token),
):
    """Run the same question under 2-3 different assumption sets, return side-by-side."""
    if len(questions) < 2 or len(questions) > 3:
        raise HTTPException(status_code=400, detail="Provide 2-3 scenarios for comparison")

    results = []
    for q in questions:
        resp = await query(q, tenant_id=tenant_id, db=db, _=None)
        results.append(resp)

    return {"scenarios": results, "count": len(results)}
