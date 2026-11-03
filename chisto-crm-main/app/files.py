"""Фото отчётов исполнителей: файлы на диске под случайными именами, отдаются только вошедшим.

Принимается JPEG, PNG или WEBP — тип определяется по первым байтам файла, а не по заголовку.
"""

from __future__ import annotations

import base64
import binascii
import re
import uuid
from pathlib import Path

from fastapi import HTTPException

from app.config import get_settings

NAME = re.compile(r"^[0-9a-f]{32}\.(jpg|png|webp)$")
DATA_URL = re.compile(r"^data:image/(?:jpeg|png|webp);base64,(.+)$", re.S)
MEDIA_TYPES = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp"}


def _root() -> Path:
    root = Path(get_settings().files_dir)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _extension(data: bytes) -> str | None:
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def save_image(data: bytes) -> str:
    if len(data) > get_settings().max_upload_bytes:
        raise HTTPException(status_code=413, detail="Файл больше допустимого размера")
    extension = _extension(data)
    if extension is None:
        raise HTTPException(status_code=422, detail="Нужна фотография в JPEG, PNG или WEBP")
    name = f"{uuid.uuid4().hex}.{extension}"
    (_root() / name).write_bytes(data)
    return name


def resolve_photo(value: str) -> str:
    """Фото из отчёта → имя файла в хранилище.

    Фронт сейчас шлёт снимок строкой data URL прямо в отчёте — сохраняем его как файл.
    Ссылка из POST /files тоже принимается: берём имя из её конца и проверяем, что файл есть.
    """
    match = DATA_URL.match(value)
    if match:
        try:
            data = base64.b64decode(match.group(1), validate=True)
        except (binascii.Error, ValueError):
            raise HTTPException(status_code=422, detail="Фото повреждено") from None
        return save_image(data)
    name = value.rstrip("/").rsplit("/", 1)[-1]
    if NAME.match(name) and (_root() / name).is_file():
        return name
    raise HTTPException(status_code=422, detail="Фото: нужен data URL снимка или ссылка из POST /files")


def path_of(name: str) -> Path:
    path = _root() / name
    if not NAME.match(name) or not path.is_file():
        raise HTTPException(status_code=404, detail="Файл не найден")
    return path


def media_type(name: str) -> str:
    return MEDIA_TYPES[name.rsplit(".", 1)[1]]
