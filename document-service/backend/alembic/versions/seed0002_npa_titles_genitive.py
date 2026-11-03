"""npa titles in genitive case

Название нормативного акта в родительном падеже: в протоколе осмотра
нарушение квалифицируется как «в нарушении … Правил благоустройства
территорий города Липецка».

Revision ID: seed0002
Revises: ae18a8699978
Create Date: 2026-10-08

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "seed0002"
down_revision: Union[str, None] = "ae18a8699978"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TITLES = {
    "836": "Правил благоустройства территорий города Липецка",
    "248-ФЗ": "Федерального закона от 31.07.2020 № 248-ФЗ",
    "195-ФЗ": "Кодекса Российской Федерации об административных правонарушениях",
}


def upgrade() -> None:
    for number, title in TITLES.items():
        escaped = title.replace("'", "''")
        op.execute(
            "UPDATE npa SET title_genitive = "
            f"'{escaped}' WHERE number = '{number}'"
        )


def downgrade() -> None:
    op.execute("UPDATE npa SET title_genitive = NULL")
