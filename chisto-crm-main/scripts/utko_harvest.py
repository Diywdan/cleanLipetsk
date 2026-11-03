"""Выгрузка мест накопления (слой 5) публичной карты ФГИС УТКО по Липецку.

Сетка тайлов -> id (кластеры раскрываются) -> карточки. Рецепт — «Справочник КП и ведение карточек», раздел 3.
Докачивает: готовые ячейки и карточки повторно не запрашивает. Только stdlib, запускается где угодно.

    python scripts/utko_harvest.py <папка>        # -> cells.json, details.jsonl, errors.log
    python -m app.cli kp-import-utko <папка>/details.jsonl --complete

В прямоугольник попадает и пригород: в реестр идут только карточки с location.areaName города (kp-import-utko --area).
Выгрузка 15.10.2026: 3 933 карточки, из них 3 064 с location.areaName «Городской округ г. Липецк».
"""
import json
import sys
import time
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

B = "https://public-api-utko.mnr.gov.ru/reo-fs-public-map-api/api/v2"
H = {"Origin": "https://utko.mnr.gov.ru", "Referer": "https://utko.mnr.gov.ru/",
     "Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
# Город с запасом: потом фильтр по areaName
LON0, LON1, LAT0, LAT1 = 39.36, 39.86, 52.47, 52.73
DLON, DLAT = 0.02, 0.0125
OUT = Path(sys.argv[1])


def call(url, data=None, tries=6):
    for i in range(tries):
        try:
            r = urllib.request.Request(url, data=json.dumps(data).encode() if data is not None else None,
                                       headers=H, method="POST" if data is not None else "GET")
            with urllib.request.urlopen(r, timeout=45) as resp:
                return resp.read().decode()
        except Exception as e:  # noqa: BLE001 — сервер медленный, повторяем
            if i == tries - 1:
                raise
            time.sleep(2 + 3 * i)


def new_filter():
    fid = str(uuid.uuid4())
    call(B + "/map/filter", {"id": fid, "layers": [5], "regionId": 48, "complexOnly": False, "objectTypeIn": [],
                             "objectStateIn": [], "wasteGroupIdIn": [], "yearInput": {"includeNulls": True}})
    return fid


def tile(fid, x0, y0, x1, y1):
    t = call(B + f"/map/tile?bbox={x0:.4f},{y0:.4f},{x1:.4f},{y1:.4f}&z=16&filterId={fid}&callback=cb")
    fc = json.loads(t[t.index("(") + 1:t.rindex(")")])
    ids = set()
    for f in fc.get("features", []):
        if f.get("type") == "Cluster":
            ids.update(f["properties"].get("ids") or [])
        else:
            ids.add(f["properties"].get("id") or f["id"])
    return sorted(ids)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    log = open(OUT / "errors.log", "a", encoding="utf-8")
    cells_path = OUT / "cells.json"
    cells = json.loads(cells_path.read_text(encoding="utf-8")) if cells_path.exists() else {}
    grid = []
    x = LON0
    while x < LON1 - 1e-9:
        y = LAT0
        while y < LAT1 - 1e-9:
            grid.append((round(x, 4), round(y, 4)))
            y += DLAT
        x += DLON
    todo = [g for g in grid if f"{g[0]},{g[1]}" not in cells]
    print(f"ячеек {len(grid)}, осталось {len(todo)}", flush=True)
    fid = new_filter()
    with ThreadPoolExecutor(5) as pool:
        futs = {pool.submit(tile, fid, gx, gy, gx + DLON, gy + DLAT): (gx, gy) for gx, gy in todo}
        for n, fu in enumerate(as_completed(futs), 1):
            gx, gy = futs[fu]
            try:
                cells[f"{gx},{gy}"] = fu.result()
            except Exception as e:  # noqa: BLE001
                log.write(f"tile {gx},{gy}: {e}\n")
            if n % 50 == 0:
                cells_path.write_text(json.dumps(cells), encoding="utf-8")
                print(f"ячейки {n}/{len(todo)}", flush=True)
    cells_path.write_text(json.dumps(cells), encoding="utf-8")
    failed_cells = len(grid) - len(cells)
    ids = sorted({i for v in cells.values() for i in v})
    print(f"id всего {len(ids)}, ячеек со сбоем {failed_cells}", flush=True)

    det_path = OUT / "details.jsonl"
    done = set()
    if det_path.exists():
        for line in det_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                done.add(json.loads(line)["id"])
    todo_ids = [i for i in ids if i not in done]
    print(f"карточек готово {len(done)}, осталось {len(todo_ids)}", flush=True)
    with open(det_path, "a", encoding="utf-8") as out, ThreadPoolExecutor(5) as pool:
        futs = {pool.submit(call, B + f"/sidebar/object?id={i}&layer=5"): i for i in todo_ids}
        for n, fu in enumerate(as_completed(futs), 1):
            i = futs[fu]
            try:
                d = json.loads(fu.result())
                d.setdefault("id", i)
                out.write(json.dumps(d, ensure_ascii=False) + "\n")
            except Exception as e:  # noqa: BLE001
                log.write(f"detail {i}: {e}\n")
            if n % 200 == 0:
                out.flush()
                print(f"карточки {n}/{len(todo_ids)}", flush=True)
    print("ГОТОВО", flush=True)


if __name__ == "__main__":
    main()
