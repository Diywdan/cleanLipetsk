"""Restore the original confirmation wording in case history."""
from __future__ import annotations

import re

from alembic import op
import sqlalchemy as sa


revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


NEUTRAL = re.compile(
    r"^Инцидент подтверждён\. Исполнителю установлен срок устранения: "
    r"(\d+) ч\. Исполнитель: (.*?)\."
)
RESTORED = re.compile(r"^Уведомление направлено: (.*?), срок (\d+) ч\.")


def _rewrite(pattern: re.Pattern[str], replacement) -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            "SELECT id, description FROM case_history "
            "WHERE action = 'CONFIRM' AND description IS NOT NULL"
        )
    ).all()
    for row_id, description in rows:
        match = pattern.match(description)
        if match is None:
            continue
        updated = replacement(match, description[match.end():])
        connection.execute(
            sa.text("UPDATE case_history SET description = :description WHERE id = :id"),
            {"id": row_id, "description": updated},
        )


def upgrade() -> None:
    _rewrite(
        NEUTRAL,
        lambda match, suffix: (
            f"Уведомление направлено: {match.group(2)}, срок {match.group(1)} ч.{suffix}"
        ),
    )


def downgrade() -> None:
    _rewrite(
        RESTORED,
        lambda match, suffix: (
            f"Инцидент подтверждён. Исполнителю установлен срок устранения: "
            f"{match.group(2)} ч. Исполнитель: {match.group(1)}.{suffix}"
        ),
    )
