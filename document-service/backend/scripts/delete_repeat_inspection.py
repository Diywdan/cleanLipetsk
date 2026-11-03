"""Удаление повторного осмотра из заявки.

Перед удалением запись сохраняется в файл: если осмотр убрали по ошибке,
его можно завести заново по этой описи. Ссылок на осмотр ни у чего нет —
проверяется до удаления.

По умолчанию — только показать, что уйдёт. Удалить: --apply

Запуск: PYTHONPATH=/app python scripts/delete_repeat_inspection.py [номер_заявки] [--apply]
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import (
    ControlAction,
    ControlActionFile,
    ControlActionInspector,
    ControlCase,
    Document,
    Violation,
)

EXPORT = Path("/data/export")


def describe(action: ControlAction, db) -> dict:
    violation_list = list(
        db.scalars(select(Violation).where(Violation.control_action_id == action.id))
    )
    files = list(
        db.scalars(
            select(ControlActionFile).where(
                ControlActionFile.control_action_id == action.id
            )
        )
    )
    inspectors = list(
        db.scalars(
            select(ControlActionInspector).where(
                ControlActionInspector.control_action_id == action.id
            )
        )
    )
    return {
        "id": action.id,
        "sequence_no": action.sequence_no,
        "inspection_kind": action.inspection_kind.value,
        "action_type": action.action_type.value,
        "started_at": action.started_at.isoformat() if action.started_at else None,
        "ended_at": action.ended_at.isoformat() if action.ended_at else None,
        "place_address_id": action.place_address_id,
        "result_text": action.result_text,
        "is_violation_found": action.is_violation_found,
        "inspection_result": (
            action.inspection_result.value if action.inspection_result else None
        ),
        "result_document_id": action.result_document_id,
        "files": [item.file_id for item in files],
        "inspectors": [item.inspector_id for item in inspectors],
        "violations": [item.id for item in violation_list],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("number", nargs="?", default="122313")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        case = db.scalar(
            select(ControlCase).where(ControlCase.case_number == args.number)
        )
        if case is None:
            print(f"заявка {args.number!r} не найдена")
            return 1

        repeats = [
            action
            for action in case.actions
            if action.inspection_kind.value == "repeat"
        ]
        print(f"заявка {args.number}: осмотров {len(case.actions)}, "
              f"повторных {len(repeats)}")
        if not repeats:
            print("повторных осмотров нет — удалять нечего")
            return 0

        inventory = {"case_number": args.number, "case_id": case.id,
                     "created_at": datetime.now(timezone.utc).isoformat(),
                     "removed": []}
        blocked = False
        for action in repeats:
            info = describe(action, db)
            inventory["removed"].append(info)
            print(f"  уйдёт осмотр id={action.id} №{action.sequence_no} "
                  f"{info['inspection_kind']}")
            print(f"      начало {info['started_at']}, окончание {info['ended_at']}")
            print(f"      место (адрес id): {info['place_address_id']}")
            print(f"      результат: {info['result_text']!r}, "
                  f"нарушение найдено: {info['is_violation_found']}")
            print(f"      фотографий: {len(info['files'])}, "
                  f"инспекторов: {len(info['inspectors'])}, "
                  f"нарушений: {len(info['violations'])}")
            if info["files"] or info["violations"] or info["result_document_id"]:
                blocked = True
                print("      ВНИМАНИЕ: на осмотр опираются данные "
                      "(фотографии, нарушение или документ)")
            # Документы, собранные по этому осмотру, ищем по снимкам пакетов.
            packages = [
                document.id
                for document in db.scalars(
                    select(Document).where(Document.package_id.is_not(None))
                )
                if document.snapshot
                and (document.snapshot.payload.get("inspection") or {}).get("id")
                == action.id
            ]
            if packages:
                blocked = True
                print(f"      по этому осмотру собраны документы: {packages}")
            inventory["removed"][-1]["documents_built"] = packages

        if blocked:
            print("\nОСТАНОВ: на повторный осмотр опираются данные. "
                  "Удаление изменит уже собранные документы.")
            return 1

        if not args.apply:
            print("\nЭто проверка. Для удаления добавьте --apply")
            return 0

        EXPORT.mkdir(parents=True, exist_ok=True)
        path = EXPORT / f"repeat-inspection-removed-{args.number}.json"
        path.write_text(
            json.dumps(inventory, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\nопись сохранена: {path}")

        for action in repeats:
            db.delete(action)
        db.commit()

        left = list(
            db.scalars(
                select(ControlAction)
                .where(ControlAction.control_case_id == case.id)
                .order_by(ControlAction.sequence_no)
            )
        )
        print(f"удалено осмотров: {len(repeats)}")
        print(f"осталось осмотров: {len(left)}")
        for action in left:
            print(f"  id={action.id} №{action.sequence_no} "
                  f"{action.inspection_kind.value} "
                  f"начало {action.started_at}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
