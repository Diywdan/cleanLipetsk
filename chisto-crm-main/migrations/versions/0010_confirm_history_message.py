"""Use accurate wording for the incident confirmation history entry."""
from __future__ import annotations

import re

from alembic import op
import sqlalchemy as sa


revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


OLD = re.compile(r"^Уведомление (?:направлено|отправлено): (.*?), срок (\d+) ч\.")
NEW = re.compile(
    r"^Инцидент подтвержден\. Исполнитель: (.*?); срок устранения — (\d+) ч\."
)


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
        OLD,
        lambda match, suffix: (
            f"Инцидент подтвержден. Исполнитель: {match.group(1)}; "
            f"срок устранения — {match.group(2)} ч.{suffix}"
        ),
    )


def downgrade() -> None:
    _rewrite(
        NEW,
        lambda match, suffix: (
            f"Уведомление направлено: {match.group(1)}, срок {match.group(2)} ч.{suffix}"
        ),
    )
