"""Удаление тестовой картинки из хранилища (после проверки подстановки кода)."""
from __future__ import annotations

from sqlalchemy import select, text

from app.db.session import SessionLocal
from app.models import StoredFile
from app.services import storage


def main() -> None:
    db = SessionLocal()
    try:
        files = list(
            db.scalars(
                select(StoredFile)
                .where(StoredFile.original_name.in_(("qr-test.png",)))
                .order_by(StoredFile.id)
            )
        )
        if not files:
            # На случай, если имя не сохранилось: ищем по контрольной сумме.
            files = list(
                db.scalars(
                    select(StoredFile).where(
                        StoredFile.sha256
                        == "9d6dcade2aa02710935bf129c490e5cf76dc92c86c87d0a0373dd9b65f3fde0b"
                    )
                )
            )
        print(f"найдено записей: {len(files)}")
        for file in files:
            used = {
                "documents.generated": db.scalar(
                    text("select count(*) from documents where generated_file_id = :i"),
                    {"i": file.id},
                ),
                "documents.signed": db.scalar(
                    text("select count(*) from documents where signed_file_id = :i"),
                    {"i": file.id},
                ),
                "templates": db.scalar(
                    text("select count(*) from document_templates where file_id = :i"),
                    {"i": file.id},
                ),
                "control_cases.qr": db.scalar(
                    text("select count(*) from control_cases where qr_file_id = :i"),
                    {"i": file.id},
                ),
            }
            print(f"  файл {file.id} {file.original_name!r} используется: {used}")
            if any(used.values()):
                print("    пропускаю: файл используется")
                continue
            path = storage.absolute_path(file.storage_path)
            db.delete(file)
            db.commit()
            if path.exists():
                path.unlink()
            print(f"    удалено: запись и файл {file.storage_path}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
