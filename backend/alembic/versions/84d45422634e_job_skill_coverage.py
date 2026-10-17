"""job skill coverage

Revision ID: 84d45422634e
Revises: af8e9c956c6e
Create Date: 2026-10-17 01:54:21.554394

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '84d45422634e'
down_revision: Union[str, Sequence[str], None] = 'af8e9c956c6e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.add_column("jobs", sa.Column("skill_coverage", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=""))
    op.add_column("jobs", sa.Column("skill_gap", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "skill_gap")
    op.drop_column("jobs", "skill_coverage")