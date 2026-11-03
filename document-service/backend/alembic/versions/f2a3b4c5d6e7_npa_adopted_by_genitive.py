"""НПА: название органа в родительном падеже

В требовании предписания реквизиты акта печатаются так: «Правил
благоустройства территорий города Липецка от 28.11.2024 № 836, утверждённых
решением Липецкого городского Совета депутатов». Название органа нужно в
родительном падеже, а в карточке акта оно хранится в именительном.

У федеральных законов оборота «утверждённых решением» нет, поэтому поле
остаётся пустым, и оборот не печатается.

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-10-27 17:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f2a3b4c5d6e7'
down_revision: Union[str, None] = 'e1f2a3b4c5d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Акт (номер) -> орган в родительном падеже.
ADOPTED_BY_GENITIVE: list[tuple[str, str]] = [
    ("836", "Липецкого городского Совета депутатов"),
]


def upgrade() -> None:
    op.add_column(
        "npa", sa.Column("adopted_by_genitive", sa.String(length=500))
    )

    connection = op.get_bind()
    for number, genitive in ADOPTED_BY_GENITIVE:
        connection.execute(
            sa.text(
                "update npa set adopted_by_genitive = :genitive "
                "where number = :number"
            ),
            {"genitive": genitive, "number": number},
        )


def downgrade() -> None:
    op.drop_column("npa", "adopted_by_genitive")
