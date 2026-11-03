"""Проверка готовности: ловит ли она филиал без почты."""
from __future__ import annotations

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import ControlCase, OrganizationContact, OrganizationUnit
from app.services import validation


def main() -> int:
    db = SessionLocal()
    try:
        case = db.scalar(select(ControlCase).where(ControlCase.case_number == "122313"))
        unit = case.controlled_unit
        organization = case.controlled_organization
        print(f"заявка 122313: организация {organization.short_name!r}, "
              f"филиал {unit.name if unit else '—'!r}")

        before = validation.check_readiness(db, case.id, "primary_prescription")
        unit_issues = [i for i in before.issues if i.field.startswith("unit")]
        print(f"готовность сейчас: {before.is_ready}, замечаний по филиалу: "
              f"{len(unit_issues)}")
        for issue in unit_issues:
            print(f"    {issue.message}")

        if unit is None:
            print("у заявки нет филиала — проверять нечего")
            return 0

        # Убираем почту филиала и смотрим, поймает ли проверка.
        contacts = list(
            db.scalars(
                select(OrganizationContact).where(
                    OrganizationContact.organization_id == organization.id,
                    OrganizationContact.unit_id == unit.id,
                )
            )
        )
        print(f"контактов филиала: {len(contacts)}")
        saved = [(c.id, c.is_active) for c in contacts]
        for contact in contacts:
            contact.is_active = False
        db.flush()

        after = validation.check_readiness(db, case.id, "primary_prescription")
        unit_issues = [i for i in after.issues if i.field.startswith("unit")]
        print(f"без почты филиала: готово={after.is_ready}, "
              f"замечаний по филиалу: {len(unit_issues)}")
        for issue in unit_issues:
            print(f"    [{issue.document}] {issue.field}: {issue.message}")

        # Возвращаем как было.
        for contact_id, was_active in saved:
            contact = db.get(OrganizationContact, contact_id)
            if contact is not None:
                contact.is_active = was_active
        db.rollback()
        print("изменения откатаны")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
