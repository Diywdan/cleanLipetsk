"""Номер акта отдельно от номера мероприятия

Номер мероприятия вводит пользователь, и он же попадает в акт и предписание.
Если акту портал присвоил другой номер, его вносят отдельным полем: пустое
значение значит «взять номер мероприятия».

Revision ID: d2e3f4a5b6c7
Revises: c9d1e2f3a4b5
Create Date: 2026-10-14 11:40:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd2e3f4a5b6c7'
down_revision: Union[str, None] = 'c9d1e2f3a4b5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'control_cases',
        sa.Column('act_number', sa.String(length=50), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('control_cases', 'act_number')
