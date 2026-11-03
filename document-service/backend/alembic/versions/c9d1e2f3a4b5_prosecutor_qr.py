"""QR-код из прокуратуры в заявке

QR-код выдаёт портал прокуратуры вместе с номером мероприятия: система его
не генерирует, а принимает загруженную картинку и печатает в акте и
предписании. Хранится как обычный файл, поэтому в заявке достаточно ссылки.

Revision ID: c9d1e2f3a4b5
Revises: b4c5d6e7f8a9
Create Date: 2026-10-14 09:10:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c9d1e2f3a4b5'
down_revision: Union[str, None] = 'b4c5d6e7f8a9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'control_cases',
        sa.Column('qr_file_id', sa.BigInteger(), nullable=True),
    )
    op.create_foreign_key(
        'fk_control_cases_qr_file',
        'control_cases',
        'files',
        ['qr_file_id'],
        ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint('fk_control_cases_qr_file', 'control_cases', type_='foreignkey')
    op.drop_column('control_cases', 'qr_file_id')
