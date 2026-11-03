"""Справочник норм: убрать название акта из строк и дубль акта

В справочнике «Правила благоустройства территорий города Липецка» был заведён
дважды: один акт с тремя нормами (ими и пользуются нарушения) и второй с 51
нормой, у которого в каждой готовой строке вписано название акта. Из-за этого
в интерфейсе нормы выглядели как «часть 12 статьи 14 Правил благоустройства
территорий города Липецка — Правила благоустройства территорий города
Липецка»: название повторялось.

Что делает миграция:

* убирает название акта из готовых строк — название печатается отдельно, из
  самого акта, поэтому в строке нормы его быть не должно;
* заполняет родительный падеж названия акта там, где его не было (без него
  документы печатали название в именительном падеже);
* удаляет дубль акта вместе с его нормами, если на эти нормы ничто не
  ссылается.

Revision ID: a7b8c9d0e1f2
Revises: f4a5b6c7d8e9
Create Date: 2026-10-27 14:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7b8c9d0e1f2'
down_revision: Union[str, None] = 'f4a5b6c7d8e9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TITLE = 'Правила благоустройства территорий города Липецка'
TITLE_GENITIVE = 'Правил благоустройства территорий города Липецка'
SUFFIX = ' Правил благоустройства территорий города Липецка'


def upgrade() -> None:
    connection = op.get_bind()

    # 1. Название акта — отдельно, в строке нормы его быть не должно.
    connection.execute(
        sa.text(
            "update npa_articles "
            "set reference_template = btrim(replace(reference_template, :suffix, '')) "
            "where reference_template like :pattern"
        ),
        {"suffix": SUFFIX, "pattern": f"%{SUFFIX.strip()}%"},
    )

    # 2. Родительный падеж названия: без него в документах именительный.
    connection.execute(
        sa.text(
            "update npa set title_genitive = :genitive "
            "where title = :title and (title_genitive is null "
            "or btrim(title_genitive) = '')"
        ),
        {"genitive": TITLE_GENITIVE, "title": TITLE},
    )

    # 3. Дубль акта: у одного и того же акта (тот же номер и дата) оставляем
    #    тот, на нормы которого ссылаются; остальные удаляем, если на их
    #    нормы ссылок нет.
    rows = connection.execute(
        sa.text(
            """
            select n.id,
                   (select count(*) from npa_articles a where a.npa_id = n.id) as norms,
                   (select count(*) from violation_provisions p
                      join npa_articles a on a.id = p.npa_article_id
                     where a.npa_id = n.id) as violation_refs,
                   (select count(*) from prescription_items i
                      join npa_articles a on a.id = i.npa_article_id
                     where a.npa_id = n.id) as prescription_refs,
                   (select count(*) from decision_items i
                      join npa_articles a on a.id = i.npa_article_id
                     where a.npa_id = n.id) as decision_refs
              from npa n
             where n.title = :title
             order by n.id
            """
        ),
        {"title": TITLE},
    ).fetchall()

    if len(rows) > 1:
        used = [row for row in rows if (row.violation_refs + row.prescription_refs
                                        + row.decision_refs) > 0]
        # Если хоть что-то ссылается — оставляем акт со ссылками.
        keep = used[0].id if used else max(rows, key=lambda row: row.norms).id
        for row in rows:
            if row.id == keep:
                continue
            if (row.violation_refs + row.prescription_refs + row.decision_refs) > 0:
                continue
            connection.execute(
                sa.text("delete from npa_articles where npa_id = :id"), {"id": row.id}
            )
            connection.execute(
                sa.text("delete from npa where id = :id"), {"id": row.id}
            )


def downgrade() -> None:
    # Возвращать дубль и вписанные названия не нужно: данные исправлены,
    # а не преобразованы. Откат оставляет справочник в очищенном виде.
    pass
