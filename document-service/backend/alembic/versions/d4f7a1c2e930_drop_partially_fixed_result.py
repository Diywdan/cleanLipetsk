"""drop partially fixed inspection result

Промежуточный результат «устранено частично» убран: от результата осмотра
зависит, какой пакет собирать дальше, а частичный результат не даёт
однозначного ответа — нарушение либо снято, либо нет.

Уже записанные значения переводятся в «нарушение не устранено»: частично
устранённое нарушение требует вторичного предписания, то есть того же
пути, что и неустранённое.

Значение остаётся в справочнике кода: PostgreSQL не умеет удалять значение
перечисления из существующего типа, а столбец хранит строку. Ограничение
теперь задаёт приложение.

Revision ID: d4f7a1c2e930
Revises: eb55bc60cef2
Create Date: 2026-10-12 18:20:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'd4f7a1c2e930'
down_revision: Union[str, None] = 'eb55bc60cef2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "UPDATE control_actions SET inspection_result = 'not_fixed' "
        "WHERE inspection_result = 'partially_fixed'"
    )


def downgrade() -> None:
    # Разделить «не устранено» обратно на «не устранено» и «устранено
    # частично» нельзя: сведения о частичном устранении не сохранены.
    pass
