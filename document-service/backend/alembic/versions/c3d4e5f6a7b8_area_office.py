"""Управы: номер кабинета

Место явки и кабинет больше не заполняются в административном производстве:
они принадлежат управе, по чьей территории заявка. Адрес управы уже есть,
не хватало номера кабинета — он печатается в уведомлении о явке.

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-10-27 18:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("areas", sa.Column("office", sa.String(length=20), nullable=True))

    # Переноса из заявок нет: управы связаны с заявками через адрес, а не
    # таблицей связи, и угадывать соответствие нельзя. Номер кабинета
    # заполняется на странице «Управы».

def downgrade() -> None:
    op.drop_column("areas", "office")
