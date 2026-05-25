import hashlib
import uuid
from pathlib import Path
import pandas as pd
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
        entry = {
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
            # Detect outliers using IQR
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
    """Normalize column names to be safe SQL identifiers."""
    return col.strip().lower().replace(" ", "_").replace("-", "_").replace(".", "_")[:63]


def _pandas_dtype_to_pg(dtype: str) -> str:
    if "int" in dtype:
        return "BIGINT"
    if "float" in dtype:
        return "DOUBLE PRECISION"
    if "bool" in dtype:
        return "BOOLEAN"
    if "datetime" in dtype:
        return "TIMESTAMP"
    return "TEXT"


async def ingest_csv(
    file_path: Path,
    tenant_id: str,
    dataset_id: str,
    db: AsyncSession,
) -> dict:
    """
    Load CSV/Excel into PostgreSQL as a tenant-namespaced table.
    Idempotent: re-upload of same file_hash drops and recreates the table.
    Table name pattern: t_{tenant_id_short}_{dataset_id_short}
    """
    suffix = file_path.suffix.lower()
    if suffix in (".xlsx", ".xls"):
        df = pd.read_excel(file_path)
    else:
        df = pd.read_csv(file_path)

    # Sanitize column names
    df.columns = [_safe_column_name(c) for c in df.columns]
    # Drop fully empty columns
    df = df.dropna(axis=1, how="all")

    schema = _infer_schema(df)

    # Table name: safe, tenant-scoped, deterministic from dataset_id
    tenant_short = tenant_id.replace("-", "")[:8]
    ds_short = dataset_id.replace("-", "")[:8]
    table_name = f"t_{tenant_short}_{ds_short}"

    # Build CREATE TABLE DDL
    col_defs = ["_row_id SERIAL PRIMARY KEY"]
    for col in df.columns:
        dtype_str = str(df[col].dtype)
        pg_type = _pandas_dtype_to_pg(dtype_str)
        col_defs.append(f'"{col}" {pg_type}')
    ddl = f'CREATE TABLE IF NOT EXISTS "{table_name}" ({", ".join(col_defs)})'

    # Drop existing table for this dataset (idempotent re-upload)
    await db.execute(text(f'DROP TABLE IF EXISTS "{table_name}"'))
    await db.execute(text(ddl))
    await db.commit()

    # Bulk insert using pandas to_sql via sync connection
    # We use the sync DSN via psycopg2 for bulk insert efficiency
    from app.core.config import get_settings
    import sqlalchemy as sa
    settings = get_settings()
    sync_engine = sa.create_engine(settings.sync_database_url)
    df.to_sql(table_name, sync_engine, if_exists="replace", index=False, chunksize=1000)
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
