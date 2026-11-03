"""Работы по нарушениям: справочник работ и объёмы

Описание нарушения и требование предписания повторяли друг друга: в обоих
были адрес, перечень работ с объёмами, нормы и реквизиты акта. Здесь работы
выносятся в справочник, объёмы — к нарушению, а действие — к требованию.

* `works` — справочник работ: «асфальт», «грунт», «дорожный бордюр» с формой
  винительного падежа и единицей измерения;
* `violation_type_works` — какие работы подсказывать для вида нарушения;
* `violation_works` — работы конкретного нарушения с объёмом;
* `prescription_items.action_code` — действие, которое предписано выполнить.

Текст описания и требования теперь собирается из этих данных, поэтому одни и
те же значения не вписываются дважды.

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-10-27 16:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c9d0e1f2a3b4'
down_revision: Union[str, None] = 'b8c9d0e1f2a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# code, name, name_accusative, unit, is_measurable, sort_order
WORKS: list[tuple[str, str, str, str, bool, int]] = [
    ("asphalt", "асфальт", "асфальт", "кв.м.", True, 1),
    ("soil", "грунт", "грунт", "кв.м.", True, 2),
    ("road_border", "дорожный бордюр", "дорожный бордюр", "шт.", False, 3),
    ("curb_stone", "бортовой камень", "бортовой камень", "шт.", False, 4),
    ("lawn", "газон", "газон", "кв.м.", True, 5),
    ("tile", "плитка", "плитку", "кв.м.", True, 6),
    ("fence", "ограждение", "ограждение", "п.м.", True, 7),
    ("trash", "твёрдые коммунальные отходы", "твёрдые коммунальные отходы", "куб.м.", True, 8),
]

# Вид нарушения -> работы, которые подсказывать.
TYPE_WORKS: dict[str, list[str]] = {
    "unrestored_improvement": ["asphalt", "soil", "road_border", "lawn", "tile"],
    "yard_area_izh": ["asphalt", "lawn", "trash"],
    "yard_area_mkd": ["asphalt", "lawn", "trash"],
    "waste_piles": ["trash"],
    "container_overflow": ["trash"],
    "untimely_waste_removal": ["trash"],
    "territory_maintenance": ["trash", "lawn", "asphalt"],
    "roads_sidewalks_izh": ["asphalt", "curb_stone"],
    "green_spaces_mkd": ["lawn"],
    "facade_graffiti_mkd": ["tile"],
}


def upgrade() -> None:
    op.create_table(
        "works",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=500), nullable=False),
        sa.Column("name_accusative", sa.String(length=500)),
        sa.Column("unit", sa.String(length=50), nullable=False),
        sa.Column(
            "is_measurable", sa.Boolean(), nullable=False,
            server_default=sa.text("true"),
        ),
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
        sa.UniqueConstraint("code", name="uq_works_code"),
    )

    op.create_table(
        "violation_type_works",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("violation_type_id", sa.BigInteger(), nullable=False),
        sa.Column("work_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["violation_type_id"], ["violation_types.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["work_id"], ["works.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "violation_type_id", "work_id", name="uq_violation_type_works_type_work"
        ),
    )

    op.create_table(
        "violation_works",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("violation_id", sa.BigInteger(), nullable=False),
        sa.Column("work_id", sa.BigInteger(), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=14, scale=3)),
        sa.Column("sequence_no", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["violation_id"], ["violations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["work_id"], ["works.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "violation_id", "work_id", name="uq_violation_works_violation_work"
        ),
    )

    op.add_column(
        "prescription_items",
        sa.Column("action_code", sa.String(length=50)),
    )

    # Наполнение справочника работ: базовый набор по разобранному предписанию.
    connection = op.get_bind()
    for code, name, accusative, unit, measurable, order in WORKS:
        connection.execute(
            sa.text(
                """
                INSERT INTO works
                       (code, name, name_accusative, unit, is_measurable, sort_order)
                VALUES (:code, :name, :accusative, :unit, :measurable, :order)
                ON CONFLICT (code) DO NOTHING
                """
            ),
            {
                "code": code,
                "name": name,
                "accusative": accusative,
                "unit": unit,
                "measurable": measurable,
                "order": order,
            },
        )

    for type_code, work_codes in TYPE_WORKS.items():
        for work_code in work_codes:
            connection.execute(
                sa.text(
                    """
                    INSERT INTO violation_type_works (violation_type_id, work_id)
                    SELECT kind.id, work.id
                      FROM violation_types kind, works work
                     WHERE kind.code = :type_code AND work.code = :work_code
                    ON CONFLICT (violation_type_id, work_id) DO NOTHING
                    """
                ),
                {"type_code": type_code, "work_code": work_code},
            )


def downgrade() -> None:
    op.drop_column("prescription_items", "action_code")
    op.drop_table("violation_works")
    op.drop_table("violation_type_works")
    op.drop_table("works")
