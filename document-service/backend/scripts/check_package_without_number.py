"""Проверка: пакет собирается и без номера из реестра контрольных мероприятий.

Номер временно снимается и возвращается в finally — данные заявки остаются как
были.
"""
from __future__ import annotations

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import ControlCase, PackageKind
from app.services import generation, validation


def main() -> None:
    db = SessionLocal()
    try:
        case = db.scalar(select(ControlCase).where(ControlCase.case_number == "122313"))
        original = case.erp_number
        print(f"номер из реестра сейчас: {original!r}")
        try:
            case.erp_number = None
            db.commit()

            for code in ("repeated_prescription", "primary_prescription"):
                readiness = validation.check_readiness(db, case.id, code).as_dict()
                print()
                print(f"пакет {code}: соберётся = {readiness['is_ready']}")
                for issue in readiness["issues"]:
                    print(f"  мешает:    {issue['message']}")
                for warning in readiness["warnings"]:
                    print(f"  замечание: {warning['message']}")

            result = generation.generate_package(
                db, case.id, package_kind_code="repeated_prescription"
            )
            numbers = [
                f"{document.code}: {document.number or 'пусто'}"
                for document in result.created
            ]
            print()
            print(f"повторный пакет собран, документов {len(result.created)}")
            for line in numbers:
                print("  " + line)
            db.rollback()
        finally:
            db.rollback()
            case = db.scalar(
                select(ControlCase).where(ControlCase.case_number == "122313")
            )
            case.erp_number = original
            db.commit()
            print()
            print(f"номер возвращён: {case.erp_number!r}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
