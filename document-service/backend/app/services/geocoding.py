"""Координаты адреса для карты.

Адрес заводится строкой прямо в заявке, и координат у него при этом нет — без
них обращение не встаёт на карту в интерфейсе диспетчера. Заполняем их сразу
при создании и правке заявки, в фоне: внешний запрос не должен задерживать
сохранение, а если геокодер не ответит — заявка всё равно сохранится.

Порядок источников: сначала геокодер Яндекса (знает российские адреса до
дома), затем открытый Nominatim (OpenStreetMap) как запасной вариант. Если
адрес не нашёлся нигде, координаты остаются пустыми: метка просто не
появится, а адрес можно поправить в справочнике вручную.

Ключ геокодера берётся из переменной окружения YANDEX_GEOCODER_KEY или из
файла /app/.geocoder-key (в репозиторий ключ не попадает).
"""

import json
import logging
import os
import threading
import urllib.parse
import urllib.request
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import Address


log = logging.getLogger(__name__)

KEY_FILE = Path("/app/.geocoder-key")
# Ограничения ключа в кабинете Яндекса проверены: запрос идёт с нашим
# User-Agent и без Referer — так сервис отвечает, с Referer отказывает (403).
USER_AGENT = "document-service/0.2 (municipal control, Lipetsk; +https://chili.moneta-rus.pro)"
YANDEX = "https://geocode-maps.yandex.ru/v1/"
NOMINATIM = "https://nominatim.openstreetmap.org/search"

# Один поток на адрес: повторные сохранения не плодят запросы.
_lock = threading.Lock()
_pending: set[int] = set()


def _yandex_key() -> str:
    key = os.environ.get("YANDEX_GEOCODER_KEY", "").strip()
    if not key and KEY_FILE.exists():
        key = KEY_FILE.read_text(encoding="utf-8").strip()
    # В файл ключ могут записать и строкой «YANDEX_GEOCODER_KEY=...» — берём
    # значение, а не всё содержимое строки.
    if "=" in key:
        key = key.split("=", 1)[1].strip()
    return key


def _lookup_yandex(address: str) -> tuple[Decimal, Decimal, str] | None:
    """Координаты и точность ответа: exact и number — это дом."""
    key = _yandex_key()
    if not key:
        return None
    query = urllib.parse.urlencode(
        {"apikey": key, "geocode": address, "format": "json", "results": 1, "lang": "ru_RU"}
    )
    request = urllib.request.Request(f"{YANDEX}?{query}", headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=20) as response:
        data = json.loads(response.read().decode("utf-8"))
    found = data["response"]["GeoObjectCollection"]["featureMember"]
    if not found:
        return None
    obj = found[0]["GeoObject"]
    precision = obj["metaDataProperty"]["GeocoderMetaData"].get("precision", "")
    longitude, latitude = obj["Point"]["pos"].split()
    return Decimal(latitude), Decimal(longitude), precision


def _lookup_nominatim(address: str) -> tuple[Decimal, Decimal] | None:
    query = urllib.parse.urlencode(
        {"q": address, "format": "json", "limit": 1, "countrycodes": "ru"}
    )
    request = urllib.request.Request(
        f"{NOMINATIM}?{query}", headers={"User-Agent": USER_AGENT}
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        found = json.loads(response.read().decode("utf-8"))
    if not found:
        return None
    return Decimal(found[0]["lat"]), Decimal(found[0]["lon"])


def fill(address_id: int) -> None:
    """Проставить координаты адресу, если их ещё нет."""

    db = SessionLocal()
    try:
        address = db.get(Address, address_id)
        if address is None:
            return
        text = (address.full_address or "").strip()
        if not text:
            return

        # Ответ геокодера — координаты и точность. Точность нужна, чтобы
        # уточнять уже стоящие координаты: адрес, определённый до дома, важнее
        # того, что лежит в базе (например, точки в центре микрорайона, которую
        # когда-то дал OpenStreetMap).
        point = None
        precision = ""
        for name, lookup in (("Яндекс", _lookup_yandex), ("OpenStreetMap", _lookup_nominatim)):
            try:
                found = lookup(text)
            except Exception as error:  # noqa: BLE001 — сеть бывает разной
                log.warning("Геокодер %s не ответил для «%s»: %s", name, text, error)
                continue
            if found is None:
                continue
            if len(found) == 3:
                point, precision = (found[0], found[1]), str(found[2])
            else:
                point, precision = found, "street"
            break

        if point is None:
            log.info("Координаты для «%s» не найдены", text)
            return

        filled = address.latitude is None or address.longitude is None
        exact = precision in {"exact", "number"}
        if not filled and not exact:
            # Координаты уже есть, а новый ответ не точнее — не трогаем.
            return

        moved = (
            not filled
            and (address.latitude, address.longitude) != point
        )
        address.latitude, address.longitude = point
        db.commit()
        if filled:
            log.info("Координаты «%s»: %s, %s", text, point[0], point[1])
        elif moved:
            log.info("Координаты «%s» уточнены по дому: %s, %s", text, point[0], point[1])
    finally:
        db.close()
        with _lock:
            _pending.discard(address_id)


def schedule(address_id: int | None) -> None:
    """Запустить заполнение координат в фоне."""

    if not address_id:
        return
    with _lock:
        if address_id in _pending:
            return
        _pending.add(address_id)
    threading.Thread(target=fill, args=(address_id,), daemon=True).start()


def schedule_for_case(case) -> None:
    """Координаты всех адресов заявки: объекта и нарушений."""

    ids: set[int] = set()
    control_object = getattr(case, "control_object", None)
    if control_object is not None and control_object.address_id:
        ids.add(control_object.address_id)
    for violation in getattr(case, "violations", []) or []:
        if violation.address_id:
            ids.add(violation.address_id)
    for address_id in ids:
        schedule(address_id)
