import asyncio
import json
from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.llm.ollama_client import get_ollama_client
from app.services.reasoning.rag_retriever import retrieve
from app.services.reasoning.sql_agent import generate_and_run_sql
from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)
settings = get_settings()

PROMPT_VERSION = "v1.0"

SYNTHESIS_SYSTEM = """You are an AI pricing analyst for insurance and banking.
Your job is to reason over both document evidence and data query results to produce
a structured pricing recommendation.

You MUST respond with valid JSON only, matching this exact schema:
{
  "action": "string - single sentence recommendation e.g. 'Increase motor premium by 8-12% for under-25 drivers in the North'",
  "confidence": "high | medium | low",
  "confidence_rationale": "string - what drives uncertainty: data gap, conflicting sources, or model uncertainty",
  "document_evidence": [
    {"text": "...", "source": "...", "page": 0, "relevance": "why this supports the recommendation"}
  ],
  "sql_evidence": [
    {"sql": "...", "key_finding": "...", "row_summary": "..."}
  ],
  "conflicts": ["list of any conflicts between document evidence and data, or empty list"],
  "reasoning_steps": ["step 1", "step 2", "..."],
  "uncertainty_sources": ["list of data gaps or limitations"]
}"""


def _format_rag_context(chunks: list[dict]) -> str:
    if not chunks:
        return "No relevant document sections found."
    lines = []
    for i, chunk in enumerate(chunks, 1):
        meta = chunk.get("metadata", {})
        source = f"[Doc {meta.get('document_id', 'unknown')[:8]}, p.{meta.get('page', '?')}]"
        lines.append(f"Evidence {i} {source}:\n{chunk['text']}\n")
    return "\n".join(lines)


def _format_sql_context(sql_results: list[dict]) -> str:
    if not sql_results:
        return "No structured data queries were run."
    lines = []
    for i, res in enumerate(sql_results, 1):
        if res.get("error"):
            lines.append(f"Query {i} (FAILED: {res['error']}):\n{res['sql']}\n")
        else:
            sample = res["rows"][:5]
            lines.append(f"Query {i}:\n{res['sql']}\nReturned {res['row_count']} rows. Sample: {json.dumps(sample, default=str)}\n")
    return "\n".join(lines)


async def synthesize(
    question: str,
    tenant_id: str,
    session_context: str,
    document_ids: list[str],
    dataset_schemas: list[dict],
    db: AsyncSession,
    scenario_assumptions: dict = None,
) -> dict:
    """
    Run RAG and SQL retrieval in parallel, then synthesize a recommendation.
    Returns the full structured recommendation + audit trail data.
    """
    scenario_note = ""
    if scenario_assumptions:
        scenario_note = f"\nScenario assumptions for this run: {json.dumps(scenario_assumptions)}"

    augmented_question = question + scenario_note

    # Run both retrieval paths in parallel
    rag_task = retrieve(
        query=augmented_question,
        tenant_id=tenant_id,
        document_ids=document_ids if document_ids else None,
    )
    sql_task = generate_and_run_sql(
        question=augmented_question,
        dataset_schemas=dataset_schemas,
        db=db,
    )

    rag_chunks, sql_results = await asyncio.gather(rag_task, sql_task)

    rag_context = _format_rag_context(rag_chunks)
    sql_context = _format_sql_context(sql_results)

    prompt = f"""Session context (prior conversation summary):
{session_context or "No prior context."}

User question:
{augmented_question}

DOCUMENT EVIDENCE (retrieved from uploaded PDFs):
{rag_context}

DATA EVIDENCE (SQL queries run against uploaded tables):
{sql_context}

Based on ALL the evidence above, produce a structured pricing recommendation.
If document evidence and data evidence conflict, you MUST surface the conflict explicitly in the "conflicts" field.
Do NOT silently resolve conflicts by choosing one source over the other."""

    ollama = get_ollama_client()
    raw_output = await ollama.generate(prompt=prompt, system=SYNTHESIS_SYSTEM, temperature=0.1)

    try:
        recommendation = json.loads(raw_output)
    except json.JSONDecodeError:
        # Retry with stricter prompt
        logger.warning("synthesis_json_parse_failed", raw_snippet=raw_output[:300])
        recommendation = await ollama.generate_json(prompt=prompt, system=SYNTHESIS_SYSTEM)

    return {
        "recommendation": recommendation,
        "raw_model_output": raw_output,
        "retrieved_chunks": rag_chunks,
        "sql_queries": sql_results,
        "prompt_version": PROMPT_VERSION,
        "llm_model": settings.ollama_llm_model,
        "embed_model": settings.ollama_embed_model,
    }
