"""job client risk

Revision ID: 7f5b5d5327f8
Revises: a89c92b3e3e5
Create Date: 2026-10-13 23:25:30.501943

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '7f5b5d5327f8'
down_revision: Union[str, Sequence[str], None] = 'a89c92b3e3e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.add_column("jobs", sa.Column("client_risk", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=""))
    op.add_column("jobs", sa.Column("client_risk_reason", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("jobs", "client_risk_reason")
    op.drop_column("jobs", "client_risk")