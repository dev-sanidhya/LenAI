#!/bin/bash
# =============================================================================
# LenAI - End-to-end demo
# Run this AFTER `docker compose up -d` is healthy.
# All steps print clearly; replayable for a video recording.
# =============================================================================

set -e

API="${API:-http://localhost:8000}"
API_KEY="${API_KEY:-dev-api-key-change-in-production}"
CSV="${CSV:-test_fixtures/demo_motor_policies.csv}"
PDF="${PDF:-test_fixtures/demo_actuarial_memo.pdf}"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

step() { echo -e "\n${CYAN}===== $1 =====${NC}"; }
ok()   { echo -e "${GREEN}OK${NC} $1"; }
warn() { echo -e "${YELLOW}> $1${NC}"; }

# -----------------------------------------------------------------------------
step "1) Wait for backend to be ready"
until curl -sf "$API/ready" >/dev/null 2>&1; do sleep 2; done
curl -s "$API/ready" | python -m json.tool
ok "backend healthy"

# -----------------------------------------------------------------------------
step "2) Exchange API key for short-lived JWT"
TOKEN=$(curl -s -X POST "$API/api/v1/auth/token" \
  -H "Content-Type: application/json" \
  -d "{\"api_key\":\"$API_KEY\"}" \
  | python -c "import json,sys; print(json.load(sys.stdin)['access_token'])")
AUTH="Authorization: Bearer $TOKEN"
echo "JWT issued (${#TOKEN} chars). API key never reused after this point."
ok "auth done"

# -----------------------------------------------------------------------------
step "3) Upload demo motor policies CSV"
DS=$(curl -s -X POST "$API/api/v1/ingest/csv" \
  -H "$AUTH" -F "file=@$CSV" \
  | python -c "import json,sys; r=json.load(sys.stdin); print(r['dataset_id'])")
echo "dataset_id: $DS"
warn "polling ingest/status/csv until ready"
until curl -s -H "$AUTH" "$API/api/v1/ingest/status/csv/$DS" | grep -q '"ready"\|"failed"'; do sleep 2; done
curl -s -H "$AUTH" "$API/api/v1/ingest/status/csv/$DS" | python -c "
import json, sys
r = json.load(sys.stdin)
print(f\"status: {r['status']}  rows: {r['row_count']}  cols: {r['column_count']}\")
print('columns inferred:')
for col, info in (r['schema_info'] or {}).items():
    print(f\"  - {col:<20} {info['dtype']:<10} nulls={info['null_count']}\")
"
ok "CSV ready"

# -----------------------------------------------------------------------------
step "4) Upload demo actuarial PDF"
DOC=$(curl -s -X POST "$API/api/v1/ingest/pdf" \
  -H "$AUTH" -F "file=@$PDF" \
  | python -c "import json,sys; r=json.load(sys.stdin); print(r['document_id'])")
echo "document_id: $DOC"
warn "polling ingest/status/pdf until chunks are embedded"
until curl -s -H "$AUTH" "$API/api/v1/ingest/status/pdf/$DOC" | grep -q '"ready"\|"failed"'; do sleep 3; done
curl -s -H "$AUTH" "$API/api/v1/ingest/status/pdf/$DOC" | python -c "
import json, sys
r = json.load(sys.stdin)
print(f\"status: {r['status']}  pages: {r['page_count']}  chunks: {r['chunk_count']}  ocr: {r['ocr_used']}\")
"
ok "PDF ready"

# -----------------------------------------------------------------------------
step "5) Pricing query - hybrid RAG + SQL reasoning"
echo "Question: 'Should we reprice motor insurance for under-25 drivers in the Northern region?'"
RESP=$(curl -s -X POST "$API/api/v1/query" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d "{
    \"question\": \"Should we reprice motor insurance for under-25 drivers in the Northern region?\",
    \"dataset_ids\": [\"$DS\"],
    \"document_ids\": [\"$DOC\"]
  }")
echo "$RESP" | python -c "
import json, sys
r = json.load(sys.stdin)
rec = r['recommendation']
print()
print(f\"ACTION:     {rec.get('action')}\")
print(f\"CONFIDENCE: {rec.get('confidence')}  ({rec.get('confidence_rationale')})\")
print()
print('REASONING STEPS:')
for i, s in enumerate(rec.get('reasoning_steps') or [], 1):
    print(f'  {i}. {s}')
print()
print(f\"SQL queries run: {len(r['reasoning_trace']['sql_queries'])}\")
for q in r['reasoning_trace']['sql_queries']:
    sql = q.get('sql','')[:200]
    print(f\"  - {sql}  ({q.get('row_count',0)} rows)\")
print(f\"Document chunks retrieved: {len(r['reasoning_trace']['retrieved_chunks'])}\")
print()
print(f\"audit_record_id: {r['audit_record_id']}\")
print(f\"session_id:      {r['session_id']}\")
"
AUDIT=$(echo "$RESP" | python -c "import json,sys; print(json.load(sys.stdin)['audit_record_id'])")
SESSION=$(echo "$RESP" | python -c "import json,sys; print(json.load(sys.stdin)['session_id'])")
echo "$AUDIT" > /tmp/lenai_audit.txt
echo "$SESSION" > /tmp/lenai_session.txt
ok "recommendation generated"

# -----------------------------------------------------------------------------
step "6) Submit Accept action on the recommendation"
curl -s -X POST "$API/api/v1/query/$AUDIT/action" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"action":"accept"}' | python -m json.tool
ok "decision logged"

# -----------------------------------------------------------------------------
step "7) Follow-up query in the same session (memory continuity)"
echo "Question: 'And how does that compare to drivers over 65?'"
curl -s -X POST "$API/api/v1/query" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d "{
    \"question\": \"And how does that compare to drivers over 65?\",
    \"session_id\": \"$SESSION\"
  }" | python -c "
import json, sys
r = json.load(sys.stdin)
rec = r['recommendation']
print(f\"ACTION:     {rec.get('action')}\")
print(f\"CONFIDENCE: {rec.get('confidence')}\")
print('Session context was preserved - no need to re-state datasets.')
"
ok "session memory works"

# -----------------------------------------------------------------------------
step "8) Export audit record as JSON"
curl -s -H "$AUTH" "$API/api/v1/audit/$AUDIT/export/json" -o demo_audit.json
echo "Wrote demo_audit.json ($(wc -c < demo_audit.json) bytes)"
python -c "
import json
r = json.load(open('demo_audit.json'))
print(f\"keys: {list(r.keys())[:10]}...\")
print(f\"llm_model: {r['llm_model']}  embed_model: {r['embed_model']}  prompt: {r['prompt_version']}\")
print(f\"sql_queries: {len(r.get('sql_queries') or [])}  chunks: {len(r.get('retrieved_chunks') or [])}  user_action: {r['user_action']}\")
"
ok "audit JSON exported"

# -----------------------------------------------------------------------------
step "9) Export audit record as PDF (committee report)"
curl -s -H "$AUTH" "$API/api/v1/audit/$AUDIT/export/pdf" -o demo_recommendation.pdf
SIZE=$(wc -c < demo_recommendation.pdf)
echo "Wrote demo_recommendation.pdf ($SIZE bytes)"
head -c 4 demo_recommendation.pdf
echo "  <- '%PDF' magic confirms it is a valid PDF"
ok "audit PDF exported"

# -----------------------------------------------------------------------------
step "10) Cross-session memory check - list all sessions for this tenant"
curl -s -H "$AUTH" "$API/api/v1/sessions" | python -c "
import json, sys
sessions = json.load(sys.stdin)
print(f'Sessions persisted in PostgreSQL: {len(sessions)}')
for s in sessions[:3]:
    print(f\"  - {s['session_id'][:8]}... | {s['turn_count']} turns | datasets: {len(s['active_dataset_ids'])} | docs: {len(s['active_document_ids'])}\")
"
ok "session list works"

echo
echo -e "${GREEN}===== DEMO COMPLETE =====${NC}"
echo "Artifacts:"
echo "  demo_audit.json           - full reproducible audit record"
echo "  demo_recommendation.pdf   - pricing committee report"
