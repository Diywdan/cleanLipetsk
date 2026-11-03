"""Чистка справочника формулировок от значений из старых заявок."""
from __future__ import annotations

from sqlalchemy import text

from app.db.session import SessionLocal


def main() -> None:
    db = SessionLocal()
    try:
        removed = db.execute(
            text("delete from case_text_options where sort_order = 100 returning id")
        ).fetchall()
        db.commit()
        print(f"удалено записей: {len(removed)}")
        rows = db.execute(
            text(
                "select id, kind, sort_order, value from case_text_options "
                "order by kind, sort_order"
            )
        ).fetchall()
        for row in rows:
            print(f"  {row.kind:<8} #{row.sort_order} {row.value[:80]}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
