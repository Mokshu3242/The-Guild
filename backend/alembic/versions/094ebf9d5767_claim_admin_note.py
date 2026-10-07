"""claim admin note

Revision ID: 094ebf9d5767
Revises: 52db4879c89d
Create Date: 2026-10-07 00:11:09.697937

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '094ebf9d5767'
down_revision: Union[str, Sequence[str], None] = '52db4879c89d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("claims", sa.Column("admin_note", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("claims", "admin_note")