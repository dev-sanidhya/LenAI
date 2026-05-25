# LenAI - Pricing Intelligence Platform
## Implementation Plan

**Assignment:** Insurance / Banking Pricing Intelligence Product  
**Deadline:** 2-3 days from May 23, 2025  
**Standard:** Production-ready on day one

---

## Current Status

**Phase:** Foundation (commit 1 - scaffolding in progress)

---

## Architecture Strategy

Build a full-stack AI co-pilot that combines:
1. Hybrid RAG (ChromaDB + local re-ranking) over uploaded PDFs
2. Text-to-SQL with sandboxed execution over uploaded CSVs
3. Self-hosted LLM via Ollama (Llama 3.1 8B) - zero external API calls
4. PostgreSQL for all relational data, sessions, and immutable audit trail
5. React frontend with structured recommendation cards

---

## Build Phases

### Phase 1 - Foundation (Day 1 AM)
- [x] Git setup, .gitignore, .env.example
- [x] Plan.md and ARCHITECTURE.md
- [ ] docker-compose.yml (full stack: postgres, chromadb, redis, ollama, backend, frontend)
- [ ] Ollama entrypoint script (model warm-up before health check passes)
- [ ] Backend Dockerfiles

### Phase 2 - Backend Core (Day 1 PM)
- [ ] FastAPI app skeleton with structured logging
- [ ] PostgreSQL models (Dataset, Document, Session, AuditRecord, Recommendation)
- [ ] Alembic migrations (001_initial_schema)
- [ ] Config management (pydantic-settings from .env)
- [ ] Health check endpoint (/health, /ready)
- [ ] API key auth middleware

### Phase 3 - Data Ingestion (Day 1 PM)
- [ ] CSV/Excel ingester: schema inference, column tagging, idempotent upload
- [ ] PDF ingester: pdfplumber extraction, table handling, chunking (512/50)
- [ ] Embedding generation via Ollama nomic-embed-text
- [ ] ChromaDB storage with dedup (content hash)
- [ ] Redis-backed background job queue for ingestion

### Phase 4 - Hybrid Reasoning Engine (Day 2 AM)
- [ ] RAG retriever: semantic search + cross-encoder reranking
- [ ] SQL agent: LLM generates SELECT, sqlglot validates, sandboxed execution
- [ ] Hybrid synthesizer: parallel retrieval paths, conflict surfacing
- [ ] Structured recommendation card output (JSON schema enforced)

### Phase 5 - Memory System (Day 2 AM)
- [ ] Within-session memory (sliding window, last 4 turns)
- [ ] Cross-session memory (summarization of older turns, stored in PostgreSQL)
- [ ] Dataset context persistence across sessions

### Phase 6 - Product Layer (Day 2 PM)
- [ ] Scenario comparison (2-3 assumption sets, side-by-side diff)
- [ ] Immutable audit trail (append-only, JSON + PDF export)
- [ ] Accept/Reject/Review actions with mandatory comment on reject

### Phase 7 - Frontend (Day 2 PM - Day 3 AM)
- [ ] React + Vite + Tailwind setup
- [ ] Upload zone (drag-drop, CSV + PDF, progress)
- [ ] Query interface (plain English input, streaming response)
- [ ] Recommendation card (action, confidence, evidence panel, reasoning trace)
- [ ] Scenario comparison view
- [ ] Audit log viewer + export button
- [ ] Session memory indicator (shows what system remembers)

### Phase 8 - Production Hardening (Day 3)
- [ ] Concurrency control (semaphore on Ollama calls)
- [ ] Graceful shutdown (SIGTERM handlers)
- [ ] Structured logs (structlog, JSON format)
- [ ] Basic metrics (Prometheus counters: request count, error rate, latency)
- [ ] Resource limits in Docker Compose
- [ ] README finalized
- [ ] Video demo recorded

---

## Tech Stack Decisions

| Component | Choice | Why |
|-----------|--------|-----|
| LLM | Ollama + Llama 3.1 8B | Self-hosted, no API cost, good at SQL gen and reasoning |
| Embeddings | nomic-embed-text via Ollama | Keeps all inference in one container |
| Re-ranking | cross-encoder/ms-marco-MiniLM-L-6-v2 | Free, local, significant retrieval quality gain |
| Vector DB | ChromaDB | Easiest Docker deploy, Python-native, free |
| Relational DB | PostgreSQL | ACID, proper migrations, audit trail |
| Job Queue | Redis + Celery | Persistent ingestion jobs survive restarts |
| PDF | pdfplumber + PyMuPDF | Best free table extraction + fast text |
| SQL Safety | sqlglot AST parse | Enforced at execution layer, not just prompt |
| Backend | FastAPI + SQLAlchemy (async) | Async-native, Pydantic validation |
| Frontend | React + Vite + Tailwind | Fast to build, clean UI |
| Logging | structlog | JSON structured logs, diagnose at 2am |

---

## Key Risks and Mitigations

| Risk | Mitigation |
|------|-----------|
| Ollama cold-start latency | Model pulled and warmed in entrypoint script before health passes |
| LLM returns invalid JSON | Retry loop (max 3) with stricter prompt; fallback error card |
| PDF table spanning pages | pdfplumber table continuity; document limitation if not solvable |
| Scanned PDFs (no text layer) | pytesseract OCR fallback; document clearly in README |
| OOM under parallel LLM calls | asyncio.Semaphore capped at OLLAMA_MAX_CONCURRENCY |
| Cross-tenant SQL injection | sqlglot AST + tenant-prefix table naming enforced at DB layer |

---

## Pivots Log

*(updated as decisions change during implementation)*

- No pivots yet - initial design.

---

## Next Steps

1. Write docker-compose.yml with all 6 services
2. Write Ollama entrypoint script
3. Write backend Dockerfile
4. Start FastAPI app skeleton
