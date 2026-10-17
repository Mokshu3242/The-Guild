"""claim mediation fields

Revision ID: af8e9c956c6e
Revises: f3138f6dd836
Create Date: 2026-10-17 01:40:14.861868

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'af8e9c956c6e'
down_revision: Union[str, Sequence[str], None] = 'f3138f6dd836'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("claims", sa.Column("ai_mediation_cents", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("claims", sa.Column("ai_mediation_reason", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("claims", "ai_mediation_reason")
    op.drop_column("claims", "ai_mediation_cents")