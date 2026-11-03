"""Дубль акта в справочнике норм: что на него ссылается."""
from __future__ import annotations

from sqlalchemy import select, text

from app.db.session import SessionLocal
from app.models import Npa, NpaArticle


def main() -> None:
    db = SessionLocal()
    try:
        for npa_id in (2, 4):
            npa = db.get(Npa, npa_id)
            articles = list(
                db.scalars(select(NpaArticle).where(NpaArticle.npa_id == npa_id))
            )
            ids = [a.id for a in articles]
            print(f"НПА {npa_id}: {npa.title!r}")
            print(f"  родительный: {npa.title_genitive!r}")
            print(f"  норм: {len(articles)}")

            for table, column in (
                ("violation_provisions", "npa_article_id"),
                ("prescription_items", "npa_article_id"),
                ("decision_items", "npa_article_id"),
            ):
                try:
                    count = db.scalar(
                        text(
                            f"select count(*) from {table} where {column} = any(:ids)"
                        ),
                        {"ids": ids},
                    )
                except Exception as exc:  # noqa: BLE001
                    db.rollback()
                    print(f"  {table}.{column}: таблицы нет ({type(exc).__name__})")
                    continue
                print(f"  {table}.{column}: {count}")
            print()

        print("=== нормы, где в готовой строке есть название акта ===")
        rows = db.execute(
            text(
                "select id, npa_id, reference_template from npa_articles "
                "where reference_template ilike '%Правил%' order by npa_id, id"
            )
        )
        count = 0
        for row in rows:
            count += 1
        print(f"  всего {count}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
