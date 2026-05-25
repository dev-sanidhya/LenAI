import time
import signal
import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.api.routes import health, ingest, query, audit, sessions, auth

configure_logging()
logger = get_logger(__name__)
settings = get_settings()

# Prometheus metrics
REQUEST_COUNT = Counter("lenai_requests_total", "Total requests", ["method", "endpoint", "status"])
REQUEST_LATENCY = Histogram("lenai_request_latency_seconds", "Request latency", ["endpoint"])
INGEST_COUNT = Counter("lenai_ingestion_total", "Total ingestion jobs", ["type", "status"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("startup", env=settings.app_env, llm_model=settings.ollama_llm_model)

    # Pre-load the cross-encoder on startup so first request doesn't pay cold start
    try:
        from app.services.reasoning.rag_retriever import _get_cross_encoder
        _get_cross_encoder()
        logger.info("cross_encoder_loaded")
    except Exception as e:
        logger.warning("cross_encoder_load_failed", error=str(e))

    yield

    logger.info("shutdown", reason="graceful")


def create_app() -> FastAPI:
    app = FastAPI(
        title="LenAI Pricing Intelligence API",
        version="1.0.0",
        description="AI co-pilot for insurance and banking pricing teams",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def metrics_middleware(request: Request, call_next):
        start = time.time()
        response = await call_next(request)
        latency = time.time() - start
        endpoint = request.url.path
        REQUEST_COUNT.labels(request.method, endpoint, response.status_code).inc()
        REQUEST_LATENCY.labels(endpoint).observe(latency)
        response.headers["X-Response-Time"] = f"{latency:.3f}s"
        return response

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.error("unhandled_exception", path=request.url.path, error=str(exc), exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "path": str(request.url.path)},
        )

    @app.get("/metrics")
    async def metrics():
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    app.include_router(health.router)
    app.include_router(auth.router, prefix="/api/v1")
    app.include_router(ingest.router, prefix="/api/v1")
    app.include_router(query.router, prefix="/api/v1")
    app.include_router(audit.router, prefix="/api/v1")
    app.include_router(sessions.router, prefix="/api/v1")

    return app


app = create_app()


def handle_sigterm(*_):
    logger.info("sigterm_received")
    sys.exit(0)


signal.signal(signal.SIGTERM, handle_sigterm)
