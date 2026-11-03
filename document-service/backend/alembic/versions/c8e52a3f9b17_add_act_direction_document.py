"""add act direction document to executed package

Письмо «О направлении акта выездного обследования» составляется, когда
нарушение устранено: в пакет об исполнении предписания входят задание,
протокол осмотра, акт и это письмо. Раньше в пакете было три документа —
письма не хватало.

Revision ID: c8e52a3f9b17
Revises: b7c41f2e8a55
Create Date: 2026-10-12 15:10:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'c8e52a3f9b17'
down_revision: Union[str, None] = 'b7c41f2e8a55'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO document_types (code, name, sort_order)
        VALUES ('act_direction',
                'О направлении акта выездного обследования',
                40)
        ON CONFLICT (code) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO package_kind_documents
               (package_kind_id, document_type_id, sequence_no)
        SELECT kind.id, type.id, 4
          FROM package_kinds AS kind, document_types AS type
         WHERE kind.code = 'executed_prescription'
           AND type.code = 'act_direction'
        ON CONFLICT (package_kind_id, document_type_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM package_kind_documents
         WHERE document_type_id = (SELECT id FROM document_types
                                    WHERE code = 'act_direction')
        """
    )
    op.execute("DELETE FROM document_types WHERE code = 'act_direction'")
