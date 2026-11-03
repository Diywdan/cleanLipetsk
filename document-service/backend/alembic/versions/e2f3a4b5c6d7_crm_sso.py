"""Add CRM SSO identities and replay protection for launch tickets.

Revision ID: e2f3a4b5c6d7
Revises: d6e7f8a9b0c1
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "e2f3a4b5c6d7"
down_revision: Union[str, None] = "d6e7f8a9b0c1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("crm_user_id", sa.String(length=128), nullable=True))
    op.create_unique_constraint("uq_users_crm_user_id", "users", ["crm_user_id"])
    op.create_table(
        "sso_login_tickets",
        sa.Column("jti", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("jti", name="pk_sso_login_tickets"),
    )


def downgrade() -> None:
    op.drop_table("sso_login_tickets")
    op.drop_constraint("uq_users_crm_user_id", "users", type_="unique")
    op.drop_column("users", "crm_user_id")
