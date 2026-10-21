"""milestone approved_by (client or silence)

Revision ID: c41d7e2b9a10
Revises: a3f9c2d41b77
Create Date: 2026-10-21 01:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = 'c41d7e2b9a10'
down_revision: Union[str, Sequence[str], None] = 'a3f9c2d41b77'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('milestones', sa.Column('approved_by', sqlmodel.sql.sqltypes.AutoString(),
                                          nullable=False, server_default=''))
    # Approvals made before this column existed were clicked by the client.
    op.execute("update milestones set approved_by = 'client' where client_approved_at is not null")


def downgrade() -> None:
    op.drop_column('milestones', 'approved_by')
