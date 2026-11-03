"""Восстановление подписанта задания по заявке 122313.

Поле assignment_approved_by_signatory_id тоже очистилось при неудачной
проверке формы: в журнале изменений его нет, но в снимке данных подписант
сохранён.
"""
from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import ControlBodySignatory, ControlCase

SNAPSHOT_PATH = Path("/app/case-122313-snapshot.json")


def main() -> None:
    payload = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    approver = payload.get("approver") or {}
    db = SessionLocal()
    try:
        case = db.scalar(select(ControlCase).where(ControlCase.case_number == "122313"))
        signatory = db.get(ControlBodySignatory, approver.get("id")) if approver else None
        if signatory is None and approver:
            signatory = db.scalars(
                select(ControlBodySignatory).where(
                    ControlBodySignatory.full_name == approver.get("full_name")
                )
            ).first()
        if signatory is None:
            raise SystemExit("подписант не найден")
        print(f"было: {case.assignment_approved_by_signatory_id}")
        case.assignment_approved_by_signatory_id = signatory.id
        db.commit()
        print(f"стало: {case.assignment_approved_by_signatory_id} "
              f"({signatory.full_name})")
    finally:
        db.close()


if __name__ == "__main__":
    main()
