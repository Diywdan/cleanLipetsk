"""fix violation type articles types

Таблица связи видов нарушений с нормами была создана с целочисленными
ключами вместо BigInteger и с метками времени без умолчаний — так, как
их задают примеси IntIdMixin и TimestampMixin. Данных в таблице нет,
поэтому она пересоздаётся в правильном виде.

Revision ID: f2c3d4e5a6b7
Revises: e1b2c3d4f5a6
Create Date: 2026-10-12 20:25:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'f2c3d4e5a6b7'
down_revision: Union[str, None] = 'e1b2c3d4f5a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table("violation_type_articles")
    op.create_table(
        "violation_type_articles",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("violation_type_id", sa.BigInteger(), nullable=False),
        sa.Column("npa_article_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
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


def downgrade() -> None:
    op.drop_table("violation_type_articles")
