from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.services.llm.ollama_client import get_ollama_client
from app.core.config import get_settings

router = APIRouter(tags=["health"])
settings = get_settings()


@router.get("/health")
async def health():
    """Liveness check - container is up."""
    return {"status": "ok", "service": "lenai-backend"}


@router.get("/ready")
async def ready(db: AsyncSession = Depends(get_db)):
    """Readiness check - all dependencies available."""
    checks = {}

    # PostgreSQL
    try:
        await db.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception as e:
        checks["postgres"] = f"error: {e}"

    # Ollama
    ollama = get_ollama_client()
    checks["ollama"] = "ok" if await ollama.health_check() else "unavailable"

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

    all_ok = all(v == "ok" for v in checks.values())
    return {"status": "ready" if all_ok else "degraded", "checks": checks}
