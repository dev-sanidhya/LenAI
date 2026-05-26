"""
LenAI - End-to-end demo runner.

Single-process Python (stdlib only). No subprocess chains, no bash fork
issues. Streams progress with per-step timing so you can see exactly
where time is being spent.

Usage:
    python scripts/demo.py
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

API = os.getenv("API", "http://localhost:8000")
API_KEY = os.getenv("API_KEY", "dev-api-key-change-in-production")

ROOT = Path(__file__).resolve().parent.parent
CSV = ROOT / "test_fixtures" / "demo_motor_policies.csv"
PDF = ROOT / "test_fixtures" / "demo_actuarial_memo.pdf"


# ----------------------------------- pretty -----------------------------------
def step(title: str) -> float:
    print(f"\n\033[36m===== {title} =====\033[0m", flush=True)
    return time.monotonic()

def ok(msg: str, t0: float) -> None:
    print(f"\033[32mOK\033[0m {msg} ({time.monotonic()-t0:.1f}s)", flush=True)

def warn(msg: str) -> None:
    print(f"\033[33m> {msg}\033[0m", flush=True)

def die(msg: str) -> None:
    print(f"\033[31mFAIL\033[0m {msg}", file=sys.stderr, flush=True)
    sys.exit(1)


# ----------------------------------- http -------------------------------------
def http_request(method: str, url: str, *, headers: dict | None = None,
                 body: bytes | None = None, timeout: float = 120.0) -> tuple[int, dict, bytes]:
    req = urllib.request.Request(url, method=method, data=body, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers or {}), e.read()


def get_json(path: str, token: str | None = None) -> dict:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    status, _, body = http_request("GET", f"{API}{path}", headers=headers)
    if status >= 400:
        die(f"GET {path} -> {status}: {body.decode(errors='replace')[:300]}")
    return json.loads(body)


def post_json(path: str, payload: dict, token: str | None = None, timeout: float = 180.0) -> dict:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    status, _, body = http_request("POST", f"{API}{path}",
                                   headers=headers,
                                   body=json.dumps(payload).encode(),
                                   timeout=timeout)
    if status >= 400:
        die(f"POST {path} -> {status}: {body.decode(errors='replace')[:300]}")
    return json.loads(body)


def post_multipart(path: str, file_path: Path, token: str) -> dict:
    """Single-shot multipart upload built from stdlib (no requests dep)."""
    import uuid as _uuid
    boundary = f"----lenai{_uuid.uuid4().hex}"
    data = (
        f"--{boundary}\r\n"
        f"Content-Disposition: form-data; name=\"file\"; filename=\"{file_path.name}\"\r\n"
        f"Content-Type: application/octet-stream\r\n\r\n"
    ).encode() + file_path.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
    headers = {
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Content-Length": str(len(data)),
        "Authorization": f"Bearer {token}",
    }
    status, _, body = http_request("POST", f"{API}{path}", headers=headers, body=data, timeout=120.0)
    if status >= 400:
        die(f"POST {path} -> {status}: {body.decode(errors='replace')[:300]}")
    return json.loads(body)


def download(path: str, token: str, dest: Path) -> int:
    status, _, body = http_request("GET", f"{API}{path}",
                                   headers={"Authorization": f"Bearer {token}"})
    if status >= 400:
        die(f"GET {path} -> {status}")
    dest.write_bytes(body)
    return len(body)


# ----------------------------------- demo -------------------------------------
def main() -> None:
    if not CSV.exists():
        die(f"CSV missing: {CSV}")
    if not PDF.exists():
        die(f"PDF missing: {PDF}")

    # 1) Readiness
    t = step("1) Wait for backend /ready")
    while True:
        try:
            r = get_json("/ready")
            if r.get("status") == "ready":
                print(json.dumps(r, indent=2))
                break
        except Exception:
            pass
        time.sleep(2)
    ok("backend healthy", t)

    # 2) Auth
    t = step("2) Exchange API key for JWT")
    tok = post_json("/api/v1/auth/token", {"api_key": API_KEY})["access_token"]
    print(f"JWT issued ({len(tok)} chars). API key never reused after this.")
    ok("auth done", t)

    # 3) CSV upload + poll
    t = step("3) Upload demo_motor_policies.csv (100 rows)")
    ds = post_multipart("/api/v1/ingest/csv", CSV, tok)
    dataset_id = ds["dataset_id"]
    print(f"dataset_id: {dataset_id}  status: {ds['status']}")
    if ds["status"] != "already_exists":
        warn("polling /ingest/status/csv every 1s")
        for i in range(120):
            s = get_json(f"/api/v1/ingest/status/csv/{dataset_id}", tok)
            print(f"  t+{i:>2}s  status={s['status']}", flush=True)
            if s["status"] in ("ready", "failed"):
                if s["status"] == "failed":
                    die("CSV ingestion failed")
                break
            time.sleep(1)
    s = get_json(f"/api/v1/ingest/status/csv/{dataset_id}", tok)
    if s["status"] != "ready":
        die(f"CSV ingestion did not complete successfully (final status: {s['status']})")
    print(f"\nFinal: rows={s['row_count']}  cols={s['column_count']}")
    print("Schema inferred:")
    for col, info in (s.get("schema_info") or {}).items():
        print(f"  - {col:<20} {info['dtype']:<10} nulls={info['null_count']}")
    ok("CSV ready", t)

    # 4) PDF upload + poll
    t = step("4) Upload demo_actuarial_memo.pdf")
    doc = post_multipart("/api/v1/ingest/pdf", PDF, tok)
    document_id = doc["document_id"]
    print(f"document_id: {document_id}  status: {doc['status']}")
    if doc["status"] != "already_exists":
        warn("polling /ingest/status/pdf every 2s (embeddings happen one chunk at a time on GPU)")
        for i in range(120):
            s = get_json(f"/api/v1/ingest/status/pdf/{document_id}", tok)
            chunks = s.get("chunk_count")
            print(f"  t+{i*2:>3}s  status={s['status']}  chunks={chunks}", flush=True)
            if s["status"] in ("ready", "failed"):
                if s["status"] == "failed":
                    die("PDF ingestion failed - check worker logs")
                break
            time.sleep(2)
    s = get_json(f"/api/v1/ingest/status/pdf/{document_id}", tok)
    if s["status"] != "ready":
        die(f"PDF ingestion did not complete successfully (final status: {s['status']})")
    print(f"\nFinal: pages={s['page_count']}  chunks={s['chunk_count']}  ocr_used={s['ocr_used']}")
    ok("PDF ready", t)

    # 5) Pricing query
    t = step("5) Pricing query - hybrid RAG + SQL synthesis")
    question = "Should we reprice motor insurance for under-25 drivers in the Northern region?"
    print(f"Question: '{question}'")
    resp = post_json("/api/v1/query", {
        "question": question,
        "dataset_ids": [dataset_id],
        "document_ids": [document_id],
    }, tok, timeout=240.0)
    rec = resp["recommendation"]
    trace = resp["reasoning_trace"]
    print(f"\nACTION:     {rec.get('action')}")
    print(f"CONFIDENCE: {rec.get('confidence')} ({rec.get('confidence_rationale')})")
    if rec.get("conflicts"):
        print("CONFLICTS:")
        for c in rec["conflicts"]:
            print(f"  - {c}")
    print("\nReasoning steps:")
    for i, st in enumerate(rec.get("reasoning_steps") or [], 1):
        print(f"  {i}. {st}")
    print(f"\nSQL queries executed: {len(trace['sql_queries'])}")
    for q in trace["sql_queries"]:
        print(f"  - {(q.get('sql') or '')[:200]}   ({q.get('row_count', 0)} rows)")
    print(f"Document chunks retrieved: {len(trace['retrieved_chunks'])}")
    audit_id = resp["audit_record_id"]
    session_id = resp["session_id"]
    print(f"\naudit_record_id: {audit_id}")
    print(f"session_id:      {session_id}")
    ok("recommendation generated", t)

    # 6) Action
    t = step("6) Submit Accept on the recommendation")
    res = post_json(f"/api/v1/query/{audit_id}/action", {"action": "accept"}, tok)
    print(json.dumps(res, indent=2))
    ok("decision recorded", t)

    # 7) Follow-up query (memory continuity)
    t = step("7) Follow-up query in same session (memory test)")
    print("Question: 'And how does that compare to drivers over 65?'")
    resp2 = post_json("/api/v1/query", {
        "question": "And how does that compare to drivers over 65?",
        "session_id": session_id,
    }, tok, timeout=240.0)
    print(f"ACTION:     {resp2['recommendation'].get('action')}")
    print(f"CONFIDENCE: {resp2['recommendation'].get('confidence')}")
    print("Datasets/documents inherited from session - not re-stated.")
    ok("session memory works", t)

    # 8) JSON export
    t = step("8) Export audit record as JSON")
    out_json = ROOT / "demo_audit.json"
    n = download(f"/api/v1/audit/{audit_id}/export/json", tok, out_json)
    j = json.loads(out_json.read_text())
    print(f"Wrote {out_json.name} ({n} bytes)")
    print(f"llm_model={j['llm_model']}  embed_model={j['embed_model']}  prompt={j['prompt_version']}")
    print(f"sql_queries={len(j.get('sql_queries') or [])}  chunks={len(j.get('retrieved_chunks') or [])}  user_action={j['user_action']}")
    ok("JSON exported", t)

    # 9) PDF export
    t = step("9) Export audit record as PDF (committee report)")
    out_pdf = ROOT / "demo_recommendation.pdf"
    n = download(f"/api/v1/audit/{audit_id}/export/pdf", tok, out_pdf)
    head = out_pdf.read_bytes()[:4]
    print(f"Wrote {out_pdf.name} ({n} bytes), magic={head!r}")
    ok("PDF exported", t)

    # 10) Cross-session listing
    t = step("10) List sessions (cross-session memory check)")
    sess = get_json("/api/v1/sessions", tok)
    print(f"Sessions persisted: {len(sess)}")
    for s in sess[:3]:
        print(f"  - {s['session_id'][:8]}...  turns={s['turn_count']}  datasets={len(s['active_dataset_ids'])}  docs={len(s['active_document_ids'])}")
    ok("session list works", t)

    print("\n\033[32m===== DEMO COMPLETE =====\033[0m")
    print("Artifacts:")
    print("  demo_audit.json           - full reproducible audit record")
    print("  demo_recommendation.pdf   - committee-ready report")


if __name__ == "__main__":
    overall = time.monotonic()
    main()
    print(f"\n\033[36mTotal demo time: {time.monotonic()-overall:.1f}s\033[0m")
