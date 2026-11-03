"""Сквозная нумерация заявок

Внутренний номер заявки присваивает система, вручную он не меняется: номер
сквозной для всех пользователей. Последовательность в базе гарантирует
разные номера при одновременной работе, а уже выданные номера не
переиспользуются.

Уже существующим заявкам номер проставляется здесь же: без этого уникальный
индекс не создать, а заявки без номера выглядели бы в интерфейсе как «—».

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
Create Date: 2026-10-14 12:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e3f4a5b6c7d8'
down_revision: Union[str, None] = 'd2e3f4a5b6c7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SEQUENCE = 'control_case_number_seq'
WIDTH = 6


def upgrade() -> None:
    op.execute(sa.text(f"create sequence if not exists {SEQUENCE}"))

    # Номера существующих заявок: пустые заполняем по порядку номеров дела.
    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            "select id from control_cases "
            "where case_number is null or btrim(case_number) = '' "
            "order by id"
        )
    ).fetchall()
    for (case_id,) in rows:
        value = connection.execute(
            sa.text(f"select nextval('{SEQUENCE}')")
        ).scalar()
        connection.execute(
            sa.text(
                "update control_cases set case_number = :number where id = :id"
            ),
            {"number": f"{int(value):0{WIDTH}d}", "id": case_id},
        )

    # Номер уникален: две заявки с одним номером сломали бы и поиск, и письма.
    op.create_index(
        'uq_control_cases_case_number',
        'control_cases',
        ['case_number'],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index('uq_control_cases_case_number', table_name='control_cases')
    op.execute(sa.text(f"drop sequence if exists {SEQUENCE}"))
