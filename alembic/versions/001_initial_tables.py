"""Initial tables

Revision ID: 001
Revises:
Create Date: 2026-01-30

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # Create clients table
    op.create_table(
        "clients",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("telegram_chat_id", sa.BigInteger(), nullable=True),
        sa.Column("todoist_project_id", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    # Create meetings table
    op.create_table(
        "meetings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("fireflies_id", sa.String(255), unique=True, nullable=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("transcript", sa.Text(), nullable=True),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=True),
        sa.Column("meeting_type", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    # Create summaries table
    op.create_table(
        "summaries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("meeting_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("meetings.id"), nullable=False),
        sa.Column("meeting_type", sa.String(50), nullable=False),
        sa.Column("content_text", sa.Text(), nullable=False),
        sa.Column("content_json", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    # Create leads table
    op.create_table(
        "leads",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("client_tg", sa.String(255), nullable=True),
        sa.Column("client_name", sa.String(255), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("channel", sa.String(100), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="new"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    # Create hypotheses table
    op.create_table(
        "hypotheses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("success_criteria", postgresql.JSONB(), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="active"),
        sa.Column("result", sa.Text(), nullable=True),
        sa.Column("result_data", postgresql.JSONB(), nullable=True),
        sa.Column("quarter", sa.String(10), nullable=True),
        sa.Column("tested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("meeting_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("meetings.id"), nullable=True),
    )

    # Create indexes
    op.create_index("ix_meetings_fireflies_id", "meetings", ["fireflies_id"])
    op.create_index("ix_meetings_client_id", "meetings", ["client_id"])
    op.create_index("ix_hypotheses_client_id", "hypotheses", ["client_id"])
    op.create_index("ix_hypotheses_quarter", "hypotheses", ["quarter"])
    op.create_index("ix_hypotheses_status", "hypotheses", ["status"])


def downgrade() -> None:
    op.drop_table("hypotheses")
    op.drop_table("leads")
    op.drop_table("summaries")
    op.drop_table("meetings")
    op.drop_table("clients")
