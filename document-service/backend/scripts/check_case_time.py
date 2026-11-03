"""Проверка: есть ли в контексте падежи должности и время осмотра."""
from __future__ import annotations

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import ControlAction, ControlCase, Inspector
from app.services import generation, snapshots


def main() -> None:
    db = SessionLocal()
    try:
        inspector = db.scalars(select(Inspector)).first()
        print(f"инспектор: {inspector.full_name!r}")
        print(f"  position_instrumental: {inspector.position_instrumental[:70]!r}")
        print(f"  full_name_instrumental: {inspector.full_name_instrumental!r}")

        case = db.scalar(select(ControlCase).where(ControlCase.case_number == "122313"))
        payload = snapshots.build_case_context(db, case.id)
        insp = payload.get("inspector") or {}
        print()
        print("в контексте inspector:")
        for key in sorted(insp.keys()):
            print(f"  {key} = {insp[key]!r}"[:110])

        print()
        print("в контексте case (даты осмотра):")
        case_ctx = payload.get("case") or {}
        for key in sorted(case_ctx.keys()):
            if "actual" in key:
                print(f"  {key} = {case_ctx[key]!r}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
