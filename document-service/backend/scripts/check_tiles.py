"""Задача 5: измерение слепка карты — охват, масштабы, точки заявок, цвет тайла.

Запускается и до, и после пересборки: сравнение «было/стало» по одним и тем
же точкам. Заодно проверяет, что новый файл вообще читается.

    PYTHONPATH=/app python scripts/check_tiles.py [путь_к_mbtiles]
"""
from __future__ import annotations

import math
import os
import sqlite3
import struct
import sys
import urllib.error
import urllib.request
import zlib
from pathlib import Path

PATH = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
    os.environ.get("MBTILES", "/data/tiles/lipetsk.mbtiles")
)
RENDER = "http://172.17.0.1:8080/styles/basic-preview"

POINTS = {
    "центр (Теперика, 3)": (39.5700, 52.6100),
    "Светлова, 31а": (39.6110, 52.6170),
    "восток города": (39.6500, 52.6100),
    "северо-восток": (39.7000, 52.6500),
    "юго-восток": (39.6500, 52.5500),
    "запад": (39.4500, 52.6100),
    "юг": (39.6000, 52.4800),
    "север": (39.6000, 52.7500),
    "край востока рамки": (39.8800, 52.6000),
    "край запада рамки": (39.3200, 52.6000),
}


def lonlat_to_tile(lon: float, lat: float, z: int) -> tuple[int, int]:
    n = 2 ** z
    x = int((lon + 180.0) / 360.0 * n)
    y = int((1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n)
    return x, y


def png_color_count(data: bytes) -> tuple[int, int, int]:
    """Сколько разных цветов в PNG и сколько байт."""
    pos, width, height = 8, 0, 0
    idat = bytearray()
    while pos < len(data):
        (length,) = struct.unpack(">I", data[pos:pos + 4])
        ctype = data[pos + 4:pos + 8]
        chunk = data[pos + 8:pos + 8 + length]
        if ctype == b"IHDR":
            width, height, depth, color = struct.unpack(">IIBB", chunk[:10])
        elif ctype == b"IDAT":
            idat += chunk
        elif ctype == b"IEND":
            break
        pos += 12 + length
    raw = zlib.decompress(bytes(idat))
    channels = 3 if color == 2 else 4
    stride = width * channels
    colors: set[bytes] = set()
    prev = bytearray(stride)
    offset = 0
    for _ in range(height):
        ftype = raw[offset]
        line = bytearray(raw[offset + 1:offset + 1 + stride])
        offset += 1 + stride
        if ftype == 1:
            for i in range(channels, stride):
                line[i] = (line[i] + line[i - channels]) & 0xFF
        elif ftype == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif ftype == 3:
            for i in range(stride):
                left = line[i - channels] if i >= channels else 0
                line[i] = (line[i] + ((left + prev[i]) >> 1)) & 0xFF
        elif ftype == 4:
            for i in range(stride):
                a = line[i - channels] if i >= channels else 0
                b = prev[i]
                c = prev[i - channels] if i >= channels else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pr) & 0xFF
        colors.update(bytes(line[i:i + channels]) for i in range(0, stride, channels))
        prev = line
    return len(colors), width, height


def main() -> int:
    print(f"файл: {PATH} ({PATH.stat().st_size / 1048576:.1f} МБ)")
    con = sqlite3.connect(f"file:{PATH}?mode=ro", uri=True)
    try:
        meta = dict(con.execute("select name, value from metadata"))
        print(f"  bounds: {meta.get('bounds')} | minzoom: {meta.get('minzoom')} | "
              f"maxzoom: {meta.get('maxzoom')}")

        print("\n--- что лежит в слепке ---")
        for z, cnt in con.execute(
            "select zoom_level, count(*) from tiles group by zoom_level order by zoom_level"
        ):
            print(f"  z{z:<3} тайлов {cnt}")

        print("\n--- тайлы над адресами ---")
        for name, (lon, lat) in POINTS.items():
            states = []
            for z in (14, 15, 16):
                x, y = lonlat_to_tile(lon, lat, z)
                tms = 2 ** z - 1 - y
                row = con.execute(
                    "select length(tile_data) from tiles where zoom_level=? "
                    "and tile_column=? and tile_row=?",
                    (z, x, tms),
                ).fetchone()
                states.append(f"z{z}={'есть' if row else 'нет'}")
            print(f"  {name:24} " + "  ".join(states))
    finally:
        con.close()

    print("\n--- что отрисовывает карта (число цветов в тайле) ---")
    for name, (lon, lat) in list(POINTS.items())[:4]:
        for z in (14, 16):
            x, y = lonlat_to_tile(lon, lat, z)
            url = f"{RENDER}/{z}/{x}/{y}.png"
            try:
                with urllib.request.urlopen(url, timeout=60) as resp:
                    data = resp.read()
            except Exception as exc:  # noqa: BLE001 — тайл может не отрисоваться
                print(f"  {name:24} z{z}: недоступно ({type(exc).__name__}: {exc})")
                continue
            try:
                colors, width, height = png_color_count(data)
                print(f"  {name:24} z{z}: {len(data):>6} байт, "
                      f"различных цветов {colors}")
            except Exception as exc:  # noqa: BLE001
                print(f"  {name:24} z{z}: {len(data)} байт, разобрать не удалось: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
