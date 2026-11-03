"""rename repeated package to secondary

Терминология департамента: пакет, который собирается после неисполнения
предписания, называется вторичным, а не повторным. Меняется только
отображаемое название — код `repeated_prescription` остаётся: он внутренний
и на него ссылаются данные и проверки.

Revision ID: b7c41f2e8a55
Revises: 09ee8ec5323e
Create Date: 2026-10-12 10:30:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'b7c41f2e8a55'
down_revision: Union[str, None] = '09ee8ec5323e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "UPDATE package_kinds SET name = 'Вторичное предписание' "
        "WHERE code = 'repeated_prescription'"
    )
    op.execute(
        "UPDATE package_kinds SET name = 'Первичное предписание' "
        "WHERE code = 'primary_prescription'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE package_kinds SET name = 'Повторное предписание' "
        "WHERE code = 'repeated_prescription'"
    )
