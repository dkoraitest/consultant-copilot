"""Add telegram_chats, telegram_messages, telegram_embeddings tables

Revision ID: 003_telegram
Revises: 002_add_embeddings
Create Date: 2026-02-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector


# revision identifiers, used by Alembic.
revision: str = '003'
down_revision: Union[str, None] = '002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # telegram_chats
    op.create_table(
        'telegram_chats',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('title', sa.String(500), nullable=False),
        sa.Column('client_name', sa.String(255), nullable=True),
        sa.Column('last_synced_message_id', sa.BigInteger(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id')
    )

    # telegram_messages
    op.create_table(
        'telegram_messages',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('chat_id', sa.BigInteger(), nullable=False),
        sa.Column('message_id', sa.BigInteger(), nullable=False),
        sa.Column('date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('sender_name', sa.String(255), nullable=True),
        sa.Column('text', sa.Text(), nullable=True),
        sa.Column('has_media', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('media_type', sa.String(50), nullable=True),
        sa.Column('meeting_id', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['chat_id'], ['telegram_chats.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['meeting_id'], ['meetings.id']),
        sa.UniqueConstraint('chat_id', 'message_id', name='uq_telegram_message')
    )

    # Index for faster lookups
    op.create_index('ix_telegram_messages_chat_date', 'telegram_messages', ['chat_id', 'date'])

    # telegram_embeddings
    op.create_table(
        'telegram_embeddings',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('message_id', sa.UUID(), nullable=False),
        sa.Column('chunk_text', sa.Text(), nullable=False),
        sa.Column('chunk_index', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('embedding', Vector(1536), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['message_id'], ['telegram_messages.id'], ondelete='CASCADE')
    )

    # Index for vector similarity search
    op.execute(
        "CREATE INDEX ix_telegram_embeddings_vector ON telegram_embeddings "
        "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )


def downgrade() -> None:
    op.drop_index('ix_telegram_embeddings_vector', 'telegram_embeddings')
    op.drop_table('telegram_embeddings')
    op.drop_index('ix_telegram_messages_chat_date', 'telegram_messages')
    op.drop_table('telegram_messages')
    op.drop_table('telegram_chats')
