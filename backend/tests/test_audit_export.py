"""
Audit record serialization and PDF generation tests.
These test the PDF/JSON export logic without needing a live database.
"""
import pytest
import json
import uuid
from datetime import datetime
from unittest.mock import MagicMock
from app.api.routes.audit import _serialize_record, _build_pdf


def make_audit_record(**kwargs):
    record = MagicMock()
    record.id = uuid.uuid4()
    record.tenant_id = "test-tenant"
    record.session_id = uuid.uuid4()
    record.recommendation_id = uuid.uuid4()
    record.query_text = "Should we reprice motor insurance for under-25s?"
    record.active_dataset_ids = ["ds-1"]
    record.active_document_ids = ["doc-1"]
    record.llm_model = "llama3.1:8b"
    record.embed_model = "nomic-embed-text"
    record.prompt_version = "v1.0"
    record.sql_queries = [{"sql": "SELECT avg(premium) FROM t_abc WHERE age < 25", "rows": [], "row_count": 0, "error": None}]
    record.retrieved_chunks = [{"text": "Motor claims for under-25s are 40% higher.", "metadata": {"document_id": "doc-1", "page": 5}, "rerank_score": 0.92}]
    record.raw_model_output = '{"action": "Increase by 10%"}'
    record.recommendation = {"action": "Increase motor premium by 10% for under-25s", "confidence": "high", "confidence_rationale": "Strong data signal", "conflicts": [], "reasoning_steps": ["Step 1", "Step 2"], "uncertainty_sources": []}
    record.user_action = "accept"
    record.user_comment = None
    record.action_at = datetime(2025, 5, 24, 10, 30, 0)
    record.scenario_label = None
    record.scenario_assumptions = None
    record.created_at = datetime(2025, 5, 24, 10, 29, 0)
    for k, v in kwargs.items():
        setattr(record, k, v)
    return record


def test_serialize_record_has_all_required_fields():
    record = make_audit_record()
    data = _serialize_record(record)
    required_fields = [
        "id", "tenant_id", "query_text", "active_dataset_ids", "active_document_ids",
        "llm_model", "embed_model", "prompt_version", "sql_queries", "retrieved_chunks",
        "raw_model_output", "recommendation", "user_action", "created_at",
    ]
    for field in required_fields:
        assert field in data, f"Missing field: {field}"


def test_serialize_record_is_json_serializable():
    record = make_audit_record()
    data = _serialize_record(record)
    # Must not raise
    json_str = json.dumps(data, default=str)
    assert len(json_str) > 0


def test_build_pdf_returns_bytes():
    record = make_audit_record()
    pdf_bytes = _build_pdf(record)
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 1000  # A non-trivial PDF
    # PDF magic bytes
    assert pdf_bytes[:4] == b"%PDF"


def test_build_pdf_with_no_recommendation():
    record = make_audit_record(recommendation=None, user_action=None, action_at=None)
    # Must not raise even when recommendation is None
    pdf_bytes = _build_pdf(record)
    assert isinstance(pdf_bytes, bytes)


def test_serialize_record_action_at_none():
    record = make_audit_record(user_action=None, action_at=None)
    data = _serialize_record(record)
    assert data["user_action"] is None
    assert data["action_at"] is None
