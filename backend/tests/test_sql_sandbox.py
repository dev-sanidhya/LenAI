import pytest
from app.services.reasoning.sql_agent import validate_sql, _normalize_sql_response

ALLOWED = ["t_abc12345_def67890"]


def test_valid_select():
    ok, sql = validate_sql("SELECT age, premium FROM t_abc12345_def67890 WHERE region = 'North'", ALLOWED)
    assert ok


def test_rejects_insert():
    ok, msg = validate_sql("INSERT INTO t_abc12345_def67890 VALUES (1)", ALLOWED)
    assert not ok


def test_rejects_drop():
    ok, msg = validate_sql("DROP TABLE t_abc12345_def67890", ALLOWED)
    assert not ok


def test_rejects_system_table():
    ok, msg = validate_sql("SELECT * FROM pg_catalog.pg_tables", ALLOWED)
    assert not ok


def test_rejects_unknown_table():
    ok, msg = validate_sql("SELECT * FROM other_tenant_table", ALLOWED)
    assert not ok


def test_rejects_delete():
    ok, msg = validate_sql("DELETE FROM t_abc12345_def67890", ALLOWED)
    assert not ok


def test_normalize_sql_strips_code_fences_and_trailing_text():
    raw = """```sql
    SELECT age, premium FROM t_abc12345_def67890 WHERE region = 'North';
    ```
    extra text
    """
    normalized = _normalize_sql_response(raw)
    assert normalized == "SELECT age, premium FROM t_abc12345_def67890 WHERE region = 'North';"
