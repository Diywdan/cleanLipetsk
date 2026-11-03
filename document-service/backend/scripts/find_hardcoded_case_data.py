"""Поиск жёстко вписанных строк бланков в коде и в данных.

Ищем то, что заказчик увидел в протоколе об административном правонарушении:
даты, номера предписаний, адреса, названия организаций — если это зашито
в коде, а не пришло из данных заявки, документ будет печатать чужой случай.
"""
from __future__ import annotations

from pathlib import Path

APP = Path("/app/app")
ROOT = Path("/app")

# Строки, которые не должны встречаться в коде: это данные конкретного дела.
NEEDLES = [
    "60-летия",
    "ПОЧТА РОССИИ",
    "3-я Песчаная",
    "48001704800001209198",
    "12.08.2026",
    "06.07.2026",
    "07.08.2026",
    "19.5",
]


def main() -> None:
    print("=== поиск данных конкретного дела в коде ===")
    found = 0
    for path in APP.rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="replace")
        for number, line in enumerate(text.splitlines(), 1):
            for needle in NEEDLES:
                if needle in line:
                    found += 1
                    print(f"  {path.relative_to(APP)}:{number}: "
                          f"[{needle}] {line.strip()[:110]}")
    if not found:
        print("  чисто: данных конкретных дел в коде нет")

    print()
    print("=== жёстко вписанные строки в шаблонах (не подстановки) ===")
    for directory in sorted((ROOT / "templates").glob("*")):
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.docx")):
            print(f"  {path.relative_to(ROOT)}")

    print()
    print("=== где в коде собираются фразы для документов ===")
    for path in (APP / "services").glob("*.py"):
        text = path.read_text(encoding="utf-8", errors="replace")
        for number, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("f\"") and len(stripped) > 60 and (
                "предписан" in stripped or "протокол" in stripped
                or "постановлен" in stripped or "Департамент" in stripped
            ):
                print(f"  {path.name}:{number}: {stripped[:110]}")


if __name__ == "__main__":
    main()
