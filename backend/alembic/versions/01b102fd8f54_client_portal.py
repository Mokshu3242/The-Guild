"""client portal


Revision ID: 01b102fd8f54
Revises: 6cf204f9e930
Create Date: 2026-10-18 14:42:52.368251

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '01b102fd8f54'
down_revision: Union[str, Sequence[str], None] = '6cf204f9e930'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('jobs', sa.Column('portal_token', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.add_column('jobs', sa.Column('portal_token_created_at', sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f('ix_jobs_portal_token'), 'jobs', ['portal_token'], unique=True)
    op.add_column('milestones', sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('milestones', sa.Column('delivery_note', sqlmodel.sql.sqltypes.AutoString(),
                                          nullable=False, server_default=''))
    op.add_column('milestones', sa.Column('client_approved_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('milestones', sa.Column('client_changes_requested_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('milestones', sa.Column('client_feedback', sqlmodel.sql.sqltypes.AutoString(),
                                          nullable=False, server_default=''))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('milestones', 'client_feedback')
    op.drop_column('milestones', 'client_changes_requested_at')
    op.drop_column('milestones', 'client_approved_at')
    op.drop_column('milestones', 'delivery_note')
    op.drop_column('milestones', 'delivered_at')
    op.drop_index(op.f('ix_jobs_portal_token'), table_name='jobs')
    op.drop_column('jobs', 'portal_token_created_at')
    op.drop_column('jobs', 'portal_token')