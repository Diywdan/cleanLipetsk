"""external problems

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-15 10:00:00

Дела не только с обхода: проблема из домовых чатов (Домовой ГЖИ → DG → CRM) приходит без
инженера, назначения и участка, а исполнитель и тип могут не найтись в справочнике — эти поля
дела становятся необязательными. Ключ проблемы в источнике (external_key) и её ревизия
связывают повторные события с одним делом; external — сводка источника (площадка, тема,
дома, учтённые сообщения).
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None

OPTIONAL = ('engineer_id', 'executor_id', 'type_violation_id', 'assignment_id', 'territory_id')
Json = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql')


def upgrade() -> None:
    with op.batch_alter_table('cases', schema=None) as batch_op:
        for column in OPTIONAL:
            batch_op.alter_column(column, existing_type=sa.String(length=64), nullable=True)
        batch_op.add_column(sa.Column('external_key', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('external_revision', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('external', Json, nullable=True))
        batch_op.create_index(batch_op.f('ix_cases_external_key'), ['external_key'], unique=True)


def downgrade() -> None:
    # Дела без обязательных полей (из домовых чатов) в старую схему не помещаются — откат их удаляет.
    op.execute(sa.text(
        "DELETE FROM case_history WHERE case_id IN (SELECT id FROM cases WHERE external_key IS NOT NULL)"
    ))
    op.execute(sa.text("DELETE FROM cases WHERE external_key IS NOT NULL"))
    with op.batch_alter_table('cases', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_cases_external_key'))
        batch_op.drop_column('external')
        batch_op.drop_column('external_revision')
        batch_op.drop_column('external_key')
        for column in OPTIONAL:
            batch_op.alter_column(column, existing_type=sa.String(length=64), nullable=False)
