"""Виды нарушений: формулировка «что не сделано» и действие по умолчанию

Описание нарушения и требование предписания собираются из справочников.
Чтобы текст складывался без ручного ввода, у вида нарушения появляются:

* `name_accusative` — что именно не сделано: «нарушенное благоустройство в
  полном объёме после производства земляных работ»;
* `requirement_object` — что предписано: «восстановление нарушенного
  благоустройства в полном объёме…»;
* `default_action` — действие по умолчанию: `restore`.

Заодно наполняются работы по разобранному нарушению и проставляется действие
уже заведённым предписаниям, чтобы требование по ним собиралось из данных.
Поле `requirement_text` остаётся: по нему воспроизводятся уже выданные
документы.

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-10-27 16:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd0e1f2a3b4c5'
down_revision: Union[str, None] = 'c9d0e1f2a3b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Формулировки для видов нарушений: код -> (что не сделано, что предписано)
TYPES: dict[str, tuple[str, str]] = {
    "unrestored_improvement": (
        "нарушенное благоустройство в полном объёме после производства "
        "земляных работ",
        "восстановление нарушенного благоустройства в полном объёме после "
        "производства земляных работ",
    ),
    "container_overflow": (
        "своевременный вывоз твёрдых коммунальных отходов",
        "вывоз твёрдых коммунальных отходов",
    ),
    "untimely_waste_removal": (
        "своевременный вывоз твёрдых коммунальных отходов",
        "вывоз твёрдых коммунальных отходов",
    ),
    "waste_piles": (
        "уборка навалов мусора",
        "уборку навалов мусора",
    ),
    "territory_maintenance": (
        "надлежащее содержание территории",
        "надлежащее содержание территории",
    ),
    "yard_area_izh": (
        "надлежащее содержание дворовой территории",
        "надлежащее содержание дворовой территории",
    ),
    "yard_area_mkd": (
        "надлежащее содержание дворовой территории",
        "надлежащее содержание дворовой территории",
    ),
    "roads_sidewalks_izh": (
        "надлежащее содержание дорог и тротуаров",
        "надлежащее содержание дорог и тротуаров",
    ),
    "green_spaces_mkd": (
        "надлежащее содержание зелёных насаждений",
        "надлежащее содержание зелёных насаждений",
    ),
}

# Действие по умолчанию: почти везде «восстановить», у уборки — «убрать».
DEFAULT_ACTIONS: dict[str, str] = {
    "waste_piles": "remove",
    "container_overflow": "remove",
    "untimely_waste_removal": "remove",
    "facade_graffiti_mkd": "clean",
}


def upgrade() -> None:
    op.add_column(
        "violation_types", sa.Column("name_accusative", sa.String(length=500))
    )
    op.add_column(
        "violation_types", sa.Column("requirement_object", sa.String(length=500))
    )
    op.add_column(
        "violation_types", sa.Column("default_action", sa.String(length=50))
    )

    connection = op.get_bind()

    for code, (accusative, requirement) in TYPES.items():
        connection.execute(
            sa.text(
                """
                update violation_types
                   set name_accusative = :accusative,
                       requirement_object = :requirement,
                       default_action = :action
                 where code = :code
                """
            ),
            {
                "accusative": accusative,
                "requirement": requirement,
                "action": DEFAULT_ACTIONS.get(code, "restore"),
                "code": code,
            },
        )

    # Работы по уже заведённому нарушению — из разобранного предписания:
    # «асфальт – 4 кв.м., грунт – 20 кв.м., дорожный бордюр – 4 шт.».
    connection.execute(
        sa.text(
            """
            insert into violation_works (violation_id, work_id, quantity, sequence_no)
            select v.id, w.id, q.quantity, q.sequence_no
              from violations v
              join violation_types t on t.id = v.violation_type_id
              join (values ('asphalt', 4, 1), ('soil', 20, 2),
                           ('road_border', 4, 3)) as q(code, quantity, sequence_no)
                on true
              join works w on w.code = q.code
             where t.code = 'unrestored_improvement'
               and not exists (
                     select 1 from violation_works vw
                      where vw.violation_id = v.id and vw.work_id = w.id)
            """
        )
    )

    # Действие у уже заведённых предписаний: требование собирается из данных.
    connection.execute(
        sa.text(
            """
            update prescription_items i
               set action_code = coalesce(t.default_action, 'restore')
              from prescriptions p
              join violations v on v.control_case_id = p.control_case_id
              join violation_types t on t.id = v.violation_type_id
             where i.prescription_id = p.id
               and i.action_code is null
            """
        )
    )


def downgrade() -> None:
    op.drop_column("violation_types", "default_action")
    op.drop_column("violation_types", "requirement_object")
    op.drop_column("violation_types", "name_accusative")
