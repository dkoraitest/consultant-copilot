"""Add client_id to telegram_chats and settings table

Revision ID: 004
Revises: 003
Create Date: 2026-02-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '004'
down_revision: Union[str, None] = '003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add client_id column to telegram_chats
    op.add_column(
        'telegram_chats',
        sa.Column('client_id', sa.UUID(), nullable=True)
    )
    op.create_foreign_key(
        'fk_telegram_chats_client_id',
        'telegram_chats',
        'clients',
        ['client_id'],
        ['id']
    )

    # Add unique constraint to clients.name (if not exists)
    # Using raw SQL to handle "if not exists" gracefully
    op.execute("""
        DO $$ BEGIN
            ALTER TABLE clients ADD CONSTRAINT uq_clients_name UNIQUE (name);
        EXCEPTION
            WHEN duplicate_table THEN NULL;
            WHEN duplicate_object THEN NULL;
        END $$;
    """)

    # Create settings table
    op.create_table(
        'settings',
        sa.Column('key', sa.String(100), nullable=False),
        sa.Column('value', sa.Text(), nullable=False),
        sa.Column('description', sa.String(500), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('key')
    )


def downgrade() -> None:
    op.drop_table('settings')
    op.drop_constraint('fk_telegram_chats_client_id', 'telegram_chats', type_='foreignkey')
    op.drop_column('telegram_chats', 'client_id')
