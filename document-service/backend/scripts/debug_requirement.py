"""Отладка: почему требование в карточке не собралось."""
from __future__ import annotations

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import ControlCase, Prescription, Violation
from app.web import router


def main() -> None:
    db = SessionLocal()
    try:
        case = db.scalar(select(ControlCase).where(ControlCase.case_number == "122313"))
        violation = db.scalar(
            select(Violation).where(Violation.control_case_id == case.id)
        )
        prescription = db.scalar(
            select(Prescription).where(Prescription.control_case_id == case.id)
        )
        print(f"нарушение: {violation is not None}, работ: {len(violation.works)}")
        print(f"предписание: {prescription is not None}, "
              f"строк: {len(prescription.items) if prescription else 0}")
        if violation is not None:
            print("норм:", len(violation.provisions))
            print("тип:", violation.violation_type.name if violation.violation_type else None)
            print("объект:", violation.control_case.control_object)
            for provision in violation.provisions:
                article = provision.npa_article
                print("  норма:", article.reference_template,
                      "| акт:", article.npa.title_genitive if article.npa else None)
        result = router._requirement_text(violation, prescription)
        print()
        print("РЕЗУЛЬТАТ:", result)
    finally:
        db.close()


if __name__ == "__main__":
    main()
