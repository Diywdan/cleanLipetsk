"""Link control cases to CRM incidents.

Revision ID: d6e7f8a9b0c1
Revises: c3d4e5f6a7b8
Create Date: 2026-10-31
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "d6e7f8a9b0c1"
down_revision: Union[str, None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("control_cases", sa.Column("crm_case_id", sa.String(length=128), nullable=True))
    op.create_unique_constraint(
        "uq_control_cases_crm_case_id", "control_cases", ["crm_case_id"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_control_cases_crm_case_id", "control_cases", type_="unique")
    op.drop_column("control_cases", "crm_case_id")
