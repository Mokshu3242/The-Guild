"""agent mandates

Revision ID: a9c3e5f7b1d2
Revises: f2b4d6e8a0c1
Create Date: 2026-10-22 12:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = 'a9c3e5f7b1d2'
down_revision: Union[str, Sequence[str], None] = 'f2b4d6e8a0c1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

S = sqlmodel.sql.sqltypes.AutoString


def upgrade() -> None:
    op.create_table(
        'agent_mandates',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('guild_id', sa.Uuid(), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.Column('remind_max_tier', sa.Integer(), nullable=False),
        sa.Column('auto_claim', sa.Boolean(), nullable=False),
        sa.Column('claim_max_cents', sa.Integer(), nullable=False),
        sa.Column('claim_min_confidence', sa.Integer(), nullable=False),
        sa.Column('auto_advance', sa.Boolean(), nullable=False),
        sa.Column('advance_max_cents', sa.Integer(), nullable=False),
        sa.Column('set_by_id', sa.Uuid(), nullable=True),
        sa.Column('set_by_name', S(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['guild_id'], ['guilds.id']),
        sa.ForeignKeyConstraint(['set_by_id'], ['members.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_agent_mandates_guild_id'), 'agent_mandates', ['guild_id'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_agent_mandates_guild_id'), table_name='agent_mandates')
    op.drop_table('agent_mandates')
