"""Проверка ключа Яндекс Карт для интерфейса диспетчера.

Карте нужен ключ JavaScript API, серверу (заполнение координат) — ключ
HTTP Геокодера. Это разные продукты, и ключи у них разные, поэтому скрипт
проверяет оба и говорит, что именно не так.

Ответы сервиса и что они значат:

* ``HTTP 200`` — ключ работает;
* ``limited`` — ключ верный, но тариф не подключён или лимит исчерпан:
  в кабинете разработчика нужно подключить тариф продукта;
* ``Invalid api key`` — ключ не знает этот сервис: он создан для другого
  продукта, либо не входит в ограничения (у карты — по адресу сайта,
  у геокодера — по IP сервера).

Важная тонкость: у сервисов разные ограничения. Ключ карты работает в
браузере, поэтому его ограничивают адресом сайта; ключ геокодера вызывается
с сервера, поэтому ему нужно ограничение по IP (или никакого) — с ограничением
по адресу сайта серверные запросы будут отклоняться.

Запуск внутри контейнера:
    PYTHONPATH=/app python scripts/check_maps_key.py <ключ> [адрес сайта]
"""

import json
import sys
import urllib.error
import urllib.parse
import urllib.request


MAPS_V3 = "https://api-maps.yandex.ru/v3/"
GEOCODER_V1 = "https://geocode-maps.yandex.ru/v1/"
GEOCODER_1X = "https://geocode-maps.yandex.ru/1.x/"
DEFAULT_SITE = "https://82.202.140.51/dispatch/"
SAMPLE_ADDRESS = "Липецк, улица Теперика, 11"


def fetch(url: str, headers: dict | None = None) -> tuple[int, str]:
    request = urllib.request.Request(
        url,
        headers=headers
        or {"User-Agent": "Mozilla/5.0 (compatible; document-service check)"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, response.read(400).decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        return error.code, error.read(400).decode("utf-8", "replace")


def verdict(status: int, body: str, service: str) -> str:
    if status == 200:
        return f"работает: {service} отвечает"
    if "limited" in body:
        return (
            f"ключ верный, но лимит исчерпан или тариф не подключён — "
            f"подключите тариф {service} в кабинете разработчика"
        )
    if "Invalid api key" in body:
        return (
            f"ключ не знает {service}: он создан для другого продукта "
            f"или не входит в ограничения ключа"
        )
    return f"неожиданный ответ: {body[:80]!r}"


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    api_key = sys.argv[1].strip()
    site = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_SITE

    print("=== ключ карты (JavaScript API) ===")
    status, body = fetch(
        f"{MAPS_V3}?apikey={api_key}&lang=ru_RU", {"Referer": site}
    )
    print(f"--- HTTP {status}: {body[:90].strip()!r}")
    print(f"    {verdict(status, body, 'JavaScript API')}")

    print("=== ключ геокодера (HTTP Геокодер) ===")
    query = urllib.parse.urlencode(
        {
            "apikey": api_key,
            "geocode": SAMPLE_ADDRESS,
            "format": "json",
            "results": 1,
            "lang": "ru_RU",
        }
    )
    geocoder_ok = False
    for url in (GEOCODER_V1, GEOCODER_1X):
        status, body = fetch(f"{url}?{query}")
        print(f"--- {url.split('/')[-2]}: HTTP {status}: {body[:90].strip()!r}")
        if status == 200:
            try:
                data = json.loads(body)
                members = data["response"]["GeoObjectCollection"]["featureMember"]
                if members:
                    point = members[0]["GeoObject"]["Point"]["pos"]
                    print(f"    координаты (долгота широта): {point}")
                geocoder_ok = True
            except (KeyError, ValueError):
                pass
            break
        if "Invalid api key" not in body:
            break
    print(f"    {verdict(200 if geocoder_ok else status, '' if geocoder_ok else body, 'HTTP Геокодер')}")

    return 0 if geocoder_ok else 1


if __name__ == "__main__":
    sys.exit(main())
