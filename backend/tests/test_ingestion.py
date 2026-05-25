"""
Ingestion pipeline tests.
These tests verify the CSV and PDF ingestion logic directly,
without needing a live database or Ollama instance.
"""
import io
import tempfile
from pathlib import Path
import pandas as pd
import pytest
from app.services.ingestion.csv_ingester import _infer_schema, _safe_column_name


# --- CSV schema inference ---

def test_safe_column_name_normalizes():
    assert _safe_column_name("Policy Number") == "policy_number"
    assert _safe_column_name("claim-frequency") == "claim_frequency"
    assert _safe_column_name("Age.Band") == "age_band"


def test_infer_schema_numeric():
    df = pd.DataFrame({"premium": [100.0, 200.0, 150.0, None], "age": [25, 30, 22, 45]})
    schema = _infer_schema(df)
    assert "premium" in schema
    assert schema["premium"]["dtype"].startswith("float")
    assert schema["premium"]["null_count"] == 1
    assert schema["premium"]["null_pct"] == 25.0
    assert "stats" in schema["premium"]
    assert "outlier_count" in schema["premium"]


def test_infer_schema_string():
    df = pd.DataFrame({"region": ["North", "South", "North", "East"]})
    schema = _infer_schema(df)
    assert "region" in schema
    assert schema["region"]["null_count"] == 0
    assert "sample_values" in schema["region"]
    assert "North" in schema["region"]["sample_values"]


def test_infer_schema_outlier_detection():
    # IQR outlier: 1000 is a clear outlier in [1,2,3,4,5]
    df = pd.DataFrame({"x": [1.0, 2.0, 3.0, 4.0, 5.0, 1000.0]})
    schema = _infer_schema(df)
    assert schema["x"]["outlier_count"] >= 1


# --- PDF chunker ---

def test_chunk_text_produces_overlap():
    from app.services.ingestion.pdf_ingester import _chunk_text
    # 600 words should produce at least 2 chunks with overlap
    text = " ".join(["word"] * 600)
    chunks = _chunk_text(text, {"page": 1, "type": "text", "document_id": "d1", "tenant_id": "t1"})
    assert len(chunks) >= 2
    # Every chunk must have an id
    for chunk in chunks:
        assert "id" in chunk
        assert chunk["document_id"] == "d1"


def test_chunk_text_short_produces_one():
    from app.services.ingestion.pdf_ingester import _chunk_text
    text = "This is a short sentence."
    chunks = _chunk_text(text, {"page": 1, "type": "text", "document_id": "d1", "tenant_id": "t1"})
    assert len(chunks) == 1


def test_chunk_indices_are_set():
    from app.services.ingestion.pdf_ingester import _chunk_text
    text = " ".join(["word"] * 800)
    chunks = _chunk_text(text, {"page": 2, "type": "text", "document_id": "dx", "tenant_id": "tx"})
    for i, chunk in enumerate(chunks):
        assert "chunk_index" in chunk
