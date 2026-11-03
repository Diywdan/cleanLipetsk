"""Сверка живой заявки 122313 со снимком: не потерялось ли что-то."""
from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import ControlCase
from app.services import snapshots

SNAPSHOT_PATH = Path("/app/case-122313-snapshot.json")


def main() -> None:
    expected = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    db = SessionLocal()
    try:
        case = db.scalar(select(ControlCase).where(ControlCase.case_number == "122313"))
        from app.models import ControlAction
        from app.models.enums import ControlActionType, InspectionKind

        inspection = db.scalars(
            select(ControlAction).where(
                ControlAction.control_case_id == case.id,
                ControlAction.action_type == ControlActionType.INSPECTION,
                ControlAction.inspection_kind == InspectionKind.PRIMARY,
            )
        ).first()
        live = snapshots.build_case_context(db, case.id, inspection)

        checks: list[tuple[str, object, object]] = []

        def add(title, before, after):
            checks.append((title, before, after))

        add("цель", expected["case"].get("purpose"), live["case"].get("purpose"))
        add("вид контроля", expected["case"].get("control_kind"),
            live["case"].get("control_kind"))
        add("форма", expected["case"].get("control_form"),
            live["case"].get("control_form"))
        add("начало", expected["case"].get("actual_start_at"),
            live["case"].get("actual_start_at"))
        add("окончание", expected["case"].get("actual_end_at"),
            live["case"].get("actual_end_at"))
        add("акт составлен", expected["case"].get("act_composed_at"),
            live["case"].get("act_composed_at"))
        add("номер задания", expected["case"].get("assignment_number"),
            live["case"].get("assignment_number"))
        add("номер мероприятия", expected["case"].get("erp_number"),
            live["case"].get("erp_number"))
        add("инспектор", expected["inspectors"][0]["full_name"],
            (live.get("inspectors") or [{}])[0].get("full_name"))
        add("роль инспектора", expected["inspectors"][0]["role"],
            (live.get("inspectors") or [{}])[0].get("role"))
        add("контролируемое лицо", expected["controlled_person"]["organization"]["short_name"],
            (live.get("controlled_person") or {}).get("organization", {}).get("short_name"))
        add("филиал", expected["controlled_person"]["unit"]["name"],
            (live.get("controlled_person") or {}).get("unit", {}).get("name"))
        add("оснований", len(expected["bases"]), len(live.get("bases") or []))
        add("осмотр начат", expected["inspection"]["started_at"],
            (live.get("inspection") or {}).get("started_at"))
        add("фото", len(expected["protocol"]["photos"]),
            len((live.get("protocol") or {}).get("photos") or []))
        add("предписание №", expected["prescription"]["number"],
            (live.get("prescription") or {}).get("number"))
        add("предписание срок", expected["prescription"]["due_on"],
            (live.get("prescription") or {}).get("due_on"))
        add("решение №", expected["decision"]["number"],
            (live.get("decision") or {}).get("number"))
        add("работ у нарушения", 3, len((live.get("violations") or [{}])[0].get("works") or []))
        add("подписант", expected["approver"]["full_name"],
            (live.get("approver") or {}).get("full_name"))

        problems = 0
        for title, before, after in checks:
            ok = before == after
            if not ok:
                problems += 1
            print(f"  {'ок  ' if ok else 'РАСХОЖДЕНИЕ'} {title}: "
                  f"{before!r} → {after!r}")
        print()
        print(f"расхождений: {problems}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
