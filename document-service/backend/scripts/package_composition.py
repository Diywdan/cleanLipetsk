"""Какие документы входят в каждый вид пакета и какие версии бланков действуют."""
from __future__ import annotations

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import (
    DocumentTemplate,
    DocumentType,
    PackageKind,
    PackageKindDocument,
)
from app.services import generation


def main() -> None:
    db = SessionLocal()
    try:
        types = {
            dt.id: dt.code
            for dt in db.scalars(select(DocumentType).order_by(DocumentType.id))
        }
        print("=== состав пакетов ===")
        for kind in db.scalars(select(PackageKind).order_by(PackageKind.id)):
            rows = list(
                db.scalars(
                    select(PackageKindDocument)
                    .where(PackageKindDocument.package_kind_id == kind.id)
                    .order_by(PackageKindDocument.sequence_no)
                )
            )
            codes = [types.get(r.document_type_id, "?") for r in rows]
            print(f"  {kind.code:24} [{kind.name[:40]}]")
            print(f"      документов {len(codes)}: {', '.join(codes)}")
        print()
        print("=== действующие версии бланков ===")
        for dt in db.scalars(
            select(DocumentType).order_by(DocumentType.sort_order, DocumentType.id)
        ):
            template = generation._active_template(db, dt.id)
            all_versions = [
                t.version
                for t in db.scalars(
                    select(DocumentTemplate)
                    .where(DocumentTemplate.document_type_id == dt.id)
                    .order_by(DocumentTemplate.version)
                )
            ]
            print(f"  {dt.code:24} действует {template.version if template else '—':<4} "
                  f"(всего версий {len(all_versions)}: {', '.join(all_versions)})")
    finally:
        db.close()


if __name__ == "__main__":
    main()
