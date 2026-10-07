"""claim status and statement

Revision ID: 52db4879c89d
Revises: 358fbf748f7e
Create Date: 2026-10-06 23:56:01.884796

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '52db4879c89d'
down_revision: Union[str, Sequence[str], None] = '358fbf748f7e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("guilds", sa.Column("claim_overdue_days", sa.Integer(), nullable=False, server_default="14"))
    op.add_column("claims", sa.Column("statement", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=""))
    op.add_column("claims", sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="submitted"))
    op.create_index(op.f("ix_claims_invoice_id"), "claims", ["invoice_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_claims_invoice_id"), table_name="claims")
    op.drop_column("claims", "status")
    op.drop_column("claims", "statement")
    op.drop_column("guilds", "claim_overdue_days")
