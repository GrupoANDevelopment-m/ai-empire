"""Skills registry

Revision ID: 0002
Revises: 0001
Create Date: 2026-01-20 10:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0002"
down_revision: Union[str, None] = "0001"


def upgrade() -> None:
    op.create_table(
        "skills",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("source", sa.String(32), nullable=False, server_default="builtin"),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("manifest", postgresql.JSONB, nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="installed"),
        sa.Column("installed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("tenant_id", "name", "version", name="uq_skill_tenant_name_version"),
    )
    op.create_index("idx_skills_tenant", "skills", ["tenant_id"])
    op.create_index("idx_skills_status", "skills", ["status"])
    
    op.create_table(
        "skill_tools",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("skill_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("skills.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("input_schema", postgresql.JSONB, nullable=False),
        sa.Column("output_schema", postgresql.JSONB, nullable=True),
        sa.Column("sandbox_profile", sa.String(32), nullable=False, server_default="standard"),
        sa.Column("network_policy", postgresql.JSONB, nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
    )
    op.create_index("idx_skill_tools_skill", "skill_tools", ["skill_id"])


def downgrade() -> None:
    op.drop_table("skill_tools")
    op.drop_table("skills")
