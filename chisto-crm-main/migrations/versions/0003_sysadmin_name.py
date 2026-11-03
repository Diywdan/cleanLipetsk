"""sysadmin name

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-14 09:30:00

Роль admin и первый администратор называются «Системный администратор» — так их
видно в консоли /admin/. Переименовываются, только если название ещё заводское.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("UPDATE roles SET name = 'Системный администратор' WHERE code = 'admin' AND name = 'Администратор'"))
    op.execute(sa.text("UPDATE users SET full_name = 'Системный администратор' WHERE full_name = 'Администратор'"))


def downgrade() -> None:
    op.execute(sa.text("UPDATE roles SET name = 'Администратор' WHERE code = 'admin' AND name = 'Системный администратор'"))
    op.execute(sa.text("UPDATE users SET full_name = 'Администратор' WHERE full_name = 'Системный администратор'"))
