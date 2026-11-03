"""Что хранится в справочнике норм и как он выводится в интерфейсе."""
from __future__ import annotations

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import Npa, NpaArticle


def main() -> None:
    db = SessionLocal()
    try:
        for npa in db.scalars(select(Npa).order_by(Npa.id)):
            print(f"НПА {npa.id}: {npa.title!r}")
            print(f"  родительный: {npa.title_genitive!r}")
            print(f"  номер: {npa.number!r}, принят: {npa.adopted_on}")
            articles = list(
                db.scalars(
                    select(NpaArticle)
                    .where(NpaArticle.npa_id == npa.id)
                    .order_by(NpaArticle.article_number, NpaArticle.part_number)
                )
            )
            print(f"  норм: {len(articles)}")
            for article in articles:
                print(f"    id={article.id:<4} "
                      f"ст.{article.article_number} "
                      f"ч.{article.part_number} "
                      f"п.{article.point_number} "
                      f"пп.{article.subpoint_number} | "
                      f"reference_template={article.reference_template!r}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
