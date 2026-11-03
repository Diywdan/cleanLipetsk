"""Управы: адрес управы

Место составления протокола об административном правонарушении — адрес
управы, по чьей территории заявка. Раньше это поле вписывали руками (и в
заявке 122313 в нём оказался адрес из образца). Теперь адрес хранится у
управы и выбирается из общего справочника адресов.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-10-27 17:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("areas", sa.Column("address_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        "fk_areas_address_id", "areas", "addresses", ["address_id"], ["id"]
    )

    # Адрес департамента уже есть в справочнике органов: если у управы адреса
    # нет, подставлять будем его, поэтому управы получают тот же адрес, что и
    # их орган контроля.
    connection = op.get_bind()
    connection.execute(
        sa.text(
            """
            update areas a
               set address_id = b.address_id
              from control_bodies b
             where b.id = a.control_body_id
               and a.address_id is null
            """
        )
    )


def downgrade() -> None:
    op.drop_constraint("fk_areas_address_id", "areas", type_="foreignkey")
    op.drop_column("areas", "address_id")
