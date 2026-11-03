"""Восстановление осмотра и фото по заявке 122313 из снимка данных.

Проверка формы отправила частичную форму, и обработчик удалил контрольное
действие вместе с привязанными файлами. Данные берутся из снимка пакета:
там сохранены сроки осмотра, место и номера фотографий.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select, text

from app.db.session import SessionLocal
from app.models import (
    ControlAction,
    ControlActionFile,
    ControlActionInspector,
    ControlCase,
    ControlObject,
    DataSnapshot,
    DocumentPackage,
    Prescription,
    Violation,
)
from app.models.enums import ControlActionType, PhotoKind

CASE_NUMBER = "122313"


def main() -> None:
    db = SessionLocal()
    try:
        case = db.scalar(
            select(ControlCase).where(ControlCase.case_number == CASE_NUMBER)
        )
        package = db.scalars(
            select(DocumentPackage)
            .where(DocumentPackage.control_case_id == case.id)
            .order_by(DocumentPackage.id.desc())
        ).first()
        snapshot = db.scalars(
            select(DataSnapshot)
            .where(DataSnapshot.entity_kind == "package",
                   DataSnapshot.entity_id == package.id)
            .order_by(DataSnapshot.id.desc())
        ).first()
        payload = snapshot.payload

        actions = payload.get("actions") or []
        first = actions[0]
        print(f"осмотр по снимку: {first['started_at']} — {first['ended_at']}, "
              f"место: {first.get('place')}")

        action = db.scalars(
            select(ControlAction).where(ControlAction.control_case_id == case.id)
        ).first()
        control_object = db.get(ControlObject, case.control_object_id)
        address_id = control_object.address_id if control_object else None
        started = datetime.fromisoformat(first["started_at"])
        ended = datetime.fromisoformat(first["ended_at"])
        if action is None:
            # Идентификатор берём из снимка: нарушение ссылается на действие.
            action = ControlAction(
                id=payload["inspection"]["id"],
                control_case_id=case.id,
                sequence_no=first.get("sequence_no") or 1,
                action_type=ControlActionType(first["type"]),
                started_at=started,
                ended_at=ended,
                place_address_id=address_id,
                result_text=first.get("result_text"),
                is_violation_found=bool(first.get("is_violation_found")),
            )
            db.add(action)
            db.flush()
        else:
            action.action_type = ControlActionType(first["type"])
            action.started_at = started
            action.ended_at = ended
            action.place_address_id = address_id
            action.result_text = first.get("result_text")
            action.is_violation_found = bool(first.get("is_violation_found"))
            db.flush()

        violation = db.scalar(
            select(Violation).where(Violation.control_case_id == case.id)
        )
        if violation is not None:
            violation.control_action_id = action.id

        # Инспектор осмотра: тот же, что указан по заявке.
        inspector_id = db.scalar(
            text(
                "select inspector_id from control_case_inspectors "
                "where control_case_id = :case_id order by id limit 1"
            ),
            {"case_id": case.id},
        )
        if inspector_id:
            exists = db.scalar(
                select(ControlActionInspector).where(
                    ControlActionInspector.control_action_id == action.id,
                    ControlActionInspector.inspector_id == inspector_id,
                )
            )
            if exists is None:
                db.add(
                    ControlActionInspector(
                        control_action_id=action.id, inspector_id=inspector_id
                    )
                )

        # Фотографии: файлы в хранилище целы, восстанавливаем только связи.
        photos = (payload.get("protocol") or {}).get("photos") or []
        print(f"фотографий в снимке: {len(photos)}")
        for index, photo in enumerate(photos, start=1):
            file_id = photo.get("file_id")
            if not file_id:
                continue
            exists = db.scalar(
                select(ControlActionFile).where(
                    ControlActionFile.control_action_id == action.id,
                    ControlActionFile.file_id == file_id,
                )
            )
            if exists is not None:
                continue
            db.add(
                ControlActionFile(
                    control_action_id=action.id,
                    file_id=file_id,
                    caption=photo.get("caption") or None,
                    photo_kind=PhotoKind.MARKED
                    if "marked" in str(photo.get("file_id"))
                    else None,
                    sequence_no=index,
                )
            )

        # Предписание: реквизиты тоже есть в снимке.
        prescription_payload = payload.get("prescription") or {}
        prescription = db.scalar(
            select(Prescription).where(Prescription.control_case_id == case.id)
        )
        if prescription is not None:
            prescription.number = prescription_payload.get("number")
            issued = prescription_payload.get("issued_on")
            due = prescription_payload.get("due_on")
            prescription.issued_on = datetime.fromisoformat(issued).date() if issued else None
            prescription.due_on = datetime.fromisoformat(due).date() if due else None
            db.flush()
            status_code = prescription_payload.get("status")
            if status_code:
                status_id = db.scalar(
                    text("select id from prescription_statuses where code = :code"),
                    {"code": status_code},
                )
                prescription.status_id = status_id

        db.commit()

        print()
        print("после восстановления:")
        action = db.scalars(
            select(ControlAction).where(ControlAction.control_case_id == case.id)
        ).first()
        print(f"  действие {action.id}: {action.action_type.value}, "
              f"{action.started_at} — {action.ended_at}, "
              f"место: {address_id}, нарушение: {action.is_violation_found}")
        print(f"  файлов: {len(action.files)}")
        for item in action.files:
            print(f"    {item.file_id}: {item.file.original_name} ({item.file.kind})")
        prescription = db.scalar(
            select(Prescription).where(Prescription.control_case_id == case.id)
        )
        print(f"  предписание {prescription.number} от {prescription.issued_on}, "
              f"срок {prescription.due_on}, статус {prescription.status.code if prescription.status else None}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
