"""advances: paid on day one

Revision ID: e7a1c3d5f9b2
Revises: d5e8f1a2b3c4
Create Date: 2026-10-21 13:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = 'e7a1c3d5f9b2'
down_revision: Union[str, Sequence[str], None] = 'd5e8f1a2b3c4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

S = sqlmodel.sql.sqltypes.AutoString


def upgrade() -> None:
    op.create_table(
        'advances',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('guild_id', sa.Uuid(), nullable=False),
        sa.Column('invoice_id', sa.Uuid(), nullable=False),
        sa.Column('member_id', sa.Uuid(), nullable=False),
        sa.Column('advance_cents', sa.Integer(), nullable=False),
        sa.Column('fee_cents', sa.Integer(), nullable=False),
        sa.Column('status', S(), nullable=False),
        sa.Column('explanation', S(), nullable=False),
        sa.Column('explained_by', S(), nullable=False),
        sa.Column('decided_by', S(), nullable=False),
        sa.Column('decision_note', S(), nullable=False),
        sa.Column('paypal_batch_id', S(), nullable=False),
        sa.Column('member_debt_id', sa.Uuid(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('paid_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['guild_id'], ['guilds.id']),
        sa.ForeignKeyConstraint(['invoice_id'], ['invoices.id']),
        sa.ForeignKeyConstraint(['member_id'], ['members.id']),
        sa.ForeignKeyConstraint(['member_debt_id'], ['member_debts.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_advances_guild_id'), 'advances', ['guild_id'])
    op.create_index(op.f('ix_advances_invoice_id'), 'advances', ['invoice_id'])
    op.create_index(op.f('ix_advances_member_id'), 'advances', ['member_id'])


def downgrade() -> None:
    op.drop_index(op.f('ix_advances_member_id'), table_name='advances')
    op.drop_index(op.f('ix_advances_invoice_id'), table_name='advances')
    op.drop_index(op.f('ix_advances_guild_id'), table_name='advances')
    op.drop_table('advances')
