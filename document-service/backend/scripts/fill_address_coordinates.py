"""Координаты адресов, у которых их ещё нет.

Адрес заводится строкой прямо в заявке, и координат у него при этом нет —
а без них обращение не встаёт на карту в интерфейсе диспетчера. Скрипт
находит такие адреса и проставляет координаты по открытому геокодеру
OpenStreetMap (Nominatim): он бесплатный, без ключа и без регистрации.

Запускать можно сколько угодно раз и по расписанию: адреса с координатами
пропускаются, поэтому повторный запуск ничего не портит. Пустые значения не
затирают уже введённые вручную — те, что заполнены людьми, скрипт не трогает.

Точность у геокодера улично-домовая. Для домов, которым нужна точность до
здания, есть scripts/geocode_addresses.py: он берёт центр здания из данных
OpenStreetMap.

Запуск внутри контейнера:
    PYTHONPATH=/app python scripts/fill_address_coordinates.py [--limit 50]
"""

import sys
import time
import urllib.parse
import urllib.request
from decimal import Decimal

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import Address


NOMINATIM = "https://nominatim.openstreetmap.org/search"
# Правила сервиса: представиться латиницей и не чаще одного запроса в секунду.
USER_AGENT = "document-service/0.2 (municipal control, Lipetsk; +https://chili.moneta-rus.pro)"
PAUSE_SECONDS = 1.1
DEFAULT_LIMIT = 50


def lookup(address: str) -> tuple[Decimal, Decimal] | None:
    """Координаты адреса по открытому геокодеру."""

    query = urllib.parse.urlencode(
        {"q": address, "format": "json", "limit": 1, "countrycodes": "ru"}
    )
    request = urllib.request.Request(
        f"{NOMINATIM}?{query}", headers={"User-Agent": USER_AGENT}
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        found = __import__("json").loads(response.read().decode("utf-8"))
    if not found:
        return None
    return Decimal(found[0]["lat"]), Decimal(found[0]["lon"])


def main() -> int:
    limit = DEFAULT_LIMIT
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])

    db = SessionLocal()
    filled = missed = 0
    try:
        addresses = list(
            db.scalars(
                select(Address)
                .where((Address.latitude.is_(None)) | (Address.longitude.is_(None)))
                .order_by(Address.id.desc())
                .limit(limit)
            )
        )
        if not addresses:
            print("адресов без координат нет")
            return 0
        print(f"адресов без координат: {len(addresses)}")
        for address in addresses:
            if not (address.full_address or "").strip():
                continue
            try:
                point = lookup(address.full_address)
            except Exception as error:  # noqa: BLE001 — сеть бывает разной
                print(f"  {address.full_address[:46]}: ошибка запроса ({error})")
                time.sleep(PAUSE_SECONDS)
                continue
            if point is None:
                missed += 1
                print(f"  {address.full_address[:46]}: не найдено")
            else:
                address.latitude, address.longitude = point
                filled += 1
                print(f"  {address.full_address[:46]}: {point[0]}, {point[1]}")
            time.sleep(PAUSE_SECONDS)
        db.commit()
        print(f"заполнено: {filled}, не найдено: {missed}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
