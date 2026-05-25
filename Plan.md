# LenAI - Pricing Intelligence Platform
## Implementation Plan

**Assignment:** Insurance / Banking Pricing Intelligence Product  
**Deadline:** 2-3 days from May 23, 2025  
**Standard:** Production-ready on day one

---

## Current Status

**Phase:** Core complete - all 6 backend services + full frontend shipped (4 commits, pushed to main)

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

### Phase 1 - Foundation (DONE)
- [x] Git setup, .gitignore, .env.example
- [x] Plan.md and ARCHITECTURE.md
- [x] docker-compose.yml (full 6-service stack)
- [x] Ollama entrypoint script (model warm-up before health check passes)
- [x] Backend + Worker Dockerfiles

### Phase 2 - Backend Core (DONE)
- [x] FastAPI app with structlog structured logging
- [x] PostgreSQL models (Dataset, Document, ChatSession, ChatMessage, AuditRecord)
- [x] Alembic migrations (001_initial_schema)
- [x] Config management (pydantic-settings from .env)
- [x] Health (/health) and readiness (/ready) endpoints
- [x] API key auth + tenant_id derivation

### Phase 3 - Data Ingestion (DONE)
- [x] CSV/Excel ingester: schema inference, outlier detection, idempotent upload
- [x] PDF ingester: pdfplumber tables + PyMuPDF text + pytesseract OCR fallback
- [x] Chunking strategy: 512/50 prose + table-as-unit
- [x] Embedding via Ollama nomic-embed-text
- [x] ChromaDB storage with upsert dedup
- [x] Redis + Celery worker for persistent ingestion jobs

### Phase 4 - Hybrid Reasoning Engine (DONE)
- [x] RAG retriever: ChromaDB semantic search + cross-encoder rerank
- [x] SQL agent: LLM generates SELECT, sqlglot AST validation, sandboxed execution
- [x] Hybrid synthesizer: parallel retrieval, conflict surfacing
- [x] JSON output with retry on parse failure

### Phase 5 - Memory System (DONE)
- [x] Within-session: sliding window (last 4 turns)
- [x] Cross-session: summarization via local LLM, stored in PostgreSQL
- [x] Dataset/document context persisted per session

### Phase 6 - Product Layer (DONE)
- [x] Scenario comparison (2-3 assumption sets)
- [x] Immutable audit trail (AuditRecord table, JSON + PDF export via reportlab)
- [x] Accept/Reject (comment required)/Review actions

### Phase 7 - Frontend (DONE)
- [x] React 18 + Vite + Tailwind
- [x] Upload zone (drag-drop, polling, status updates)
- [x] Query interface with session memory indicator
- [x] Dataset/document multi-select
- [x] Scenario comparison mode (2-3 side-by-side cards)
- [x] Recommendation card (full evidence panel + reasoning trace)
- [x] Audit log with expandable records + export buttons
- [x] Nginx with SPA routing + API proxy

### Phase 8 - Production Hardening (DONE)
- [x] Ollama concurrency cap (asyncio.Semaphore)
- [x] SIGTERM graceful shutdown handler
- [x] structlog JSON logging in production mode
- [x] Prometheus metrics middleware (request count, latency, error rate)
- [x] Resource limits in Docker Compose (mem_limit per service)
- [x] README finalized with audit JSON schema
- [ ] Demo dataset generation (synthetic motor insurance CSV + actuarial PDF)
- [ ] Video demo recorded

### Next Steps (Day 3)
- [ ] Generate synthetic demo data (Python script producing motor_policy_book.csv + actuarial_memo.pdf)
- [ ] Add .env with working defaults so `docker compose up` just works
- [ ] End-to-end smoke test (cold start -> upload -> query -> audit export)
- [ ] Record video demo

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
