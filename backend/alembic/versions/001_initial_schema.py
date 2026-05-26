"""initial schema

Revision ID: 001
Revises:
Create Date: 2025-05-23
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "datasets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("file_hash", sa.String(64), nullable=False),
        sa.Column("file_size_bytes", sa.Integer, nullable=False),
        sa.Column("row_count", sa.Integer, nullable=True),
        sa.Column("column_count", sa.Integer, nullable=True),
        sa.Column("schema_info", postgresql.JSON, nullable=True),
        sa.Column("column_tags", postgresql.JSON, nullable=True),
        sa.Column("statistics", postgresql.JSON, nullable=True),
        sa.Column("table_name", sa.String(128), nullable=True),
        sa.Column("upload_status", sa.String(32), server_default="pending"),
        sa.Column("job_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("is_active", sa.Boolean, server_default="true"),
    )
    op.create_index("ix_datasets_tenant_id", "datasets", ["tenant_id"])
    op.create_index("ix_datasets_file_hash", "datasets", ["file_hash"])

    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("file_hash", sa.String(64), nullable=False),
        sa.Column("file_size_bytes", sa.Integer, nullable=False),
        sa.Column("page_count", sa.Integer, nullable=True),
        sa.Column("chunk_count", sa.Integer, nullable=True),
        sa.Column("embedding_model", sa.String(128), nullable=True),
        sa.Column("upload_status", sa.String(32), server_default="pending"),
        sa.Column("job_id", sa.String(64), nullable=True),
        sa.Column("ocr_used", sa.Boolean, server_default="false"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("is_active", sa.Boolean, server_default="true"),
    )
    op.create_index("ix_documents_tenant_id", "documents", ["tenant_id"])
    op.create_index("ix_documents_file_hash", "documents", ["file_hash"])

    op.create_table(
        "chat_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("messages", postgresql.JSON, server_default="[]"),
        sa.Column("context_summary", sa.Text, nullable=True),
        sa.Column("turn_count", sa.Integer, server_default="0"),
        sa.Column("active_dataset_ids", postgresql.JSON, server_default="[]"),
        sa.Column("active_document_ids", postgresql.JSON, server_default="[]"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("last_active_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_chat_sessions_tenant_id", "chat_sessions", ["tenant_id"])

    op.create_table(
        "chat_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("turn_index", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_chat_messages_session_id", "chat_messages", ["session_id"])

    op.create_table(
        "audit_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("recommendation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("query_text", sa.Text, nullable=False),
        sa.Column("active_dataset_ids", postgresql.JSON, server_default="[]"),
        sa.Column("active_document_ids", postgresql.JSON, server_default="[]"),
        sa.Column("llm_model", sa.String(128), nullable=False),
        sa.Column("embed_model", sa.String(128), nullable=False),
        sa.Column("prompt_version", sa.String(32), nullable=False),
        sa.Column("sql_queries", postgresql.JSON, server_default="[]"),
        sa.Column("retrieved_chunks", postgresql.JSON, server_default="[]"),
        sa.Column("raw_model_output", sa.Text, nullable=True),
        sa.Column("recommendation", postgresql.JSON, nullable=True),
        sa.Column("user_action", sa.String(32), nullable=True),
        sa.Column("user_comment", sa.Text, nullable=True),
        sa.Column("action_at", sa.DateTime, nullable=True),
        sa.Column("scenario_label", sa.String(128), nullable=True),
        sa.Column("scenario_assumptions", postgresql.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("is_finalized", sa.Boolean, server_default="true"),
    )
    op.create_index("ix_audit_records_tenant_id", "audit_records", ["tenant_id"])
    op.create_index("ix_audit_records_session_id", "audit_records", ["session_id"])


def downgrade() -> None:
    op.drop_table("audit_records")
    op.drop_table("chat_messages")
    op.drop_table("chat_sessions")
    op.drop_table("documents")
    op.drop_table("datasets")
