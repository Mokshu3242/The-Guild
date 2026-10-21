"""members.read_only for judge accounts

Revision ID: b1d3f5a7c9e2
Revises: a9c3e5f7b1d2
Create Date: 2026-10-22 18:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b1d3f5a7c9e2'
down_revision: Union[str, Sequence[str], None] = 'a9c3e5f7b1d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('members', sa.Column('read_only', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column('members', 'read_only')
