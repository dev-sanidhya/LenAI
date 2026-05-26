# LenAI - Architecture and Production Design Rationale

This document is not an MVP diary. It explains the system as if we were preparing
to operate it for real analysts inside a regulated pricing workflow, with clear
statements about reliability, traceability, tenant isolation, and scaling limits.

The implementation in this repo is intentionally compact, but the design posture
is production-first:
- Every analyst decision is auditable.
- Every retrieval path is tenant-scoped.
- Every generated SQL query is validated before execution.
- Every major dependency is health-checked before traffic is accepted.
- Every major shortcut is called out explicitly with its operational consequence.

---

## 1. System Shape

### Deployed services

The local stack is six services:

```text
Frontend (React + Vite + Nginx)
        |
        v
Backend (FastAPI)
  |        |         |         |
  v        v         v         v
Postgres  ChromaDB  Ollama   Redis/Celery
```

### Why this shape

We split the system by responsibility, not by hype:
- `FastAPI` owns request orchestration, auth, audit writes, and API contracts.
- `PostgreSQL` owns structured truth: datasets, documents, sessions, chat history, and audit records.
- `ChromaDB` owns semantic retrieval over document chunks.
- `Ollama` owns both generation and embedding so no external model provider is required.
- `Redis + Celery` exist to separate long-running ingestion from request handling.
- `Nginx` serves a static frontend with a minimal operational footprint.

This is not a microservices architecture for its own sake. It is the smallest
decomposition that gives us fault boundaries between:
- synchronous analyst interactions,
- asynchronous ingestion,
- relational state,
- vector search,
- and model inference.

---

## 2. Product Posture

### What kind of product this is

LenAI is not positioned as a chatbot demo. It is a pricing intelligence system
for analysts who need:
- evidence-backed recommendations,
- reproducible outputs,
- session continuity,
- and a defensible audit trail.

That changes the architecture materially. A generic chat app can tolerate
opaque model outputs. A pricing recommendation product cannot.

### Design principles

We built around five principles:

1. **Traceability over cleverness**
   Every recommendation stores its evidence inputs, raw model output, SQL
   queries, model versions, and user action.

2. **Isolation over convenience**
   Tenants are scoped in PostgreSQL, JWT claims, dataset table naming, and
   Chroma metadata filters.

3. **Operational honesty over fake guarantees**
   We document where the local stack is production-shaped and where it is
   still single-node.

4. **Deterministic guardrails around nondeterministic models**
   LLMs can generate text; the system still validates SQL, normalizes output,
   and constrains execution.

5. **Degradation before corruption**
   If retrieval fails, we return low-confidence output. We do not silently
   invent evidence or skip provenance.

---

## 3. LLM Layer: Ollama

### Chose

Self-hosted `Ollama` for:
- text generation,
- embeddings,
- local-only operation.

### Rejected

- OpenAI / Anthropic / Cohere APIs
- managed inference endpoints
- separate generation and embedding providers

### Why

The product requirement is strong data control. Pricing, underwriting, and
actuarial materials are exactly the kind of internal documents teams are
reluctant to send to third-party hosted inference APIs. Ollama gives us:
- a simple Docker deployment,
- a stable local HTTP API,
- model warm-up at startup,
- and a direct path to air-gapped or VPC-only deployment patterns later.

### Implemented operating model

- LLM model: configurable through `.env`
- embedding model: configurable through `.env`
- readiness checks verify model availability before the backend is considered ready
- generation concurrency is explicitly capped to prevent host OOM

### Production reading

The current repo proves the control plane, not infinite throughput. A single
Ollama instance is a valid starting point for an internal pilot or small team,
but the production path is:
- multiple inference replicas,
- centralized model management,
- and eventually a higher-throughput serving layer such as `vLLM`.

---

## 4. Retrieval Architecture: ChromaDB + Re-ranking

### Chose

- `ChromaDB` for vector storage
- `nomic-embed-text` for local embeddings
- `cross-encoder/ms-marco-MiniLM-L-6-v2` for re-ranking

### Why

This gives us a practical two-stage retrieval architecture:
1. fast approximate recall from Chroma,
2. precise ranking by a cross-encoder before synthesis.

That matters because actuarial and policy documents often contain many chunks
that are semantically similar but operationally different. Re-ranking reduces
the risk of citing nearby but irrelevant text.

### Important implementation details

- Chunks store `tenant_id`, `document_id`, `page`, `type`, and `chunk_index`
- Chroma queries always include tenant scoping
- single-document queries use an explicit `$and` filter shape compatible with Chroma
- the cross-encoder is loaded lazily, not at API startup

### Why lazy load the cross-encoder

Preloading the cross-encoder makes first-query latency better, but it also
front-loads significant memory pressure. In this repo we chose startup
stability over cold-start elegance:
- backend starts reliably on modest hardware,
- the first retrieval query pays the warm-up cost,
- subsequent requests are fast.

That is a production-minded trade-off for constrained environments. It avoids
turning the API into a fragile process that crashes before serving traffic.

### Scaling path

At large scale, `Qdrant` is the likely migration target because it offers
better filtering, clustering, and operational maturity. Chroma is acceptable
for the current scope because the product value here is in the workflow, not
in billion-vector retrieval.

---

## 5. Relational Core: PostgreSQL

### Chose

`PostgreSQL` with:
- SQLAlchemy async ORM
- Alembic migrations

### Why

Postgres is the operational backbone of the system:
- uploaded tabular datasets become SQL-queryable tables,
- document and dataset records are persisted with status,
- chat sessions survive restart,
- audit records are immutable in their core provenance fields.

This is the correct storage model for a product that must explain how it
arrived at a recommendation.

### Why not SQLite

SQLite is fine for prototypes. It is the wrong database for:
- concurrent analyst usage,
- write-heavy audit capture,
- job status transitions,
- and dynamic table creation with multiple active sessions.

### Migration posture

Schema changes go through Alembic and run at container start before the API
accepts traffic. That is deliberate. A “works on my machine” approach to schema
management is unacceptable once auditability matters.

---

## 6. Tabular Data Ingestion

### Chose

Uploaded CSV/Excel files are materialized into tenant-scoped Postgres tables.

### Why

We want real SQL over uploaded business data, not simulated analytics over a
pandas dataframe hidden in process memory. Persisting datasets into Postgres
gives us:
- proper SQL semantics,
- multi-session reuse,
- restart durability,
- and a stable base for audit logging.

### Implementation details

- files are hash-deduplicated
- columns are normalized to safe SQL identifiers
- schema inference records dtype, null rates, distinct counts, and outliers
- table names follow `t_{tenant_short}_{dataset_short}`

### Product mindset

We intentionally store more than raw rows. We also store inferred schema and
column tags because real analyst workflows need interpretable datasets, not
just storage. This is the start of a governed data workspace, not a file dump.

---

## 7. PDF Ingestion and Document Preparation

### Chose

- `PyMuPDF` for text extraction
- `pdfplumber` for table extraction
- `pytesseract` as OCR fallback

### Why

Actuarial memos and pricing documents are not clean markdown files. They are
usually PDFs with mixed prose, tables, appendices, and occasional scanned
pages. A production-shaped system needs differentiated handling:
- prose should chunk with overlap,
- tables should preserve row integrity,
- scanned pages need best-effort OCR.

### Chunking policy

- prose: ~512-token chunks with overlap
- tables: preserved as units where possible
- very large tables: split by row groups

### Reliability improvement implemented

The chunker previously had an end-of-document loop bug that could stall PDF
ingestion on certain inputs. That is now fixed. This is exactly why ingestion
must be treated as an operational subsystem with status tracking and tests,
not just helper code behind an upload button.

---

## 8. Asynchronous Work: Celery, Redis, and Inline Fallback

### Intended production design

The primary design is:
- API receives upload
- API persists metadata and job state
- Celery worker performs ingestion
- client polls status endpoints

This is the correct production model because ingestion can be slow and should
not block API workers.

### Why Celery + Redis

We rejected “just run it in the request” because:
- PDF extraction and embedding can take significant time,
- failures need explicit job states,
- request latencies must stay bounded,
- and ingestion throughput should scale separately from API throughput.

### Important implementation nuance

This repo also supports `INGEST_INLINE=true`, which runs ingestion via FastAPI
`BackgroundTasks` inside the backend process.

That is not the ideal production path. It exists because local and
memory-constrained environments can make Celery less reliable than a single
process execution model. The production-minded part is not pretending this is
equivalent. We document the trade-off clearly:
- `Celery` is the durable queue path
- `inline` is the safe demo/local fallback
- inline jobs do not have the same crash resilience guarantees

### Additional hardening implemented

If an identical upload is found in a non-ready state while inline mode is on,
the system now requeues it instead of leaving the document stranded in
`processing`. That is a recovery behavior, not just a convenience patch.

---

## 9. SQL Generation and Execution Safety

### Chose

LLM-generated SQL is treated as untrusted input.

We validate it with `sqlglot` before execution and reject anything that is not
a permitted `SELECT`.

### Rejected

- prompt-only instructions
- regex-only validation
- “trust the model” execution

### Why

In a regulated pricing workflow, the model is not allowed to be the security
boundary. The system must enforce:
- read-only query shape,
- no system tables,
- no cross-schema access,
- no access to other tenants’ uploaded tables.

### Additional hardening implemented

The smaller local model occasionally returns SQL wrapped in markdown or with
trailing text. We now normalize that output before validation. That keeps the
system robust to model formatting variance without weakening the safety model.

This is a good example of production thinking: the model is allowed to be messy;
the execution layer is not.

---

## 10. Query Synthesis and Recommendation Output

### Chose

Hybrid reasoning:
- RAG over document evidence
- SQL over uploaded datasets
- synthesis pass that combines both

### Why

A pricing recommendation is rarely defensible from just one source:
- documents explain policy, regulation, and narrative context
- tabular data provides observed claims and pricing evidence

The product must surface both. If they conflict, the system should record the
conflict explicitly rather than pretending the answer is certain.

### Output shape

Each query returns:
- recommendation action,
- confidence and rationale,
- document evidence,
- SQL evidence,
- reasoning steps,
- uncertainty sources,
- audit record ID,
- session ID.

This is structured because downstream analyst action matters more than chat
fluency. A product team can build review workflows, approvals, and committee
exports on top of this contract.

---

## 11. Memory and Session Continuity

### Chose

- sliding window for recent turns
- summary compression for older context
- persisted sessions in Postgres

### Why

Pricing work is iterative. Analysts ask follow-up questions, compare segments,
and revisit earlier conclusions. Stateless Q&A would force them to restate the
entire working set every time.

### Implementation posture

- recent turns remain verbatim
- older turns are summarized
- session active datasets/documents are carried forward
- scenario runs can be marked `is_ephemeral` so they do not contaminate the
  main conversational timeline

That last point matters. Scenario analysis is synthetic by design. Letting
hypothetical assumptions bleed into the primary session history would be a
product integrity failure.

---

## 12. Authentication and Tenant Isolation

### Chose

- one API key per tenant
- exchange for short-lived JWT
- frontend stores JWT in memory only

### Why

This is a deliberate middle ground:
- simpler than a full identity platform,
- materially safer than embedding a long-lived secret in the browser,
- and sufficient to enforce tenant-scoped access server-side.

### Tenant isolation layers

Isolation is not a single check. It exists in multiple places:
- JWT carries `tenant_id`
- API routes scope DB queries by `tenant_id`
- uploaded SQL tables are tenant namespaced
- Chroma metadata includes `tenant_id`
- retrieval filters scope by tenant
- audit and session records are tenant-bound

That redundancy is intentional. Production-grade isolation should survive a
single missed check better than a single-boundary design.

---

## 13. Auditability as a First-Class Feature

### Chose

Every query produces a persisted audit record, not just a UI response.

### Why

This is the most important product decision in the system. If a pricing analyst
acts on a recommendation, the organization must be able to answer:
- what question was asked,
- what datasets and documents were active,
- what the model saw,
- what SQL ran,
- what evidence was retrieved,
- what recommendation was produced,
- and what human action followed.

### Immutability policy

Core provenance is written once:
- query text
- active assets
- SQL trace
- retrieval trace
- raw model output
- recommendation payload
- model identifiers

User action fields are append-once in practice:
- accept / reject / review
- optional comment
- action timestamp

This is a realistic audit model. It preserves recommendation provenance while
allowing a single explicit analyst decision to be attached afterward.

---

## 14. Health, Readiness, and Operational Behavior

### Chose

Separate operational endpoints:
- `/health` for liveness
- `/ready` for dependency readiness
- `/metrics` for Prometheus scraping

### Why

A container being alive is not the same as the product being usable. The
backend should not take traffic until:
- Postgres is reachable,
- Chroma is reachable,
- Ollama is reachable,
- required models are loaded.

That distinction is basic but important. Many “working” AI apps are only
process-alive. This one is dependency-aware before it claims readiness.

### Metrics posture

The repo includes request counters and latency histograms. That is not full
observability, but it is the right starting point:
- establish request-level telemetry early,
- then add job metrics, retrieval metrics, and model latency breakdowns as the
  system matures.

---

## 15. Runtime Configuration Decisions

### Backend worker count

The verified working runtime uses a single uvicorn worker in the backend image.

### Why

Multiple workers sound more production-like, but on constrained local hardware
they increase:
- model memory pressure,
- duplicated warm state,
- and failure surface for ingestion-heavy flows.

Running one worker here is a stability-first choice. Real production scaling
would come from:
- more API replicas,
- separate inference capacity,
- and an external load balancer,
not from blindly increasing workers inside one small container.

### Celery pool choice

The worker uses `--pool=solo`.

That is again a stability-first decision. Prefork looks more scalable on paper
but caused memory pressure in this environment. Solo mode is slower, but it is
predictable and avoids a fake throughput claim that collapses under real usage.

---

## 16. What We Intentionally Did Not Build Yet

These are not forgotten features. They are explicit boundary lines.

| Feature | Current position | Production path |
|---------|------------------|-----------------|
| Full user identity and RBAC | Tenant API key -> JWT only | Add users, roles, SSO/OIDC, scoped permissions |
| Refresh tokens | Re-authenticate after expiry | Add rotating refresh token flow |
| Streaming responses | Request/response only | Add SSE or WebSocket streaming from Ollama through API |
| Strong OCR guarantees | Best-effort pytesseract fallback | Managed OCR or document intelligence pipeline |
| HA queueing | Single Redis + single Celery worker | Managed broker and multiple worker replicas |
| HA vector store | Single Chroma node | Qdrant or another clustered vector service |
| Multi-tenant org UI | Single-tenant frontend posture | org switcher, asset scoping, admin views |
| Policy and prompt governance UI | prompt version is stored, not managed visually | internal prompt registry and approval workflow |

The key point: these are roadmap items, not architectural blind spots.

---

## 17. Failure Order at 10x Load

If usage increases by an order of magnitude, the system breaks in this order:

1. **Ollama inference throughput**
   One local model server becomes the queueing bottleneck first.

2. **Cross-encoder memory/latency**
   Re-ranking remains valuable, but it becomes a more expensive per-query step.

3. **Single-node Chroma**
   Filtering and query concurrency become limiting.

4. **Single worker ingestion throughput**
   Bulk uploads back up behind long embedding jobs.

5. **Postgres connection pressure**
   Especially once API replicas increase.

### Scale plan

The production scale-out path is straightforward:
- move inference to a dedicated serving tier,
- move vector storage to a stronger clustered engine,
- scale API replicas horizontally,
- front Postgres with pooling,
- add queue metrics and worker autoscaling.

Nothing in the current codebase blocks that evolution. That is the real point
of this architecture: it starts simple without trapping the product in demo-only
decisions.

---

## 18. Bottom Line

This repo is compact, but the design intent is not.

We are not presenting LenAI as:
- a chatbot with files,
- a notebook wrapped in an API,
- or a hackathon MVP dressed up with AI language.

We are presenting it as an analyst-facing system with:
- explicit provenance,
- constrained execution,
- restart-aware ingestion,
- tenant isolation,
- session continuity,
- and a credible path from local deployment to production operation.

That is the product mindset behind the architecture.
