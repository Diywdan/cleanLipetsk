"""rename upravas to areas

В базе управа называется area, в интерфейсе остаётся «Управа»: терминологию
департамента не меняем, меняются только имена объектов базы.

Переименовываются таблицы, колонки связи, ключи и индексы — иначе
``alembic check`` увидит расхождение с моделями.

Revision ID: b4c5d6e7f8a9
Revises: a3b4c5d6e7f8
Create Date: 2026-10-12 22:10:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'b4c5d6e7f8a9'
down_revision: Union[str, None] = 'a3b4c5d6e7f8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLES = [
    ("upravas", "areas"),
    ("uprava_addresses", "area_addresses"),
    ("uprava_inspectors", "area_inspectors"),
]

COLUMNS = [
    ("area_addresses", "uprava_id", "area_id"),
    ("area_inspectors", "uprava_id", "area_id"),
]

CONSTRAINTS = [
    ("areas", "pk_upravas", "pk_areas"),
    ("areas", "fk_upravas_control_body_id_control_bodies",
     "fk_areas_control_body_id_control_bodies"),
    ("area_addresses", "pk_uprava_addresses", "pk_area_addresses"),
    ("area_addresses", "uq_uprava_address", "uq_area_address"),
    ("area_addresses", "fk_uprava_addresses_address_id_addresses",
     "fk_area_addresses_address_id_addresses"),
    ("area_addresses", "fk_uprava_addresses_uprava_id_upravas",
     "fk_area_addresses_area_id_areas"),
    ("area_inspectors", "pk_uprava_inspectors", "pk_area_inspectors"),
    ("area_inspectors", "uq_uprava_inspector", "uq_area_inspector"),
    ("area_inspectors", "fk_uprava_inspectors_inspector_id_inspectors",
     "fk_area_inspectors_inspector_id_inspectors"),
    ("area_inspectors", "fk_uprava_inspectors_uprava_id_upravas",
     "fk_area_inspectors_area_id_areas"),
]

INDEXES = [
    ("ix_upravas_control_body_id", "ix_areas_control_body_id"),
    ("ix_uprava_addresses_address_id", "ix_area_addresses_address_id"),
    ("ix_uprava_inspectors_inspector_id", "ix_area_inspectors_inspector_id"),
]


def upgrade() -> None:
    for old, new in TABLES:
        op.rename_table(old, new)
    for table, old, new in COLUMNS:
        op.alter_column(table, old, new_column_name=new)
    for table, old, new in CONSTRAINTS:
        op.execute(f"ALTER TABLE {table} RENAME CONSTRAINT {old} TO {new}")
    for old, new in INDEXES:
        op.execute(f"ALTER INDEX {old} RENAME TO {new}")


def downgrade() -> None:
    for old, new in INDEXES:
        op.execute(f"ALTER INDEX {new} RENAME TO {old}")
    for table, old, new in CONSTRAINTS:
        op.execute(f"ALTER TABLE {table} RENAME CONSTRAINT {new} TO {old}")
    for table, old, new in COLUMNS:
        op.alter_column(table, new, new_column_name=old)
    for old, new in TABLES:
        op.rename_table(new, old)
