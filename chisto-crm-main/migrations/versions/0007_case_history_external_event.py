"""Make imported document-service history events idempotent."""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("case_history") as batch_op:
        batch_op.add_column(sa.Column("external_event_id", sa.String(length=160), nullable=True))
        batch_op.create_unique_constraint(
            "uq_case_history_external_event_id", ["external_event_id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("case_history") as batch_op:
        batch_op.drop_constraint("uq_case_history_external_event_id", type_="unique")
        batch_op.drop_column("external_event_id")
