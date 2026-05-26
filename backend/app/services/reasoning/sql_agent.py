import re
import sqlglot
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.llm.ollama_client import get_ollama_client

logger = get_logger(__name__)
settings = get_settings()

PROMPT_VERSION = "v1.0"

SQL_SYSTEM_PROMPT = """You are a SQL expert for insurance and banking pricing analysis.
Generate ONLY a single SELECT query. Never use INSERT, UPDATE, DELETE, DROP, CREATE, ALTER, TRUNCATE, or any DDL/DML.
Never reference system tables (pg_catalog, information_schema, pg_tables, etc).
Output ONLY the SQL query, nothing else - no explanation, no markdown."""


def _normalize_sql_response(sql: str) -> str:
    sql = sql.strip()
    sql = re.sub(r"```(?:sql)?", "", sql, flags=re.IGNORECASE).strip()

    select_match = re.search(r"\bSELECT\b", sql, re.IGNORECASE)
    if select_match:
        sql = sql[select_match.start():]

    semicolon_index = sql.find(";")
    if semicolon_index != -1:
        sql = sql[:semicolon_index + 1]

    return sql.strip()


def validate_sql(sql: str, allowed_tables: list[str]) -> tuple[bool, str]:
    """
    Parse SQL AST with sqlglot. Reject anything that is not a pure SELECT.
    Enforce that all referenced tables are in allowed_tables.
    This is enforced at execution layer, not just prompt.
    """
    sql = _normalize_sql_response(sql).rstrip(";")

    try:
        statements = sqlglot.parse(sql, dialect="postgres")
    except Exception as e:
        return False, f"SQL parse error: {e}"

    if not statements or len(statements) != 1:
        return False, "Expected exactly one SQL statement"

    stmt = statements[0]

    # Must be a SELECT statement
    if not isinstance(stmt, sqlglot.exp.Select):
        return False, f"Only SELECT statements are allowed, got: {type(stmt).__name__}"

    # Check for forbidden expression types
    forbidden = (
        sqlglot.exp.Insert,
        sqlglot.exp.Update,
        sqlglot.exp.Delete,
        sqlglot.exp.Drop,
        sqlglot.exp.Create,
        sqlglot.exp.AlterTable,
    )
    for node in stmt.walk():
        if isinstance(node, forbidden):
            return False, "Forbidden SQL operation detected"

    # Verify all table references are in allowed list
    referenced_tables = set()
    for table_node in stmt.find_all(sqlglot.exp.Table):
        name = table_node.name.lower()
        db = table_node.args.get("db")
        catalog = table_node.args.get("catalog")
        if db or catalog:
            return False, f"Cross-schema table reference forbidden: {table_node}"
        referenced_tables.add(name)

    forbidden_system = {"pg_catalog", "information_schema", "pg_tables", "pg_class", "pg_namespace"}
    for t in referenced_tables:
        if t in forbidden_system:
            return False, f"System table access forbidden: {t}"
        if t not in [a.lower() for a in allowed_tables]:
            return False, f"Table '{t}' is not in allowed tables: {allowed_tables}"

    return True, sql


async def generate_and_run_sql(
    question: str,
    dataset_schemas: list[dict],
    db: AsyncSession,
) -> list[dict]:
    """
    Generate SQL for the user question, validate it, execute it, return results.
    Each entry in dataset_schemas: {table_name, columns: [{name, dtype}], row_count}
    """
    if not dataset_schemas:
        return []

    # Build schema context for the prompt
    schema_text = ""
    allowed_tables = []
    for ds in dataset_schemas:
        table = ds["table_name"]
        allowed_tables.append(table.lower())
        cols = ", ".join(f"{c['name']} ({c['dtype']})" for c in ds["columns"])
        schema_text += f"\nTable: {table}\nColumns: {cols}\nRow count: {ds.get('row_count', 'unknown')}\n"

    prompt = f"""Available tables:
{schema_text}

User question: {question}

Write a SQL SELECT query to answer this question using the tables above.
Only reference the tables and columns listed. Use standard PostgreSQL syntax."""

    ollama = get_ollama_client()
    sql_raw = _normalize_sql_response(
        await ollama.generate(prompt=prompt, system=SQL_SYSTEM_PROMPT, temperature=0.0)
    )

    results = []
    is_valid, validated_sql = validate_sql(sql_raw, allowed_tables)

    if not is_valid:
        logger.warning("sql_validation_failed", reason=validated_sql, raw_sql=sql_raw)
        return [{
            "sql": sql_raw,
            "error": validated_sql,
            "rows": [],
            "row_count": 0,
        }]

    try:
        # Execute with a row limit to prevent runaway queries
        limited_sql = f"SELECT * FROM ({validated_sql}) AS _q LIMIT 500"
        result = await db.execute(text(limited_sql))
        rows = result.mappings().all()
        row_dicts = [dict(r) for r in rows]

        logger.info("sql_executed", sql=validated_sql[:200], row_count=len(row_dicts))
        results.append({
            "sql": validated_sql,
            "rows": row_dicts,
            "row_count": len(row_dicts),
            "error": None,
        })
    except Exception as e:
        logger.error("sql_execution_error", sql=validated_sql, error=str(e))
        results.append({
            "sql": validated_sql,
            "rows": [],
            "row_count": 0,
            "error": str(e),
        })

    return results
