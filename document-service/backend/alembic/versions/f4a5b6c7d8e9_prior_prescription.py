"""Прошлое предписание в административном производстве

Протокол об административном правонарушении по части 1 статьи 19.5 КоАП
описывает неисполнение ранее выданного предписания. Чтобы этот текст
собирался из данных, а не вписывался в бланк, у производства появляются
поля о том предписании: дата, номер, срок исполнения и статья НПА, по
которой оно выдано.

Revision ID: f4a5b6c7d8e9
Revises: e3f4a5b6c7d8
Create Date: 2026-10-27 14:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f4a5b6c7d8e9'
down_revision: Union[str, None] = 'e3f4a5b6c7d8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'administrative_cases',
        sa.Column('prior_prescription_number', sa.String(length=50)),
    )
    op.add_column(
        'administrative_cases',
        sa.Column('prior_prescription_date', sa.Date()),
    )
    op.add_column(
        'administrative_cases',
        sa.Column('prior_prescription_due', sa.Date()),
    )
    op.add_column(
        'administrative_cases',
        sa.Column('prior_prescription_basis', sa.String(length=255)),
    )


def downgrade() -> None:
    op.drop_column('administrative_cases', 'prior_prescription_basis')
    op.drop_column('administrative_cases', 'prior_prescription_due')
    op.drop_column('administrative_cases', 'prior_prescription_date')
    op.drop_column('administrative_cases', 'prior_prescription_number')
