"""Store document-service linkage and stage-2 readiness."""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

Json = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    op.add_column("cases", sa.Column("document_service_case_id", sa.Integer(), nullable=True))
    op.add_column("cases", sa.Column("document_service_status", sa.String(length=32), nullable=True))
    op.add_column("cases", sa.Column("document_service_readiness", Json, nullable=True))


def downgrade() -> None:
    op.drop_column("cases", "document_service_readiness")
    op.drop_column("cases", "document_service_status")
    op.drop_column("cases", "document_service_case_id")
