"""address search key and gar guid

Добавляет приведённый к единому виду адрес (search_key) и идентификатор ГАР.
Существующие адреса заполняются сразу: без этого поиск и «найти или создать»
не увидели бы уже заведённые записи и начали бы плодить дубли.

Revision ID: cdf4c736d144
Revises: b50ee2bed541
Create Date: 2026-10-09 12:16:29.678450

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cdf4c736d144'
down_revision: Union[str, None] = 'b50ee2bed541'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('addresses', sa.Column('gar_guid', sa.String(length=36), nullable=True))
    op.add_column('addresses', sa.Column('search_key', sa.String(length=500), nullable=True))
    op.create_index(op.f('ix_addresses_gar_guid'), 'addresses', ['gar_guid'], unique=False)
    op.create_index(op.f('ix_addresses_search_key'), 'addresses', ['search_key'], unique=False)

    # Приведение существующих адресов к тому же виду, что делает
    # app.services.addresses.normalize: обрезка, ё -> е, без точек,
    # одиночные пробелы, нижний регистр.
    op.execute(
        """
        update addresses
           set search_key = lower(
                 regexp_replace(
                   replace(replace(
                     regexp_replace(btrim(full_address, ' .,;'), '\\s+', ' ', 'g'),
                     'ё', 'е'),
                     'Ё', 'Е'),
                   '\\.', '', 'g'))
         where search_key is null
        """
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_addresses_search_key'), table_name='addresses')
    op.drop_index(op.f('ix_addresses_gar_guid'), table_name='addresses')
    op.drop_column('addresses', 'search_key')
    op.drop_column('addresses', 'gar_guid')
