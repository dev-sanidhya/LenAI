# LenAI - Pricing Intelligence Platform

An AI co-pilot for insurance and banking pricing teams. Upload policy CSVs and actuarial PDFs, ask pricing questions in plain English, and get cited, auditable recommendations backed by a self-hosted LLM.

---

## Quick Start

```bash
cp .env.example .env
# Edit .env - set POSTGRES_PASSWORD at minimum
docker compose up --build
```

That's it. The stack takes 5-10 minutes on first run while Ollama pulls and warms the LLM. The frontend is available at http://localhost:3000.

**Note:** Ollama will download ~5GB of model weights on first run. The backend won't accept traffic until models are warmed (health check enforces this).

---

## Architecture

```
Frontend (React)  -->  Backend (FastAPI)  -->  Ollama (LLM + Embeddings)
                                          -->  ChromaDB (Vector Store)
                                          -->  PostgreSQL (Relational + Audit)
                                          -->  Redis + Celery (Job Queue)
```

Six Docker services, one command to start them all. See [ARCHITECTURE.md](ARCHITECTURE.md) for every technology decision with trade-offs.

---

## What It Does

### 1. Data Ingestion
- **CSV/Excel**: Schema inference, column tagging (feature/target/ignore), outlier detection, idempotent upload. Stored in PostgreSQL as tenant-namespaced tables.
- **PDF**: Layout-aware text extraction (PyMuPDF), table extraction (pdfplumber), OCR fallback for scanned pages (pytesseract). Chunked at 512 tokens with 50-token overlap. Tables kept whole. Embedded with `nomic-embed-text` via Ollama. Stored in ChromaDB.
- Re-uploading the same file never creates duplicates (hash-based dedup).

### 2. Hybrid Reasoning Engine
- **RAG**: Semantic search over ChromaDB (top 20), re-ranked by `cross-encoder/ms-marco-MiniLM-L-6-v2` (top 5). All local, no external API.
- **Text-to-SQL**: LLM generates SELECT queries, validated by sqlglot AST parser (only SELECT allowed, only user's own tables). Results fed back into the reasoning pass.
- **Synthesis**: Both retrieval paths run in parallel. Conflicts between document and data evidence are surfaced explicitly, never silently resolved.

### 3. Memory
- **Within-session**: Last 4 turns kept in full. Older turns summarized using the local LLM.
- **Cross-session**: Stored in PostgreSQL. Survives server restart. Loading a session ID restores full context.

### 4. Recommendation Cards
Structured output per query:
- Single-sentence action
- Confidence level (high/medium/low) with rationale
- Evidence panel: document chunks with page references, SQL results
- Reasoning trace: every step, every SQL query run
- Accept / Reject (comment required) / Request Review actions
- All actions logged in audit trail

### 5. Scenario Comparison
Run the same question under 2-3 different assumption sets. Results shown side-by-side with differences highlighted.

### 6. Immutable Audit Trail
Every query produces an audit record containing:
- Exact query text
- Dataset/document snapshot references (IDs active at query time)
- LLM model and prompt version
- Every SQL query generated and executed, with results
- Every document chunk retrieved, with similarity and rerank scores
- Raw LLM output before post-processing
- User's decision and comment

Exportable as structured JSON or formatted PDF.

---

## API Endpoints

### Authentication

All protected endpoints require a Bearer JWT in the `Authorization` header.

1. Exchange your API key for a short-lived JWT:
   ```bash
   curl -X POST http://localhost:8000/api/v1/auth/token \
     -H "Content-Type: application/json" \
     -d '{"api_key": "your-api-key"}'
   ```
   Response:
   ```json
   { "access_token": "eyJ...", "token_type": "bearer", "expires_in": 86400 }
   ```

2. Use the token on every subsequent request:
   ```bash
   curl http://localhost:8000/api/v1/ingest/datasets \
     -H "Authorization: Bearer eyJ..."
   ```

The API key never travels over the wire after the exchange. The JWT is signed
with `APP_SECRET_KEY`, contains a `tenant_id` claim derived from the API key,
and expires after 24 hours. The frontend stores the token in JS memory only
(no `localStorage`, no cookies) and clears it on page refresh or 401.

### Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/health` | public | Liveness check |
| GET | `/ready` | public | Readiness (503 if any dep is degraded) |
| GET | `/metrics` | public | Prometheus metrics |
| POST | `/api/v1/auth/token` | api_key | Exchange API key for JWT |
| POST | `/api/v1/ingest/csv` | Bearer | Upload CSV/Excel |
| POST | `/api/v1/ingest/pdf` | Bearer | Upload PDF |
| GET | `/api/v1/ingest/datasets` | Bearer | List datasets |
| GET | `/api/v1/ingest/documents` | Bearer | List documents |
| GET | `/api/v1/ingest/status/csv/{dataset_id}` | Bearer | Dataset ingestion status |
| GET | `/api/v1/ingest/status/pdf/{document_id}` | Bearer | Document ingestion status |
| PATCH | `/api/v1/ingest/csv/{dataset_id}/tags` | Bearer | Update column tags (feature/target/ignore) |
| POST | `/api/v1/query` | Bearer | Submit pricing query (set `is_ephemeral:true` for scenarios) |
| POST | `/api/v1/query/{id}/action` | Bearer | Accept/Reject/Review recommendation |
| GET | `/api/v1/audit` | Bearer | List audit records |
| GET | `/api/v1/audit/{id}` | Bearer | Get audit record |
| GET | `/api/v1/audit/{id}/export/json` | Export as JSON |
| GET | `/api/v1/audit/{id}/export/pdf` | Export as PDF |
| GET | `/api/v1/sessions` | List sessions |
| GET | `/api/v1/sessions/{id}` | Get session with memory |
| GET | `/metrics` | Prometheus metrics |

Full interactive docs at http://localhost:8000/docs.

---

## Audit Record Structure

```json
{
  "id": "uuid",
  "tenant_id": "string",
  "session_id": "uuid",
  "query_text": "Should we reprice motor insurance for under-25 drivers in the North?",
  "active_dataset_ids": ["uuid"],
  "active_document_ids": ["uuid"],
  "llm_model": "llama3.1:8b",
  "embed_model": "nomic-embed-text",
  "prompt_version": "v1.0",
  "sql_queries": [
    {
      "sql": "SELECT AVG(claim_frequency), region FROM t_abc_def WHERE age < 25 GROUP BY region",
      "rows": [...],
      "row_count": 4,
      "error": null
    }
  ],
  "retrieved_chunks": [
    {
      "text": "...",
      "metadata": { "document_id": "...", "page": 12, "type": "text" },
      "similarity_score": 0.91,
      "rerank_score": 0.87
    }
  ],
  "raw_model_output": "...",
  "recommendation": {
    "action": "Increase motor premium by 8-12% for under-25 drivers in the North",
    "confidence": "high",
    "confidence_rationale": "Strong signal from both data and regulatory document",
    "document_evidence": [...],
    "sql_evidence": [...],
    "conflicts": [],
    "reasoning_steps": [...],
    "uncertainty_sources": [...]
  },
  "user_action": "accept",
  "user_comment": null,
  "action_at": "2025-05-24T10:30:00Z",
  "created_at": "2025-05-24T10:29:45Z"
}
```

---

## RAG and Memory Design

See [ARCHITECTURE.md](ARCHITECTURE.md) for full rationale. Summary:

**Chunking:** 512-token fixed-size with 50-token overlap for prose. Tables extracted whole (pdfplumber), stored as single chunks regardless of size. Large tables (>1500 tokens) split by row groups of 20.

**Embedding:** `nomic-embed-text` via Ollama. 768-dim embeddings, outperforms all-MiniLM on domain-specific retrieval. Model name recorded with every chunk so re-indexing can be detected.

**Retrieval:** ChromaDB HNSW cosine similarity. Top 20 retrieved, re-ranked by `cross-encoder/ms-marco-MiniLM-L-6-v2` to top 5.

**Memory:** Sliding window of 4 turns. After 8 turns, older turns are summarized by the local LLM and stored as context_summary. Full message history preserved in chat_messages table.

---

## What Breaks First at 10x Load

1. **Ollama** (single instance, serial inference) - fix: vLLM with multiple replicas
2. **ChromaDB** (single-node, no sharding) - fix: Qdrant cluster
3. **Celery worker** (single process) - fix: increase replicas in docker-compose
4. **PostgreSQL** (connection pool) - fix: PgBouncer

Current architecture handles ~10-20 concurrent users. See ARCHITECTURE.md for scaling paths.

---

## What Was Intentionally Cut

| Feature | Why | Production path |
|---------|-----|-----------------|
| User accounts / RBAC | Single API key per tenant, exchanged for JWT | Add user table, password hashing, role claims on JWT |
| Refresh tokens | 24h JWT, user re-auths on expiry | Add `/auth/refresh` with refresh token rotation |
| Streaming responses | Adds WebSocket complexity | Ollama supports streaming, wire it up |
| Fine-tuned model | Out of scope | Domain fine-tune on actuarial corpora |
| Multi-tenant UI | Tenant isolation enforced at DB + ChromaDB query level | Add org switcher to frontend |
| OCR quality guarantees | pytesseract is best-effort for scanned PDFs | Use a dedicated OCR service (AWS Textract, Azure Document Intelligence) |

---

## Environment Variables

See [.env.example](.env.example) for all documented variables. Nothing is hardcoded. All secrets come from the `.env` file.

---

## Running Tests

```bash
cd backend
pip install -r requirements.txt
pytest tests/ -v
```

The SQL sandbox tests run without any external dependencies and verify that the security layer is enforced correctly.
