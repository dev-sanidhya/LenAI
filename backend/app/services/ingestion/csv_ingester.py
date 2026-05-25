import hashlib
import uuid
from pathlib import Path
import pandas as pd
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.logging import get_logger

logger = get_logger(__name__)


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def _infer_schema(df: pd.DataFrame) -> dict:
    """Infer column types and compute basic statistics."""
    schema = {}
    for col in df.columns:
        dtype = str(df[col].dtype)
        null_count = int(df[col].isna().sum())
        unique_count = int(df[col].nunique())
        entry: dict = {
            "dtype": dtype,
            "null_count": null_count,
            "null_pct": round(null_count / len(df) * 100, 2) if len(df) else 0,
            "unique_count": unique_count,
        }
        if pd.api.types.is_numeric_dtype(df[col]):
            desc = df[col].describe()
            entry["stats"] = {
                "mean": round(float(desc["mean"]), 4) if "mean" in desc else None,
                "std": round(float(desc["std"]), 4) if "std" in desc else None,
                "min": round(float(desc["min"]), 4) if "min" in desc else None,
                "max": round(float(desc["max"]), 4) if "max" in desc else None,
                "p25": round(float(desc["25%"]), 4) if "25%" in desc else None,
                "p50": round(float(desc["50%"]), 4) if "50%" in desc else None,
                "p75": round(float(desc["75%"]), 4) if "75%" in desc else None,
            }
            q1 = df[col].quantile(0.25)
            q3 = df[col].quantile(0.75)
            iqr = q3 - q1
            outliers = int(((df[col] < q1 - 1.5 * iqr) | (df[col] > q3 + 1.5 * iqr)).sum())
            entry["outlier_count"] = outliers
        elif pd.api.types.is_string_dtype(df[col]) or pd.api.types.is_object_dtype(df[col]):
            entry["sample_values"] = df[col].dropna().unique()[:5].tolist()
        schema[col] = entry
    return schema


def _safe_column_name(col: str) -> str:
    return col.strip().lower().replace(" ", "_").replace("-", "_").replace(".", "_")[:63]


async def ingest_csv(
    file_path: Path,
    tenant_id: str,
    dataset_id: str,
    db: AsyncSession,
) -> dict:
    """
    Load CSV/Excel into PostgreSQL as a tenant-namespaced table.

    Schema authority: pandas `to_sql` is the single source of truth for the
    table schema. We do NOT pre-create the table with manual DDL - that pattern
    causes the DDL to be silently discarded when to_sql(if_exists="replace")
    drops and recreates the table.

    After to_sql, we add a _row_id SERIAL column for a stable primary key.
    This keeps schema creation atomic and avoids the DDL/ORM conflict.

    Table name pattern: t_{tenant_short}_{dataset_short}
    Idempotent: same dataset_id always maps to the same table name.
    """
    suffix = file_path.suffix.lower()
    if suffix in (".xlsx", ".xls"):
        df = pd.read_excel(file_path)
    else:
        df = pd.read_csv(file_path)

    # Sanitize column names to safe SQL identifiers
    df.columns = [_safe_column_name(c) for c in df.columns]
    df = df.dropna(axis=1, how="all")

    schema = _infer_schema(df)

    tenant_short = tenant_id.replace("-", "")[:8]
    ds_short = dataset_id.replace("-", "")[:8]
    table_name = f"t_{tenant_short}_{ds_short}"

    from app.core.config import get_settings
    settings = get_settings()

    # Use a sync engine for pandas interop.
    # to_sql is the single schema authority - no competing manual DDL.
    sync_engine = sa.create_engine(settings.sync_database_url)
    try:
        df.to_sql(
            table_name,
            sync_engine,
            if_exists="replace",  # sole schema creator - drops existing, recreates cleanly
            index=False,
            chunksize=1000,
        )
        # Add a stable primary key after pandas creates the table.
        # ALTER TABLE is safe here because to_sql just finished writing.
        with sync_engine.connect() as conn:
            conn.execute(sa.text(
                f'ALTER TABLE "{table_name}" ADD COLUMN IF NOT EXISTS _row_id SERIAL PRIMARY KEY'
            ))
            conn.commit()
    finally:
        sync_engine.dispose()

    row_count = len(df)
    col_count = len(df.columns)

    logger.info("csv_ingest_done", table=table_name, rows=row_count, cols=col_count)

    return {
        "table_name": table_name,
        "row_count": row_count,
        "column_count": col_count,
        "schema_info": schema,
    }
