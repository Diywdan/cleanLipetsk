"""Что доступно для текста протокола: падежи должности и даты."""
from __future__ import annotations

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import Inspector
from app.services import ru


def main() -> None:
    db = SessionLocal()
    try:
        for inspector in db.scalars(select(Inspector).order_by(Inspector.id).limit(5)):
            print(f"инспектор {inspector.id}: {inspector.full_name!r}")
            print(f"  должность: {inspector.position!r}")
            print(f"  должность (тв.): {inspector.position_instrumental!r}")
            print(f"  ФИО (тв.): {inspector.full_name_instrumental!r}")
            print(f"  ФИО (род., до): {inspector.short_name_genitive or '—'!r}")
        print()
        print("=== функции падежей в ru ===")
        for name in dir(ru):
            if name.startswith("_"):
                continue
            value = getattr(ru, name)
            if callable(value):
                doc = (value.__doc__ or "").strip().splitlines()
                print(f"  {name}: {doc[0] if doc else ''}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
