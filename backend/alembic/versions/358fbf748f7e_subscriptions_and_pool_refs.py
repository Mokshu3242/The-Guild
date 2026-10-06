"""subscriptions and pool refs

Revision ID: 358fbf748f7e
Revises: 2c6a63f90e40
Create Date: 2026-10-06 03:52:46.502477

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '358fbf748f7e'
down_revision: Union[str, Sequence[str], None] = '2c6a63f90e40'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "guilds",
        sa.Column("paypal_plan_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=""),
    )
    op.add_column(
        "pool_tx",
        sa.Column("external_ref", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    )
    op.create_unique_constraint("uq_pool_tx_external_ref", "pool_tx", ["external_ref"])
    op.add_column(
        "subscriptions",
        sa.Column("approve_url", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=""),
    )
    op.add_column(
        "subscriptions",
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("subscriptions", "activated_at")
    op.drop_column("subscriptions", "approve_url")
    op.drop_constraint("uq_pool_tx_external_ref", "pool_tx", type_="unique")
    op.drop_column("pool_tx", "external_ref")
    op.drop_column("guilds", "paypal_plan_id")