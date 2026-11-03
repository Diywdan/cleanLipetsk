"""Фото и видео из событий DG — по постоянной ссылке CRM.

Файл DG хранит в своём хранилище (MinIO) постоянно, а в событие кладёт подписанную ссылку на него,
которая живёт час (CANONICAL_MEDIA_URL_EXPIRES_SECONDS у DG). Поэтому:
1) сразу после приёма дела CRM забирает снимки к себе (files_dir) — дальше они не зависят от DG;
2) если копии нет (старое дело, DG был недоступен) — CRM берёт у DG свежую ссылку по ключу объекта
   (GET {datagateway_url}/api/v1/storage/object?key=…), забирает файл и тоже оставляет у себя.
Видео не копируется (тяжёлое) — отдаётся потоком по живой или свежей ссылке.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import urlopen

from fastapi import HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session

from app import files
from app.config import get_settings
from app.db import session_scope, utc_now
from app.models import Case, DgIntegration

log = logging.getLogger("crm.media")
HEADERS = {"Content-Disposition": "inline", "X-Content-Type-Options": "nosniff"}


def _dg_base(db: Session) -> str | None:
    override = get_settings().dg_media_url
    if override:
        return override
    row = db.get(DgIntegration, 1)
    return row.datagateway_url if row else None


def _alive(item: dict[str, Any]) -> str | None:
    """Ссылка из события, если до конца её жизни больше минуты."""
    meta = item.get("metadata") or {}
    url, expires = meta.get("download_url"), meta.get("download_url_expires_at")
    if not url:
        return None
    try:
        if expires and datetime.fromisoformat(str(expires).replace("Z", "+00:00")) < utc_now() + timedelta(minutes=1):
            return None
    except ValueError:
        pass
    return url


def _fresh(db: Session, item: dict[str, Any]) -> str | None:
    """Свежая подписанная ссылка у DG по ключу объекта в хранилище."""
    key, base = (item.get("storage") or {}).get("key"), _dg_base(db)
    if not key or not base or urlsplit(base).scheme not in {"http", "https"}:
        return None
    with urlopen(f"{base.rstrip('/')}/api/v1/storage/object?key={quote(str(key), safe='')}", timeout=10) as r:  # noqa: S310
        url = json.loads(r.read()).get("url")
    return url if url and urlsplit(url).scheme in {"http", "https"} else None


def open_object(db: Session, item: dict[str, Any]):
    """Открыть файл в хранилище DG: сначала ссылка из события, если жива, потом свежая."""
    errors = []
    for get_url in (lambda: _alive(item), lambda: _fresh(db, item)):
        try:
            url = get_url()
            if url:
                return urlopen(url, timeout=20)  # noqa: S310 — адрес выдал DG
        except HTTPError as exc:
            errors.append(f"HTTP {exc.code}")
        except (URLError, TimeoutError, OSError, ValueError) as exc:
            errors.append(str(exc))
    raise HTTPException(status_code=502, detail="Хранилище DG не отдало файл" + (f": {errors[-1]}" if errors else ""))


def cache_image(db: Session, case: Case, index: int) -> str | None:
    """Копия снимка в хранилище CRM; имя файла запоминается в деле (media[i].crm_file)."""
    media = list(case.media or [])
    item = dict(media[index])
    name = item.get("crm_file")
    if name:
        try:
            files.path_of(name)
            return name
        except HTTPException:
            pass  # файл пропал с диска — заберём заново
    if item.get("type") != "image":
        return None
    limit = get_settings().max_upload_bytes
    with open_object(db, item) as response:
        data = response.read(limit + 1)
    name = files.save_image(data)  # проверяет размер и что это JPEG/PNG/WEBP
    item["crm_file"] = name
    media[index] = item
    case.media = media  # новый список — иначе изменение JSON не попадёт в базу
    return name


def cache_case_media(case_id: int) -> int:
    """После приёма дела: забрать все снимки, пока ссылка из события жива. Сбой не мешает делу."""
    saved = 0
    with session_scope() as db:
        case = db.get(Case, case_id)
        for index, item in enumerate((case.media if case else None) or []):
            if item.get("type") != "image" or item.get("crm_file"):
                continue
            try:
                saved += bool(cache_image(db, case, index))
            except Exception as exc:  # noqa: BLE001 — копию попробуем снова при первом просмотре
                log.warning("media: case %s item %s not cached: %s", case_id, index, exc)
    return saved


def response(db: Session, case: Case | None, media: list[dict[str, Any]], index: int):
    """Ответ с файлом: снимок — из копии CRM (сделает, если её нет), видео — потоком из DG."""
    if index < 0 or index >= len(media):
        raise HTTPException(status_code=404, detail="Файл не найден")
    item = media[index]
    if item.get("type") == "image":
        name = item.get("crm_file")
        if case is not None:
            name = cache_image(db, case, index)
        if name:
            return FileResponse(files.path_of(name), media_type=files.media_type(name),
                                headers={**HEADERS, "Cache-Control": "private, max-age=86400"})
    upstream = open_object(db, item)
    content_type = upstream.headers.get_content_type()
    if not content_type.startswith(("image/", "video/")):
        upstream.close()
        raise HTTPException(status_code=415, detail="Неподдерживаемый тип файла")

    def stream() -> Iterator[bytes]:
        try:
            while chunk := upstream.read(64 * 1024):
                yield chunk
        finally:
            upstream.close()

    headers = {**HEADERS, "Cache-Control": "private, max-age=240"}
    if upstream.headers.get("Content-Length"):
        headers["Content-Length"] = upstream.headers["Content-Length"]
    return StreamingResponse(stream(), media_type=content_type, headers=headers)
