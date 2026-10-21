"""hire by agent: api keys, quotes, job source

Revision ID: f2b4d6e8a0c1
Revises: e7a1c3d5f9b2
Create Date: 2026-10-21 15:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = 'f2b4d6e8a0c1'
down_revision: Union[str, Sequence[str], None] = 'e7a1c3d5f9b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

S = sqlmodel.sql.sqltypes.AutoString


def upgrade() -> None:
    op.create_table(
        'api_keys',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('guild_id', sa.Uuid(), nullable=False),
        sa.Column('member_id', sa.Uuid(), nullable=False),
        sa.Column('name', S(), nullable=False),
        sa.Column('prefix', S(), nullable=False),
        sa.Column('key_hash', S(), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.Column('request_count', sa.Integer(), nullable=False),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['guild_id'], ['guilds.id']),
        sa.ForeignKeyConstraint(['member_id'], ['members.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_api_keys_guild_id'), 'api_keys', ['guild_id'])
    op.create_index(op.f('ix_api_keys_key_hash'), 'api_keys', ['key_hash'], unique=True)

    op.add_column('jobs', sa.Column('source', S(), nullable=False, server_default='manual'))
    op.add_column('jobs', sa.Column('api_key_id', sa.Uuid(), nullable=True))
    op.create_foreign_key('fk_jobs_api_key_id', 'jobs', 'api_keys', ['api_key_id'], ['id'])

    op.create_table(
        'quotes',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('guild_id', sa.Uuid(), nullable=False),
        sa.Column('api_key_id', sa.Uuid(), nullable=False),
        sa.Column('brief', S(), nullable=False),
        sa.Column('summary', S(), nullable=False),
        sa.Column('pricing_basis', S(), nullable=False),
        sa.Column('budget_cents', sa.Integer(), nullable=True),
        sa.Column('milestones', sa.JSON(), nullable=True),
        sa.Column('total_cents', sa.Integer(), nullable=False),
        sa.Column('status', S(), nullable=False),
        sa.Column('job_id', sa.Uuid(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['guild_id'], ['guilds.id']),
        sa.ForeignKeyConstraint(['api_key_id'], ['api_keys.id']),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_quotes_guild_id'), 'quotes', ['guild_id'])
    op.create_index(op.f('ix_quotes_api_key_id'), 'quotes', ['api_key_id'])


def downgrade() -> None:
    op.drop_index(op.f('ix_quotes_api_key_id'), table_name='quotes')
    op.drop_index(op.f('ix_quotes_guild_id'), table_name='quotes')
    op.drop_table('quotes')
    op.drop_constraint('fk_jobs_api_key_id', 'jobs', type_='foreignkey')
    op.drop_column('jobs', 'api_key_id')
    op.drop_column('jobs', 'source')
    op.drop_index(op.f('ix_api_keys_key_hash'), table_name='api_keys')
    op.drop_index(op.f('ix_api_keys_guild_id'), table_name='api_keys')
    op.drop_table('api_keys')
