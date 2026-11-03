"""Полное значение цели заявки 122313 из снимка данных.

В журнале изменений длинные значения обрезаются многоточием, поэтому цель
восстанавливается из снимка — там она сохранена целиком.
"""
from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import ControlCase

SNAPSHOT_PATH = Path("/app/case-122313-snapshot.json")


def main() -> None:
    payload = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    purpose = payload["case"]["purpose"]
    db = SessionLocal()
    try:
        case = db.scalar(select(ControlCase).where(ControlCase.case_number == "122313"))
        print(f"было: {case.purpose!r}")
        case.purpose = purpose
        db.commit()
        print(f"стало: {case.purpose!r}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
