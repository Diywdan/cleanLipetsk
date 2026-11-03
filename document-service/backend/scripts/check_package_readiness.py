"""Готовность повторного пакета: что мешает, а что только замечание."""
from __future__ import annotations

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import ControlCase, PackageKind
from app.services import validation


def main() -> None:
    db = SessionLocal()
    try:
        case = db.scalar(select(ControlCase).where(ControlCase.case_number == "122313"))
        print(f"заявка {case.case_number}: номер из реестра = {case.erp_number!r}")
        for kind in db.scalars(select(PackageKind).order_by(PackageKind.sort_order, PackageKind.id)):
            try:
                readiness = validation.check_readiness(db, case.id, kind.code).as_dict()
            except ValueError as error:
                print(f"  {kind.code}: {error}")
                continue
            print()
            print(f"  пакет {kind.code}: соберётся = {readiness['is_ready']}")
            for issue in readiness["issues"]:
                print(f"    мешает:   {issue['message']}")
            for warning in readiness["warnings"]:
                print(f"    замечание: {warning['message']}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
