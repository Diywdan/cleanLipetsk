"""Цель проведения и предмет заявки — списки формулировок

Цель и предмет вписывались в каждую заявку руками длинными юридическими
фразами: опечатка меняла текст документа, а одинаковые заявки выглядели
по-разному. Здесь заводится справочник готовых формулировок и его начальное
наполнение — те фразы, что уже используются в заявках.

Формулировка в заявке остаётся текстом: если запись справочника потом
поправят, уже выданные документы не изменятся.

Revision ID: a1b2c3d4e5f6
Revises: f2a3b4c5d6e7
Create Date: 2026-10-27 17:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'f2a3b4c5d6e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


PURPOSE = (
    "Оценка соблюдения контролируемым лицом обязательных требований "
    "действующего законодательства, проверка фактов, изложенных в материале "
    "МУ «Управление главного смотрителя г. Липецка»"
)

SUBJECT = "Соблюдение обязательных требований действующего законодательства"

# Список по умолчанию: первая строка подставляется в новую заявку.
DEFAULTS: list[tuple[str, str, int]] = [
    ("purpose", PURPOSE, 0),
    ("subject", SUBJECT, 0),
]


def upgrade() -> None:
    op.create_table(
        "case_text_options",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("kind", "value", name="uq_case_text_options_kind_value"),
    )
    op.create_index(
        "ix_case_text_options_kind", "case_text_options", ["kind", "sort_order"]
    )

    connection = op.get_bind()
    for kind, text, order in DEFAULTS:
        connection.execute(
            sa.text(
                """
                insert into case_text_options (kind, value, sort_order)
                values (:kind, :value, :order)
                on conflict (kind, value) do nothing
                """
            ),
            {"kind": kind, "value": text, "order": order},
        )

    # Значения из уже созданных заявок в список НЕ переносим: в заявках
    # бывает текст обращения ("куча шин у площадки"), и он засорил бы
    # справочник юридических формулировок. Своя формулировка заявки всё равно
    # видна в её карточке отдельным вариантом.


def downgrade() -> None:
    op.drop_index("ix_case_text_options_kind", table_name="case_text_options")
    op.drop_table("case_text_options")
