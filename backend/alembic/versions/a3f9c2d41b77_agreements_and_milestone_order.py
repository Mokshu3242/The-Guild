"""agreements, milestone order, agreement summary

Revision ID: a3f9c2d41b77
Revises: 01b102fd8f54
Create Date: 2026-10-21 00:30:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = 'a3f9c2d41b77'
down_revision: Union[str, Sequence[str], None] = '01b102fd8f54'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Milestones keep the order they were made in. Old rows all get "now".
    op.add_column('milestones', sa.Column('created_at', sa.DateTime(timezone=True),
                                          nullable=False, server_default=sa.func.now()))

    op.add_column('jobs', sa.Column('agreement_summary', sqlmodel.sql.sqltypes.AutoString(),
                                    nullable=False, server_default=''))
    op.add_column('jobs', sa.Column('agreement_summary_hash', sqlmodel.sql.sqltypes.AutoString(),
                                    nullable=False, server_default=''))

    op.create_table(
        'agreements',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('guild_id', sa.Uuid(), nullable=False),
        sa.Column('job_id', sa.Uuid(), nullable=True),
        sa.Column('member_id', sa.Uuid(), nullable=True),
        sa.Column('kind', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('template_version', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('body', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('sha256', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('milestone_ids', sa.JSON(), nullable=True),
        sa.Column('total_cents', sa.Integer(), nullable=False),
        sa.Column('signer_name', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('signer_email', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('ip', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('user_agent', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('accepted_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['guild_id'], ['guilds.id'], ),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ),
        sa.ForeignKeyConstraint(['member_id'], ['members.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_agreements_guild_id'), 'agreements', ['guild_id'], unique=False)
    op.create_index(op.f('ix_agreements_job_id'), 'agreements', ['job_id'], unique=False)
    op.create_index(op.f('ix_agreements_member_id'), 'agreements', ['member_id'], unique=False)
    op.create_index(op.f('ix_agreements_sha256'), 'agreements', ['sha256'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_agreements_sha256'), table_name='agreements')
    op.drop_index(op.f('ix_agreements_member_id'), table_name='agreements')
    op.drop_index(op.f('ix_agreements_job_id'), table_name='agreements')
    op.drop_index(op.f('ix_agreements_guild_id'), table_name='agreements')
    op.drop_table('agreements')
    op.drop_column('jobs', 'agreement_summary_hash')
    op.drop_column('jobs', 'agreement_summary')
    op.drop_column('milestones', 'created_at')
