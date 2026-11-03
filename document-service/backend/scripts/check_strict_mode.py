"""Проверка строгого режима: пустое поле должно валить сборку, а не печататься.

Инструмент проверки готовности должен заранее сказать, каких данных не
хватает. Здесь мы убеждаемся, что при отсутствии данных шаблон падает —
значит, ослабление режима действительно отменено.
"""
from __future__ import annotations

from copy import deepcopy

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import DataSnapshot, DocumentType
from app.services import generation, storage


def main() -> int:
    db = SessionLocal()
    try:
        sample = db.scalars(
            select(DataSnapshot)
            .where(DataSnapshot.entity_kind == "package")
            .order_by(DataSnapshot.id.desc())
        ).first()
        payload = deepcopy(sample.payload)

        # Убираем данные контрольного органа: раньше на этом месте печаталась
        # пустая строка, теперь сборка обязана упасть.
        payload.pop("control_body", None)
        payload.pop("inspector", None)

        failures = 0
        for code in ["direction", "administrative_protocol", "appearance_notice",
                     "act", "act_direction", "prescription", "decision", "assignment"]:
            dt = db.scalar(select(DocumentType).where(DocumentType.code == code))
            template = generation._active_template(db, dt.id)
            try:
                generation.build_document_bytes(
                    payload, code, storage.read_bytes(template.file)
                )
            except Exception as exc:  # noqa: BLE001
                failures += 1
                print(f"{code:24} упал как положено: {type(exc).__name__}: {str(exc)[:80]}")
            else:
                print(f"{code:24} ВНИМАНИЕ: собрался без данных control_body/inspector")
        print()
        print(f"упало на пустых данных: {failures} из 8")
        return 0 if failures else 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
