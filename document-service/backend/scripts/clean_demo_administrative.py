"""Очистка демонстрационных данных административного производства.

Скрипт проверки (check_admin_documents.py) заполнял данные производства по
заявке 122313 примерами из образца протокола: номер 769-П, место составления
на Механизаторов, явка 14.10.2026, место правонарушения в Москве на 3-й
Песчаной. В заявке эти значения остались как настоящие.

Скрипт убирает их, но не трогает то, что действительно относится к делу:
адрес объекта, предписание, решение.

Запуск внутри контейнера:
    PYTHONPATH=/app python scripts/clean_demo_administrative.py
"""
from __future__ import annotations

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import AdministrativeCase, ControlCase

CASE_NUMBER = "122313"

# Поля, заполненные демонстрационными значениями.
DEMO_FIELDS = (
    "protocol_number",
    "protocol_date",
    "protocol_place",
    "appearance_date",
    "appearance_time",
    "appearance_place",
    "appearance_office",
    "notice_number",
    "notice_date",
    "offense_date",
    "offense_time",
    "offense_place",
    "offense_description",
    "representative_info",
)


def main() -> None:
    db = SessionLocal()
    try:
        case = db.scalar(
            select(ControlCase).where(ControlCase.case_number == CASE_NUMBER)
        )
        if case is None:
            raise SystemExit("заявка не найдена")
        row = db.scalars(
            select(AdministrativeCase).where(
                AdministrativeCase.control_case_id == case.id
            )
        ).first()
        if row is None:
            print("данных производства нет")
            return

        print("очищаю демонстрационные значения:")
        for field in DEMO_FIELDS:
            value = getattr(row, field)
            if value in (None, ""):
                continue
            print(f"  {field}: {value!r} -> пусто")
            setattr(row, field, None)
        db.commit()

        print()
        print("после очистки:")
        for field in DEMO_FIELDS:
            print(f"  {field} = {getattr(row, field)!r}")
        print()
        print("осталось как было (это относится к делу):")
        for field in ("offense_article", "prior_prescription_number"):
            print(f"  {field} = {getattr(row, field)!r}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
