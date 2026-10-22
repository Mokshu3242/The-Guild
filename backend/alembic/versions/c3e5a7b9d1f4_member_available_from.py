"""members.available_from (busy until)

Revision ID: c3e5a7b9d1f4
Revises: b1d3f5a7c9e2
Create Date: 2026-10-22 20:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c3e5a7b9d1f4'
down_revision: Union[str, Sequence[str], None] = 'b1d3f5a7c9e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('members', sa.Column('available_from', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('members', 'available_from')
