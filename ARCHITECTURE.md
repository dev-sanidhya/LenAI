# LenAI - Architectural Decisions Record

Every significant decision made during implementation - what we chose, what we rejected, and why.

---

## 1. LLM: Ollama + Llama 3.1 8B

**Chose:** Ollama serving `llama3.1:8b`  
**Rejected:** OpenAI API, Anthropic API, Groq, HuggingFace Inference API

**Why:** The assignment explicitly requires a self-hosted LLM. Ollama is the cleanest way to run open-weight models in Docker - single container, OpenAI-compatible REST API, supports model warm-up at container start via the entrypoint script. Llama 3.1 8B is strong at instruction following, structured JSON output, and SQL generation. Mistral 7B is a valid alternative with roughly equivalent quality.

**Trade-off:** 8B parameter models are slower than cloud APIs (4-8s per response vs 0.5s) and require meaningful RAM (8GB+ for 8B quantized at Q4). We cap concurrency to 2 simultaneous requests to prevent OOM on modest hardware. If the host cannot run 8B, `phi3:mini` (3.8B) is the fallback - document this.

**What breaks at 10x load:** A single Ollama instance queues requests serially. At 10x, users wait in line. Fix: run multiple Ollama replicas behind a load balancer, or use a model serving framework like vLLM.

---

## 2. Embeddings: nomic-embed-text via Ollama

**Chose:** `nomic-embed-text` pulled and served through the same Ollama container  
**Rejected:** OpenAI text-embedding-3-small, sentence-transformers all-MiniLM-L6-v2 (standalone), Cohere Embed

**Why:** Keeping embeddings in the Ollama container means zero extra infrastructure. `nomic-embed-text` produces 768-dim embeddings, outperforms all-MiniLM on MTEB benchmarks, and runs locally. Swapping the embedding model later requires re-indexing ChromaDB - this is unavoidable with any embedding model change, so we record the model name with every chunk.

**Trade-off:** all-MiniLM-L6-v2 (standalone sentence-transformers) is faster and lighter. We chose nomic because it's meaningfully better on domain-specific retrieval, which matters for insurance/actuarial documents.

---

## 3. Re-ranking: cross-encoder/ms-marco-MiniLM-L-6-v2

**Chose:** Local cross-encoder re-ranking (sentence-transformers library)  
**Rejected:** Cohere Rerank API, no re-ranking at all

**Why:** Semantic similarity alone retrieves chunks that are semantically close but not necessarily relevant to the specific question. A cross-encoder scores each (query, chunk) pair jointly, which is dramatically more accurate. ms-marco-MiniLM-L-6-v2 is ~50MB, runs on CPU in <100ms for 20 candidates, and requires no external API. We retrieve top 20 from ChromaDB, re-rank to top 5, and pass those to the LLM.

**Trade-off:** Adds ~100-200ms latency per query. Worth it for the quality improvement.

---

## 4. Vector Database: ChromaDB

**Chose:** ChromaDB (self-hosted, Docker)  
**Rejected:** Qdrant, Milvus, Pinecone, Weaviate, pgvector

**Why:** ChromaDB has the simplest Docker deployment (single container, no external config) and a clean Python client. For this project's scale (hundreds to low thousands of document chunks per tenant), it is more than sufficient. The HTTP server mode (not the in-process mode) means it survives backend restarts independently.

**Trade-off:** Qdrant is more production-hardened with better filtering, sharding, and payload indexing. At real scale (millions of chunks), we would migrate to Qdrant. pgvector is attractive because it eliminates a service but it lacks HNSW-quality ANN performance for large collections. We document this in the README.

---

## 5. Relational Database: PostgreSQL

**Chose:** PostgreSQL with SQLAlchemy async ORM and Alembic migrations  
**Rejected:** SQLite, MySQL, MongoDB

**Why:** ACID transactions for the immutable audit trail. Alembic for proper schema versioning (not "create tables on first run"). The structured data uploaded by users (CSVs) is stored in dynamically-named tables within PostgreSQL - this lets us run real SQL against it for the Text-to-SQL feature without an extra database. SQLite is not suitable for multi-tenant concurrent writes.

**Migrations:** All schema changes go through numbered Alembic revisions. `alembic upgrade head` runs automatically on container start before the app accepts traffic.

**Audit record immutability clarification:** Core provenance fields (query_text, sql_queries, retrieved_chunks, raw_model_output, model versions) are written once and never modified. The user action fields (user_action, user_comment, action_at) are updated exactly once when the analyst makes a decision. A 409 is returned on any second attempt to update action fields. This matches the actual implementation - the ADR was previously overstated as "no UPDATE ever runs on this table."

---

## 6. SQL Sandboxing: sqlglot AST Validation

**Chose:** Parse every LLM-generated SQL with `sqlglot`, reject anything that is not a pure SELECT, enforce tenant-prefix table naming at the execution layer  
**Rejected:** Prompt-only safety ("only generate SELECT statements"), regex-based validation

**Why:** Prompt instructions are not a security control. A malicious or confused model can still generate DROP TABLE. sqlglot parses the AST and lets us traverse every node - we reject any statement type that is not SELECT, any reference to system tables (pg_catalog, information_schema), and any table not in the user's tenant namespace. This is enforced before the query reaches the database driver, not after.

**Implementation:** Every user's CSV tables are stored as `t_{tenant_id}_{upload_id}`. The sandbox checks every table reference against this pattern. No matches outside the pattern are allowed.

---

## 7. Job Queue: Redis + Celery

**Chose:** Celery with Redis as broker for ingestion jobs  
**Rejected:** Pure async background tasks (FastAPI BackgroundTasks), RQ, Postgres-backed queues

**Why:** File ingestion (PDF extraction, chunking, embedding 50+ pages) can take 30-120 seconds. FastAPI BackgroundTasks do not survive server restart - if the pod dies mid-ingestion, the job is lost silently. Celery + Redis means jobs are persisted in Redis, survive restarts, and can be retried. The upload endpoint returns the resource ID + job ID immediately; the client polls `GET /api/v1/ingest/status/csv/{dataset_id}` for tabular uploads and `GET /api/v1/ingest/status/pdf/{document_id}` for documents. Status transitions: `pending -> processing -> ready | failed`.

**Trade-off:** Adds a Redis container and Celery worker. For a simpler system, asyncio tasks + database-backed job state (polling the DB for status) is a valid middle ground. We chose Celery because the assignment explicitly requires that jobs survive server restart.

---

## 8. Memory Management: Sliding Window + Summarization

**Chose:** Keep last 4 full conversation turns in context; summarize all older turns into a single paragraph using the local LLM; store both in PostgreSQL  
**Rejected:** Pure sliding window (loses early context), raw append (hits token limit), vector retrieval of past turns (overkill for this use case)

**Why:** A pricing investigation conversation rarely needs verbatim recall of messages from 10 turns ago - it needs to know the topic, the datasets loaded, and key conclusions. Summarizing with the local LLM preserves semantic meaning while staying well under the context window. The summary is regenerated incrementally - when a new turn pushes us past the threshold, we summarize the oldest 4 turns and replace them with a summary node.

**Session persistence:** The full message list + current summary are stored in PostgreSQL. On reconnect, the session is loaded from the database. Memory survives server restart.

---

## 9. PDF Processing: pdfplumber + PyMuPDF

**Chose:** pdfplumber for table extraction, PyMuPDF (fitz) for text and layout  
**Rejected:** pypdf (no table support), PDFMiner (complex API), LlamaParse (external API)

**Why:** Tables in actuarial PDFs are the hardest part of this problem. pdfplumber's table extraction uses line detection and is more reliable than most alternatives for multi-column financial tables. PyMuPDF is fast for text blocks with coordinate metadata (useful for preserving reading order). We use both: fitz for overall layout, pdfplumber for table regions.

**Limitation documented:** Scanned PDFs (image-only, no text layer) require OCR. We include a pytesseract OCR fallback and document that table extraction quality degrades for scanned documents.

---

## 10. Chunking Strategy: 512-token fixed-size with 50-token overlap + table-as-unit

**Chose:** 512-token chunks with 50-token overlap for prose; tables extracted whole as single chunks regardless of size  
**Rejected:** Sentence-level chunking, semantic chunking (embedding-based boundaries), paragraph chunking

**Why:** 512 tokens is large enough to contain a complete reasoning unit (a paragraph + surrounding context) and small enough that the re-ranker can compare 20 candidates efficiently. The 50-token overlap prevents a sentence from being split cleanly at a boundary and losing context from both sides.

Tables are a special case. Splitting a table mid-row destroys its meaning. We extract tables with pdfplumber and store each table as a single chunk with metadata `{"type": "table", "page": N, "table_index": M}`. If a table exceeds 1500 tokens, we split by row groups (every 20 rows) and note the continuation.

---

## What We Intentionally Cut

| Feature | Reason |
|---------|--------|
| User accounts + RBAC | Auth model shipped: single API key per tenant exchanged for a 24h HS256 JWT carrying a `tenant_id` claim. Tenant isolation enforced at every query (PostgreSQL tenant column + ChromaDB metadata filter). User accounts, role claims, and refresh tokens are the next step but not in scope here. |
| Refresh token rotation | Single short-lived access token only. User re-authenticates on expiry. |
| Multi-tenancy UI (org switching) | Tenant isolation is enforced at DB + ChromaDB level; the UI shows single-tenant. |
| Streaming LLM responses | Ollama supports streaming; wiring it through WebSockets adds complexity. Polling works for demo. |
| Fine-tuned model | Domain fine-tuning on actuarial text would improve quality. Out of scope for 2-3 day timeline. |
| PDF OCR (scanned pages) | pytesseract fallback exists but quality is not guaranteed. Documented. |
| Horizontal scaling | Single Ollama instance. Scaling path: vLLM + multiple replicas. Documented. |

---

## What Breaks First at 10x Load

1. **Ollama** - single instance, serial inference. Fix: vLLM with tensor parallelism or multiple Ollama replicas.
2. **ChromaDB** - single-node, no sharding. Fix: Qdrant cluster or managed Weaviate.
3. **Celery worker** - single worker process. Fix: increase worker replicas in Docker Compose.
4. **PostgreSQL** - connection pool exhaustion. Fix: PgBouncer connection pooler in front.

The current architecture handles ~10-20 concurrent users comfortably. Beyond that, Ollama is the bottleneck.
