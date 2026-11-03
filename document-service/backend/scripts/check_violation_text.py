"""Проверка: собираются ли описание нарушения и требование из справочников."""
from __future__ import annotations

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import ControlCase
from app.services import snapshots


def main() -> None:
    db = SessionLocal()
    try:
        case = db.scalar(
            select(ControlCase).where(ControlCase.case_number == "122313")
        )
        payload = snapshots.build_case_context(db, case.id)
        violation = payload["violations"][0]
        print("=== описание нарушения ===")
        print(violation["description"])
        print()
        print("=== работы ===")
        for item in violation.get("works") or []:
            print(f"  {item['name']}: {item['quantity']} {item['unit']}")
        print()
        print("=== требование ===")
        prescription = payload.get("prescription") or {}
        for requirement in prescription.get("requirements") or []:
            print(requirement.get("requirement_text"))
            print(f"  (действие: {requirement.get('action_code')})")
        print()
        print("=== протокол осмотра ===")
        protocol = payload.get("protocol") or {}
        print("  описание:", (protocol.get("violation_description") or "")[:120])
        print("  нормы:", protocol.get("violation_provisions_genitive"))
    finally:
        db.close()


if __name__ == "__main__":
    main()
