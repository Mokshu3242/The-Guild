"""recovery: claim recovered amount, direct payments, member debts

Revision ID: d5e8f1a2b3c4
Revises: c41d7e2b9a10
Create Date: 2026-10-21 12:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = 'd5e8f1a2b3c4'
down_revision: Union[str, Sequence[str], None] = 'c41d7e2b9a10'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

S = sqlmodel.sql.sqltypes.AutoString


def upgrade() -> None:
    op.add_column('claims', sa.Column('recovered_cents', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('claims', sa.Column('recovered_at', sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        'direct_payments',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('guild_id', sa.Uuid(), nullable=False),
        sa.Column('invoice_id', sa.Uuid(), nullable=False),
        sa.Column('member_id', sa.Uuid(), nullable=False),
        sa.Column('amount_cents', sa.Integer(), nullable=False),
        sa.Column('method', S(), nullable=False),
        sa.Column('note', S(), nullable=False),
        sa.Column('status', S(), nullable=False),
        sa.Column('owed_cents', sa.Integer(), nullable=False),
        sa.Column('decided_by', S(), nullable=False),
        sa.Column('decision_note', S(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['guild_id'], ['guilds.id']),
        sa.ForeignKeyConstraint(['invoice_id'], ['invoices.id']),
        sa.ForeignKeyConstraint(['member_id'], ['members.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_direct_payments_guild_id'), 'direct_payments', ['guild_id'])
    op.create_index(op.f('ix_direct_payments_invoice_id'), 'direct_payments', ['invoice_id'])
    op.create_index(op.f('ix_direct_payments_member_id'), 'direct_payments', ['member_id'])

    op.create_table(
        'member_debts',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('guild_id', sa.Uuid(), nullable=False),
        sa.Column('member_id', sa.Uuid(), nullable=False),
        sa.Column('kind', S(), nullable=False),
        sa.Column('source_id', S(), nullable=False),
        sa.Column('amount_cents', sa.Integer(), nullable=False),
        sa.Column('repaid_cents', sa.Integer(), nullable=False),
        sa.Column('status', S(), nullable=False),
        sa.Column('note', S(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['guild_id'], ['guilds.id']),
        sa.ForeignKeyConstraint(['member_id'], ['members.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_member_debts_guild_id'), 'member_debts', ['guild_id'])
    op.create_index(op.f('ix_member_debts_member_id'), 'member_debts', ['member_id'])


def downgrade() -> None:
    op.drop_index(op.f('ix_member_debts_member_id'), table_name='member_debts')
    op.drop_index(op.f('ix_member_debts_guild_id'), table_name='member_debts')
    op.drop_table('member_debts')
    op.drop_index(op.f('ix_direct_payments_member_id'), table_name='direct_payments')
    op.drop_index(op.f('ix_direct_payments_invoice_id'), table_name='direct_payments')
    op.drop_index(op.f('ix_direct_payments_guild_id'), table_name='direct_payments')
    op.drop_table('direct_payments')
    op.drop_column('claims', 'recovered_at')
    op.drop_column('claims', 'recovered_cents')
