"""Какое событие правонарушения и приложение попадают в снимок."""
from __future__ import annotations

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import ControlCase
from app.services import snapshots


def main() -> None:
    db = SessionLocal()
    try:
        case = db.scalar(select(ControlCase).where(ControlCase.case_number == "122313"))
        from app.models import ControlAction
        from app.models.enums import ControlActionType, InspectionKind
        from app.services import inspections

        inspection = inspections.primary(db, case.id)
        payload = snapshots.build_case_context(db, case.id, inspection)
        administrative = payload.get("administrative") or {}
        print("circumstances:")
        print(" ", administrative.get("circumstances"))
        print("appendix_note:", administrative.get("appendix_note"))
        print("appendix_effective:", administrative.get("appendix_effective"))
        print("prior basis:", administrative.get("prior_prescription_basis"))
    finally:
        db.close()


if __name__ == "__main__":
    main()
