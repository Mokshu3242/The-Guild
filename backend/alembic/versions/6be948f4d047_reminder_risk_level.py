"""reminder risk level

Revision ID: 6be948f4d047
Revises: 7f5b5d5327f8
Create Date: 2026-10-13 23:37:54.152485

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '6be948f4d047'
down_revision: Union[str, Sequence[str], None] = '7f5b5d5327f8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.add_column(
        "reminders",
        sa.Column("risk_level", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("reminders", "risk_level")