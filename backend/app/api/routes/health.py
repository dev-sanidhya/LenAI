from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
import httpx
from app.db.session import get_db
from app.core.config import get_settings

router = APIRouter(tags=["health"])
settings = get_settings()


@router.get("/health")
async def health():
    """Liveness check - container process is up."""
    return {"status": "ok", "service": "lenai-backend"}


@router.get("/ready")
async def ready(db: AsyncSession = Depends(get_db)):
    """
    Readiness check - all critical dependencies are available.
    Returns HTTP 200 only when every dependency is healthy.
    Returns HTTP 503 (Service Unavailable) when degraded, so that
    orchestrators (k8s, Docker healthcheck, load balancers) correctly
    stop routing traffic to an unready instance.
    """
    checks: dict[str, str] = {}
    all_ok = True

    # PostgreSQL
    try:
        await db.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception as e:
        checks["postgres"] = f"error: {e}"
        all_ok = False

    # Ollama - verify the API responds AND the required models are loaded
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{settings.ollama_base_url}/api/tags")
            resp.raise_for_status()
            loaded_models = {m["name"] for m in resp.json().get("models", [])}

            # Check LLM model is present (may be prefixed e.g. "llama3.1:8b")
            llm_ready = any(
                settings.ollama_llm_model in m or m.startswith(settings.ollama_llm_model.split(":")[0])
                for m in loaded_models
            )
            embed_ready = any(
                settings.ollama_embed_model in m or m.startswith(settings.ollama_embed_model.split(":")[0])
                for m in loaded_models
            )

            if llm_ready and embed_ready:
                checks["ollama"] = "ok"
            else:
                missing = []
                if not llm_ready:
                    missing.append(f"llm:{settings.ollama_llm_model}")
                if not embed_ready:
                    missing.append(f"embed:{settings.ollama_embed_model}")
                checks["ollama"] = f"models not ready: {missing}"
                all_ok = False
    except Exception as e:
        checks["ollama"] = f"error: {e}"
        all_ok = False

    # ChromaDB
    try:
        import chromadb
        from chromadb.config import Settings as ChromaSettings
        client = chromadb.HttpClient(
            host=settings.chroma_host,
            port=settings.chroma_port,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        client.heartbeat()
        checks["chromadb"] = "ok"
    except Exception as e:
        checks["chromadb"] = f"error: {e}"
        all_ok = False

    status_code = 200 if all_ok else 503
    body = {
        "status": "ready" if all_ok else "degraded",
        "checks": checks,
    }
    return JSONResponse(content=body, status_code=status_code)
