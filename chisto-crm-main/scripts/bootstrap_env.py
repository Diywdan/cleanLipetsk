"""Создаёт .env из .env.example, заменяя generate-me случайными секретами.

Секреты в консоль не печатаются: пароль администратора смотреть в .env на сервере.
Существующий .env не трогает без --force.
"""

from __future__ import annotations

import argparse
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLACEHOLDER = "generate-me"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="перезаписать существующий .env")
    parser.add_argument("--output", default=str(ROOT / ".env"))
    args = parser.parse_args()

    target = Path(args.output)
    if target.exists() and not args.force:
        raise SystemExit(f"{target} уже есть — секреты не перегенерирую (--force, если нужно)")

    lines, generated = [], []
    for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        key, sep, value = line.partition("=")
        if sep and not line.lstrip().startswith("#") and value.strip() == PLACEHOLDER:
            line = f"{key}={secrets.token_urlsafe(48)}"
            generated.append(key)
        lines.append(line)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        target.chmod(0o600)
    except OSError:
        pass
    print(f"Создан {target}; сгенерированы: {', '.join(generated)}")


if __name__ == "__main__":
    main()
