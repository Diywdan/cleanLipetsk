"""rename control areas to upravas

Переименование по терминологии департамента: «участок» → «управа».
Заодно убирается описание управы — в департаменте его не ведут.

Таблицы переименовываются, а не пересоздаются: адреса управ и закрепления
инспекторов должны сохраниться. Вместе с таблицами переименовываются
ограничения и индексы — иначе их имена остались бы от прежнего названия
и разошлись бы с именами, которые задаёт модель.

Revision ID: e5b2c7a91d34
Revises: d1a0cbec7c6c
Create Date: 2026-10-09 13:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5b2c7a91d34'
down_revision: Union[str, None] = 'd1a0cbec7c6c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Таблицы, колонки, ограничения и индексы: старое имя → новое.
TABLES = [
    ('control_areas', 'upravas'),
    ('control_area_addresses', 'uprava_addresses'),
    ('control_area_inspectors', 'uprava_inspectors'),
]

COLUMNS = [
    ('uprava_addresses', 'area_id', 'uprava_id'),
    ('uprava_inspectors', 'area_id', 'uprava_id'),
]

CONSTRAINTS = [
    ('upravas', 'pk_control_areas', 'pk_upravas'),
    ('upravas', 'fk_control_areas_control_body_id_control_bodies',
     'fk_upravas_control_body_id_control_bodies'),
    ('uprava_addresses', 'pk_control_area_addresses', 'pk_uprava_addresses'),
    ('uprava_addresses', 'uq_control_area_address', 'uq_uprava_address'),
    ('uprava_addresses', 'fk_control_area_addresses_address_id_addresses',
     'fk_uprava_addresses_address_id_addresses'),
    ('uprava_addresses', 'fk_control_area_addresses_area_id_control_areas',
     'fk_uprava_addresses_uprava_id_upravas'),
    ('uprava_inspectors', 'pk_control_area_inspectors', 'pk_uprava_inspectors'),
    ('uprava_inspectors', 'uq_control_area_inspector', 'uq_uprava_inspector'),
    ('uprava_inspectors', 'fk_control_area_inspectors_inspector_id_inspectors',
     'fk_uprava_inspectors_inspector_id_inspectors'),
    ('uprava_inspectors', 'fk_control_area_inspectors_area_id_control_areas',
     'fk_uprava_inspectors_uprava_id_upravas'),
]

INDEXES = [
    ('ix_control_areas_control_body_id', 'ix_upravas_control_body_id'),
    ('ix_control_area_addresses_address_id', 'ix_uprava_addresses_address_id'),
    ('ix_control_area_inspectors_inspector_id', 'ix_uprava_inspectors_inspector_id'),
]


def upgrade() -> None:
    for old, new in TABLES:
        op.rename_table(old, new)
    for table, old, new in COLUMNS:
        op.alter_column(table, old, new_column_name=new)
    for table, old, new in CONSTRAINTS:
        op.execute(f'ALTER TABLE {table} RENAME CONSTRAINT {old} TO {new}')
    for old, new in INDEXES:
        op.execute(f'ALTER INDEX {old} RENAME TO {new}')
    # Описание управы в департаменте не ведут.
    op.drop_column('upravas', 'description')


def downgrade() -> None:
    op.add_column('upravas', sa.Column('description', sa.Text(), nullable=True))
    for old, new in INDEXES:
        op.execute(f'ALTER INDEX {new} RENAME TO {old}')
    for table, old, new in CONSTRAINTS:
        op.execute(f'ALTER TABLE {table} RENAME CONSTRAINT {new} TO {old}')
    for table, old, new in COLUMNS:
        op.alter_column(table, new, new_column_name=old)
    for old, new in TABLES:
        op.rename_table(new, old)
