"""Knowledge base for vector storage

Revision ID: 0005
Revises: 0004
Create Date: 2026-02-01 10:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0005"
down_revision: Union[str, None] = "0004"


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    op.create_table(
        "knowledge_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("data_file_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("data_files.id", ondelete="CASCADE"), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("embedding", postgresql.ARRAY(sa.Float), nullable=True),
        sa.Column("embedding_model", sa.String(64), nullable=True),
        sa.Column("chunk_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("idx_knowledge_tenant", "knowledge_chunks", ["tenant_id"])
    op.create_index("idx_knowledge_file", "knowledge_chunks", ["data_file_id"])
    
    # GIN index for full-text search
    op.execute("""
        CREATE INDEX idx_knowledge_content_fts
        ON knowledge_chunks
        USING gin(to_tsvector('portuguese', content));
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_knowledge_content_fts")
    op.drop_table("knowledge_chunks")
