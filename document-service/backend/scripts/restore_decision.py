"""Восстановление решения по заявке 122313 из снимка данных."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import (
    ControlBodySignatory,
    ControlCase,
    Decision,
    DecisionItem,
)
from app.models.enums import DecisionItemKind

SNAPSHOT_PATH = Path("/app/case-122313-snapshot.json")


def main() -> None:
    payload = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    decision_data = payload.get("decision") or {}
    approver = payload.get("approver") or {}
    db = SessionLocal()
    try:
        case = db.scalar(select(ControlCase).where(ControlCase.case_number == "122313"))
        decision = db.scalars(
            select(Decision).where(Decision.control_case_id == case.id)
        ).first()
        signatory = db.get(ControlBodySignatory, approver.get("id")) if approver else None
        if decision is None:
            decision = Decision(
                id=decision_data.get("id"),
                control_case_id=case.id,
                number=decision_data.get("number"),
                decision_date=date.fromisoformat(decision_data["decision_date"])
                if decision_data.get("decision_date")
                else None,
                decision_kind=decision_data.get("decision_kind"),
                content=decision_data.get("content"),
                approved_by_signatory_id=signatory.id if signatory else None,
            )
            db.add(decision)
            db.flush()
        else:
            decision.number = decision_data.get("number")
            decision.decision_kind = decision_data.get("decision_kind")
            decision.content = decision_data.get("content")

        for point in decision_data.get("points") or []:
            exists = db.scalar(
                select(DecisionItem).where(
                    DecisionItem.decision_id == decision.id,
                    DecisionItem.sequence_no == point.get("sequence_no"),
                )
            )
            if exists is None:
                db.add(
                    DecisionItem(
                        decision_id=decision.id,
                        sequence_no=point.get("sequence_no") or 1,
                        kind=DecisionItemKind(point["kind"]),
                        description=point.get("description"),
                    )
                )
        db.commit()

        print(f"решение {decision.id}: № {decision.number} от {decision.decision_date}")
        print(f"  вид: {decision.decision_kind}")
        print(f"  содержание: {decision.content}")
        for item in decision.items:
            print(f"  пункт {item.sequence_no}: {item.kind.value} — {item.description}")
        print(f"  подписант: "
              f"{decision.approved_by_signatory.full_name if decision.approved_by_signatory else None}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
