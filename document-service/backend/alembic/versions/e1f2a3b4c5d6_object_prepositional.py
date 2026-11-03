"""Объект контроля: название в предложном падеже

Для описания нарушения нужна форма «на земельном участке, расположенном по
адресу …». Родительный падеж у объекта уже есть, предложного не было —
добавляем: иначе пришлось бы брать родительный и получалось «на земельного
участка».

Заодно требование предписания описывает, что именно сделать: у вида
нарушения появляется форма в винительном падеже — «нарушенное благоустройство
в полном объёме после производства земляных работ».

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-10-27 17:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e1f2a3b4c5d6'
down_revision: Union[str, None] = 'd0e1f2a3b4c5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "control_objects",
        sa.Column("name_prepositional", sa.String(length=1000)),
    )

    connection = op.get_bind()

    # «земельный участок, расположенный по адресу …» ->
    # «земельном участке, расположенном по адресу …».
    connection.execute(
        sa.text(
            """
            update control_objects
               set name_prepositional = replace(
                       replace(name_genitive, 'Земельного участка', 'земельном участке'),
                       'расположенного', 'расположенном')
             where name_genitive is not null
               and name_prepositional is null
            """
        )
    )
    # Если родительного падежа нет — собираем из названия.
    connection.execute(
        sa.text(
            """
            update control_objects
               set name_prepositional = replace(
                       replace(name, 'земельный участок', 'земельном участке'),
                       'расположенный', 'расположенном')
             where name_prepositional is null
               and name is not null
            """
        )
    )

    # Что именно выполнить по предписанию: «восстановить нарушенное
    # благоустройство в полном объёме после производства земляных работ».
    connection.execute(
        sa.text(
            """
            update violation_types
               set requirement_object = name_accusative
             where code = 'unrestored_improvement'
               and name_accusative is not null
            """
        )
    )


def downgrade() -> None:
    op.drop_column("control_objects", "name_prepositional")
