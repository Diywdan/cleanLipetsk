"""Хранилище файлов: содержимое на диске, метаданные и хэш — в базе."""

import hashlib
import mimetypes
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import StoredFile
from app.models.enums import FileKind


DATA_ROOT = Path(settings.data_root)
FILES_SUBDIR = "files"


def _target_path(digest: str, suffix: str) -> Path:
    return DATA_ROOT / FILES_SUBDIR / digest[:2] / digest[2:4] / f"{digest}{suffix}"


def relative_path(path: Path) -> str:
    return path.relative_to(DATA_ROOT).as_posix()


def absolute_path(storage_path: str) -> Path:
    return DATA_ROOT / storage_path


def sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def save_bytes(
    db: Session,
    data: bytes,
    original_name: str,
    kind: FileKind = FileKind.ATTACHMENT,
    mime_type: str | None = None,
    captured_at: datetime | None = None,
    uploaded_by_user_id: int | None = None,
    commit: bool = True,
) -> StoredFile:
    """Сохраняет содержимое и заводит запись о файле.

    Путь строится из sha256, поэтому один и тот же файл не дублируется,
    а подмена содержимого видна сразу: хэш перестанет совпадать.
    """

    digest = sha256_of(data)
    suffix = Path(original_name).suffix
    path = _target_path(digest, suffix)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(data)

    storage_path = relative_path(path)
    existing = (
        db.query(StoredFile)
        .filter(StoredFile.storage_path == storage_path)
        .one_or_none()
    )
    if existing is not None:
        return existing

    file = StoredFile(
        kind=kind,
        storage_path=storage_path,
        original_name=original_name,
        mime_type=mime_type or mimetypes.guess_type(original_name)[0],
        size_bytes=len(data),
        sha256=digest,
        captured_at=captured_at,
        uploaded_by_user_id=uploaded_by_user_id,
    )
    db.add(file)
    if commit:
        db.commit()
        db.refresh(file)
    else:
        db.flush()
    return file


def read_bytes(file: StoredFile) -> bytes:
    return absolute_path(file.storage_path).read_bytes()
