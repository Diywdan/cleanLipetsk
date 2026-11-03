"""Где в бланках печатаются нормы нарушения и как они выглядят."""
from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

from lxml import etree
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import DocumentType
from app.services import generation, storage

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
KEYS = ("violation_provisions_genitive", "violation_npa_titles", "provisions")
PHRASE = "Правил благоустройства"


def template_text(data: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        root = etree.fromstring(archive.read("word/document.xml"))
        return "".join(n.text or "" for n in root.iter(f"{W}t"))


def main() -> None:
    root = Path("/app/templates")
    print("=== бланки, где встречаются нормы ===")
    for path in sorted(root.glob("*/*.docx")):
        try:
            text = template_text(path.read_bytes())
        except Exception:  # noqa: BLE001
            continue
        hits = [key for key in KEYS if key in text]
        if hits:
            for match in re.finditer(
                r"\{\{[^}]*(" + "|".join(KEYS) + r")[^}]*\}\}", text
            ):
                print(f"  {path.relative_to(root)}: {match.group(0)[:110]}")

    print()
    print("=== как выглядит норма в собранном протоколе осмотра ===")
    db = SessionLocal()
    try:
        from app.models import DataSnapshot

        snapshot = db.scalars(
            select(DataSnapshot)
            .where(DataSnapshot.entity_kind == "package")
            .order_by(DataSnapshot.id.desc())
        ).first()
        payload = snapshot.payload
        protocol = payload["protocol"]
        print(f"  violation_provisions_genitive = "
              f"{protocol.get('violation_provisions_genitive')!r}")
        print(f"  violation_npa_titles = {protocol.get('violation_npa_titles')!r}")
        print(f"  violation_npa_titles_genitive = "
              f"{protocol.get('violation_npa_titles_genitive')!r}")
        violations = payload.get("violations") or []
        for violation in violations:
            print(f"  нарушение: {violation.get('description', '')[:60]!r}")
            for provision in violation.get("provisions") or []:
                print(f"    reference={provision.get('reference')!r}")
                print(f"    npa_title={provision.get('npa_title')!r}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
