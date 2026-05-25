"""
Tenant isolation tests for the SQL sandbox.
Verifies that a query from tenant A cannot reference tenant B's tables,
even if the LLM generates a query that tries to cross tenant boundaries.
"""
import pytest
from app.services.reasoning.sql_agent import validate_sql

TENANT_A_TABLE = "t_aaaaaaaa_bbbbbbbb"
TENANT_B_TABLE = "t_cccccccc_dddddddd"


def test_tenant_a_can_query_own_table():
    ok, _ = validate_sql(f"SELECT * FROM {TENANT_A_TABLE} WHERE age > 25", [TENANT_A_TABLE])
    assert ok


def test_tenant_a_cannot_query_tenant_b_table():
    """Cross-tenant access must be rejected at the execution layer."""
    ok, msg = validate_sql(f"SELECT * FROM {TENANT_B_TABLE}", [TENANT_A_TABLE])
    assert not ok
    assert TENANT_B_TABLE in msg or "not in allowed" in msg


def test_cannot_reference_both_tenants_in_join():
    """Even a JOIN across tenants must be rejected."""
    ok, msg = validate_sql(
        f"SELECT a.premium FROM {TENANT_A_TABLE} a JOIN {TENANT_B_TABLE} b ON a.id = b.id",
        [TENANT_A_TABLE],
    )
    assert not ok


def test_cannot_access_information_schema():
    ok, msg = validate_sql(
        "SELECT table_name FROM information_schema.tables",
        [TENANT_A_TABLE],
    )
    assert not ok


def test_union_with_cross_tenant_rejected():
    ok, msg = validate_sql(
        f"SELECT premium FROM {TENANT_A_TABLE} UNION SELECT premium FROM {TENANT_B_TABLE}",
        [TENANT_A_TABLE],
    )
    assert not ok


def test_subquery_cross_tenant_rejected():
    ok, msg = validate_sql(
        f"SELECT * FROM {TENANT_A_TABLE} WHERE id IN (SELECT id FROM {TENANT_B_TABLE})",
        [TENANT_A_TABLE],
    )
    assert not ok


def test_valid_aggregate_query():
    ok, _ = validate_sql(
        f"SELECT region, AVG(premium) as avg_premium FROM {TENANT_A_TABLE} GROUP BY region ORDER BY avg_premium DESC",
        [TENANT_A_TABLE],
    )
    assert ok


def test_valid_multicolumn_filter():
    ok, _ = validate_sql(
        f"SELECT * FROM {TENANT_A_TABLE} WHERE age < 25 AND region = 'North' AND claim_count > 2",
        [TENANT_A_TABLE],
    )
    assert ok
