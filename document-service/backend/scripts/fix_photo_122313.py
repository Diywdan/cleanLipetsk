"""Фотографии осмотра 122313: восстановить пару «оригинал + размеченная».

В базе каждая фотография осмотра — это два файла: исходный снимок (original)
и размеченная копия (annotated). Снимок данных хранил только размеченную.
"""
from __future__ import annotations

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import ControlAction, ControlActionFile
from app.models.enums import PhotoKind

ACTION_ID = 7
ORIGINAL_FILE_ID = 200
ANNOTATED_FILE_ID = 201
CAPTION = "г. Липецк, ул. Теперика, д.3 22.09.2026 12 ч 20 мин."


def main() -> None:
    db = SessionLocal()
    try:
        action = db.get(ControlAction, ACTION_ID)
        if action is None:
            raise SystemExit("действие не найдено")

        for item in list(action.files):
            db.delete(item)
        db.flush()

        db.add(
            ControlActionFile(
                control_action_id=ACTION_ID,
                file_id=ORIGINAL_FILE_ID,
                photo_kind=PhotoKind.ORIGINAL,
                sequence_no=0,
            )
        )
        db.add(
            ControlActionFile(
                control_action_id=ACTION_ID,
                file_id=ANNOTATED_FILE_ID,
                photo_kind=PhotoKind.ANNOTATED,
                annotation_color="white",
                caption=CAPTION,
                sequence_no=1,
            )
        )
        db.commit()

        action = db.get(ControlAction, ACTION_ID)
        print(f"действие {action.id}: файлов {len(action.files)}")
        for item in action.files:
            print(f"  {item.file_id}: {item.file.original_name}, "
                  f"{item.photo_kind.value if item.photo_kind else None}, "
                  f"подпись: {item.caption!r}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
