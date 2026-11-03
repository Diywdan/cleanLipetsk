"""Координаты адресов для карты интерфейса диспетчера.

Обращение встаёт на карту по координатам своего адреса. Заполнить их можно
руками в справочнике адресов, а этот скрипт проставляет координаты тем
адресам, у которых их ещё нет.

Источник — открытый геокодер OpenStreetMap (Nominatim): он бесплатный и не
требует ключа, но просит не чаще одного запроса в секунду и осмысленный
User-Agent. Для боевой работы координаты лучше брать из официального
адресного реестра или у геокодера Яндекса: по российским адресам он точнее.

Запуск внутри контейнера:
    PYTHONPATH=/app python scripts/geocode_addresses.py            # заполнить
    PYTHONPATH=/app python scripts/geocode_addresses.py --dry-run  # только показать
"""

import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from decimal import Decimal

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import Address


NOMINATIM = "https://nominatim.openstreetmap.org/search"
# Геокодер Яндекса: по российским адресам точнее, но нужен ключ и он
# должен быть ограничен по IP сервера, а не по адресу сайта.
YANDEX_GEOCODER = (
    "https://geocode-maps.yandex.ru/v1/",
    "https://geocode-maps.yandex.ru/1.x/",
)
# Их правила: представиться и не частить с запросами. В заголовке только
# латиница: HTTP-заголовки передаются в latin-1, кириллица их ломает.
USER_AGENT = "document-service/0.2 (municipal control, Lipetsk; +https://82.202.140.51)"
PAUSE_SECONDS = 1.1


def lookup(address: str) -> tuple[Decimal, Decimal] | None:
    """Координаты адреса по открытому геокодеру."""

    query = urllib.parse.urlencode(
        {"q": address, "format": "json", "limit": 1, "countrycodes": "ru"}
    )
    request = urllib.request.Request(
        f"{NOMINATIM}?{query}", headers={"User-Agent": USER_AGENT}
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        found = json.loads(response.read().decode("utf-8"))
    if not found:
        return None
    item = found[0]
    return Decimal(item["lat"]), Decimal(item["lon"])


def lookup_yandex(api_key: str, address: str) -> tuple[Decimal, Decimal] | None:
    """Координаты адреса по геокодеру Яндекса.

    Кабинет выдаёт ключи под разные продукты, и у новых ключей endpoint
    другой, поэтому пробуем оба.
    """

    query = urllib.parse.urlencode(
        {
            "apikey": api_key,
            "geocode": address,
            "format": "json",
            "results": 1,
            "lang": "ru_RU",
        }
    )
    for url in YANDEX_GEOCODER:
        request = urllib.request.Request(
            f"{url}?{query}", headers={"User-Agent": USER_AGENT}
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                found = json.loads(response.read().decode("utf-8"))
        except Exception:  # noqa: BLE001 — второй endpoint может не подойти
            continue
        members = (
            found.get("response", {})
            .get("GeoObjectCollection", {})
            .get("featureMember", [])
        )
        if not members:
            return None
        # В ответе Яндекса порядок «долгота широта», у нас хранится наоборот.
        longitude, latitude = members[0]["GeoObject"]["Point"]["pos"].split()
        return Decimal(latitude), Decimal(longitude)
    return None


# Здания в OpenStreetMap: у них есть адрес и геометрия, поэтому центр здания
# и есть точка нужного дома — точнее текстового геокодера, который знает
# только улицу.
OVERPASS = "https://overpass-api.de/api/interpreter"
# Границы Липецка: спрашиваем здания только по городу.
CITY_BBOX = "52.53,39.42,52.68,39.68"


def normalize_street(value: str) -> str:
    """«ул. Теперика» и «улица Теперика» — одна улица."""

    text = (value or "").lower()
    for word in ("улица", "ул.", "ул ", "проспект", "пр-т", "переулок", "шоссе", "бульвар", "б-р"):
        text = text.replace(word, " ")
    return re.sub(r"[^а-яёa-z0-9]+", "", text)


def street_and_house(address: Address) -> tuple[str, str]:
    """Улица и дом адреса: по ним ищем здание в OpenStreetMap."""

    street = address.street or ""
    house = (address.house or "").strip().lower()
    full = address.full_address or ""
    if not street:
        found = re.search(
            r"(?:ул\.?|улица|проспект|пр-т|переулок|шоссе|бульвар|б-р)\s*([^,]+?)(?:\s*,|\s+д)",
            full,
            re.I,
        )
        if found:
            street = found.group(1).strip()
    if not house:
        found = re.search(r"(?:д\.?|дом)\s*([0-9]+[а-яa-z]?)", full, re.I)
        if found:
            house = found.group(1).lower()
    return street, house


def osm_house_points(streets: list[str]) -> dict[tuple[str, str], tuple[Decimal, Decimal]]:
    """Координаты домов: центр здания из данных OpenStreetMap."""

    # Точные совпадения вместо регулярного выражения: поиск по значению тега
    # идёт по индексу и не упирается в таймаут на весь город. Варианты
    # написания — потому что в OSM улица может быть и «Теперика», и
    # «улица Теперика».
    variants: set[str] = set()
    for street in streets:
        cleaned = (street or "").strip()
        if not cleaned:
            continue
        variants.update({cleaned, "улица " + cleaned, "ул. " + cleaned})
    if not variants:
        return {}
    parts = "".join(
        'way["addr:street"="' + variant + '"]["addr:housenumber"](' + CITY_BBOX + ');'
        for variant in sorted(variants)
    )
    query = "[out:json][timeout:120];" + parts + "out center tags;"
    request = urllib.request.Request(
        f"{NOMINATIM}?{query}", headers={"User-Agent": USER_AGENT}
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        found = json.loads(response.read().decode("utf-8"))
    if not found:
        return None
    item = found[0]
    return Decimal(item["lat"]), Decimal(item["lon"])


def lookup_yandex(api_key: str, address: str) -> tuple[Decimal, Decimal] | None:
    """Координаты адреса по геокодеру Яндекса.

    Кабинет выдаёт ключи под разные продукты, и у новых ключей endpoint
    другой, поэтому пробуем оба.
    """

    query = urllib.parse.urlencode(
        {
            "apikey": api_key,
            "geocode": address,
            "format": "json",
            "results": 1,
            "lang": "ru_RU",
        }
    )
    for url in YANDEX_GEOCODER:
        request = urllib.request.Request(
            f"{url}?{query}", headers={"User-Agent": USER_AGENT}
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                found = json.loads(response.read().decode("utf-8"))
        except Exception:  # noqa: BLE001 — второй endpoint может не подойти
            continue
        members = (
            found.get("response", {})
            .get("GeoObjectCollection", {})
            .get("featureMember", [])
        )
        if not members:
            return None
        # В ответе Яндекса порядок «долгота широта», у нас хранится наоборот.
        longitude, latitude = members[0]["GeoObject"]["Point"]["pos"].split()
        return Decimal(latitude), Decimal(longitude)
    return None


# Здания в OpenStreetMap: у них есть адрес и геометрия, поэтому центр здания
# и есть точка нужного дома — точнее текстового геокодера, который знает
# только улицу.
OVERPASS = "https://overpass-api.de/api/interpreter"
# Границы Липецка: спрашиваем здания только по городу.
CITY_BBOX = "52.53,39.42,52.68,39.68"


def normalize_street(value: str) -> str:
    """«ул. Теперика» и «улица Теперика» — одна улица."""

    text = (value or "").lower()
    for word in ("улица", "ул.", "ул ", "проспект", "пр-т", "переулок", "шоссе", "бульвар", "б-р"):
        text = text.replace(word, " ")
    return re.sub(r"[^а-яёa-z0-9]+", "", text)


def street_and_house(address: Address) -> tuple[str, str]:
    """Улица и дом адреса: по ним ищем здание в OpenStreetMap."""

    street = address.street or ""
    house = (address.house or "").strip().lower()
    full = address.full_address or ""
    if not street:
        found = re.search(
            r"(?:ул\.?|улица|проспект|пр-т|переулок|шоссе|бульвар|б-р)\s*([^,]+?)(?:\s*,|\s+д)",
            full,
            re.I,
        )
        if found:
            street = found.group(1).strip()
    if not house:
        found = re.search(r"(?:д\.?|дом)\s*([0-9]+[а-яa-z]?)", full, re.I)
        if found:
            house = found.group(1).lower()
    return street, house


def osm_house_points(streets: list[str]) -> dict[tuple[str, str], tuple[Decimal, Decimal]]:
    """Координаты домов: центр здания из данных OpenStreetMap."""

    pattern = "|".join(sorted({s for s in streets if s}, key=len, reverse=True))
    if not pattern:
        return {}
    query = (
        "[out:json][timeout:60];"
        f'way["addr:housenumber"]["addr:street"~"{pattern}",i]({CITY_BBOX});'
        "out center tags;"
    )
    request = urllib.request.Request(
        f"{OVERPASS}?data={urllib.parse.quote(query)}",
        headers={"User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        data = json.loads(response.read().decode("utf-8"))
    points: dict[tuple[str, str], tuple[Decimal, Decimal]] = {}
    for element in data.get("elements", []):
        tags = element.get("tags", {})
        center = element.get("center") or {}
        if not center:
            continue
        key = (
            normalize_street(tags.get("addr:street", "")),
            (tags.get("addr:housenumber") or "").strip().lower(),
        )
        points[key] = (Decimal(str(center["lat"])), Decimal(str(center["lon"])))
    return points


def main() -> int:
    dry_run = "--dry-run" in sys.argv
    refresh = "--refresh" in sys.argv
    # Режим зданий OpenStreetMap: точка берётся с контура дома, а не с улицы.
    osm_mode = "--osm-houses" in sys.argv
    # Ключ геокодера: --yandex <ключ> или переменная окружения.
    yandex_key = None
    if "--yandex" in sys.argv:
        yandex_key = sys.argv[sys.argv.index("--yandex") + 1]
    else:
        yandex_key = os.environ.get("YANDEX_GEOCODER_KEY")
    db = SessionLocal()
    filled = 0
    missed: list[str] = []
    try:
        statement = select(Address).order_by(Address.id)
        if not refresh:
            statement = statement.where(
                (Address.latitude.is_(None)) | (Address.longitude.is_(None))
            )
        addresses = list(db.scalars(statement))
        if osm_mode:
            streets = {}
            for address in addresses:
                street, _house = street_and_house(address)
                if street:
                    streets[street] = True
            print(f"улиц в запросе: {len(streets)}")
            points = osm_house_points(sorted(streets))
            print(f"домов найдено в OpenStreetMap: {len(points)}")
            filled = missed = 0
            for address in addresses:
                street, house = street_and_house(address)
                point = points.get((normalize_street(street), house))
                if point is None:
                    missed += 1
                    print(f"  {address.full_address[:44]}: дома нет в OSM")
                    continue
                latitude, longitude = point
                print(f"  {address.full_address[:44]}: дом {latitude}, {longitude}")
                if not dry_run:
                    address.latitude = latitude
                    address.longitude = longitude
                filled += 1
            if not dry_run:
                db.commit()
            print(f"координаты по домам: {filled}, не найдено: {missed}")
            return 0

        print(
            f"адресов к обработке: {len(addresses)}"
            + (f", геокодер: {'Яндекса' if yandex_key else 'OpenStreetMap'}")
        )
        for address in addresses:
            try:
                point = (
                    lookup_yandex(yandex_key, address.full_address)
                    if yandex_key
                    else lookup(address.full_address)
                )
            except Exception as error:  # noqa: BLE001 — сеть бывает разной
                print(f"  {address.full_address[:50]}: ошибка запроса ({error})")
                time.sleep(PAUSE_SECONDS)
                continue
            if point is None:
                missed.append(address.full_address)
                print(f"  {address.full_address[:50]}: не найдено")
            else:
                latitude, longitude = point
                print(
                    f"  {address.full_address[:50]}: {latitude}, {longitude}"
                    + (" (только показ)" if dry_run else "")
                )
                if not dry_run:
                    address.latitude = latitude
                    address.longitude = longitude
                    filled += 1
            time.sleep(PAUSE_SECONDS)
        if not dry_run:
            db.commit()
        print(f"заполнено: {filled}, не найдено: {len(missed)}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
