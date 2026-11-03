"""add violation kinds and their links to norms

Заводится справочник видов нарушений из мобильного приложения диспетчера
аварийных заявок и связь «вид нарушения — норма права».

Признак ИЖ — отдельное поле, а не часть названия: нарушение по существу
одно, но нормы и юрисликция разные. Снятая галочка означает МКД, таких
видов большинство, и это состояние по умолчанию.

Из списка приложения убрана «Консультация» (это не нарушение) и объединены
две записи «Уборка дорог»: в приложении они различаются только уточнением,
а у нас уточнение задаётся признаком ИЖ.

Revision ID: e1b2c3d4f5a6
Revises: 65ef2f09c1f3
Create Date: 2026-10-12 20:05:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'e1b2c3d4f5a6'
down_revision: Union[str, None] = '65ef2f09c1f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (код, название, признак ИЖ)
KINDS: list[tuple[str, str, bool]] = [
    ("stray_animals_izh", "Бродячие животные (ИЖ)", True),
    ("stray_animals_mkd", "Бродячие животные (МКД)", False),
    ("yard_area_izh", "Дворовая территория (ИЖ)", True),
    ("yard_area_mkd", "Дворовая территория (МКД)", False),
    ("outdoor_lighting_izh", "Наружное освещение (ИЖ)", True),
    ("outdoor_lighting_mkd", "Наружное освещение (МКД)", False),
    (
        "owners_meeting_order_mkd",
        "Нарушение порядка проведения общих собраний собственников (МКД)",
        False,
    ),
    (
        "facade_graffiti_mkd",
        "Несанкционированные надписи, рисунки, реклама на фасаде "
        "многоквартирного дома (МКД)",
        False,
    ),
    (
        "new_waste_site_mkd",
        "Организация новой контейнерной площадки ТКО (МКД)",
        False,
    ),
    (
        "missing_manholes_izh",
        "Отсутствие люков на коммуникационных колодцах (ИЖ)",
        True,
    ),
    (
        "missing_manholes_mkd",
        "Отсутствие люков на коммуникационных колодцах (МКД)",
        False,
    ),
    ("snow_cleaning_izh", "Очистка от снега (ИЖ)", True),
    ("snow_cleaning_mkd", "Очистка от снега (МКД)", False),
    (
        "waste_collection_izh",
        "Сбор и вывоз твёрдых коммунальных отходов (ИЖ)",
        True,
    ),
    (
        "waste_collection_mkd",
        "Сбор и вывоз твёрдых коммунальных отходов (МКД)",
        False,
    ),
    (
        "playgrounds_maintenance_mkd",
        "Содержание детских и спортивных площадок (МКД)",
        False,
    ),
    (
        "roads_maintenance_yards_mkd",
        "Содержание дорог (в части дворовых территорий) (МКД)",
        False,
    ),
    (
        "green_spaces_mkd",
        "Содержание зелёных насаждений, покос травы (МКД)",
        False,
    ),
    (
        "apartment_adjacent_area_mkd",
        "Содержание МКД и придомовой территории "
        "(в части придомовой территории) (МКД)",
        False,
    ),
    ("waste_site_condition_izh", "Состояние контейнерной площадки (ИЖ)", True),
    ("waste_site_condition_mkd", "Состояние контейнерной площадки (МКД)", False),
    ("icicles_mkd", "Сосульки (наледь) (МКД)", False),
    (
        "roads_sidewalks_izh",
        "Строительство и содержание дорог и тротуаров (ИЖ)",
        True,
    ),
    ("road_sweeping_mkd", "Уборка дорог (МКД)", False),
    (
        "waste_site_surroundings_mkd",
        "Уборка мусора вокруг площадки ТКО (МКД)",
        False,
    ),
]


def upgrade() -> None:
    op.add_column(
        "violation_types",
        sa.Column(
            "is_individual_housing",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.create_table(
        "violation_type_articles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("violation_type_id", sa.Integer(), nullable=False),
        sa.Column("npa_article_id", sa.Integer(), nullable=False),
        sa.Column(
            "is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["violation_type_id"], ["violation_types.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["npa_article_id"], ["npa_articles.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "violation_type_id",
            "npa_article_id",
            name="uq_violation_type_articles_type_article",
        ),
    )

    for order, (code, name, is_izh) in enumerate(KINDS, start=1):
        op.execute(
            sa.text(
                """
                INSERT INTO violation_types
                       (code, name, sort_order, is_active, is_individual_housing)
                VALUES (:code, :name, :order, true, :is_izh)
                ON CONFLICT (code) DO UPDATE
                   SET name = EXCLUDED.name,
                       sort_order = EXCLUDED.sort_order,
                       is_individual_housing = EXCLUDED.is_individual_housing
                """
            ).bindparams(code=code, name=name, order=order * 10, is_izh=is_izh)
        )


def downgrade() -> None:
    for code, _, _ in KINDS:
        op.execute(
            sa.text("DELETE FROM violation_types WHERE code = :code").bindparams(
                code=code
            )
        )
    op.drop_table("violation_type_articles")
    op.drop_column("violation_types", "is_individual_housing")
