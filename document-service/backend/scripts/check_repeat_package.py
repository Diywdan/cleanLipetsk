"""Проверка: повторный пакет собирается без номера из реестра.

Пакет создаётся в транзакции и откатывается — данные заявки не меняются.
"""
from __future__ import annotations

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import ControlCase, PackageKind
from app.services import generation


def main() -> None:
    db = SessionLocal()
    try:
        case = db.scalar(select(ControlCase).where(ControlCase.case_number == "122313"))
        print(f"заявка {case.case_number}, номер из реестра: {case.erp_number!r}")

        for code in ("repeated_prescription", "executed_prescription"):
            kind = db.scalar(select(PackageKind).where(PackageKind.code == code))
            if kind is None:
                print(f"  {code}: вида пакета нет")
                continue
            try:
                result = generation.generate_package(db, case.id, package_kind_code=code)
            except Exception as error:  # noqa: BLE001
                print(f"  {code}: НЕ СОБРАЛСЯ — {type(error).__name__}: {error}")
                db.rollback()
                continue
            documents = [
                f"{document.code} (номер {document.number or 'пусто'})"
                for document in result.created
            ]
            print(f"  {code}: собран, документов {len(result.created)}: "
                  + ", ".join(documents))
            db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    main()
