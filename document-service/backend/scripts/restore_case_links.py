"""Восстановление связей заявки 122313: инспектор, участник, основания.

Проверка формы отправила частичную форму, и обработчик пересобрал вложенные
наборы с нуля: инспектор, участник дела и основания были удалены. Значения
берутся из снимка данных пакета — там они сохранены как были.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import (
    ControlCase,
    ControlCaseBase,
    ControlCaseInspector,
    ControlCaseParty,
    Organization,
    OrganizationContact,
    OrganizationRequisite,
    OrganizationSignatory,
    OrganizationUnit,
)
from app.models.enums import CaseBaseKind, CasePartyKind, InspectorRole

CASE_NUMBER = "122313"
SNAPSHOT_PATH = Path("/app/case-122313-snapshot.json")


def _find_unit(db, organization_id: int, name: str | None):
    if not name:
        return None
    for unit in db.scalars(
        select(OrganizationUnit).where(
            OrganizationUnit.organization_id == organization_id
        )
    ):
        if unit.name == name:
            return unit
    return None


def _current_requisite(db, organization_id: int, unit_id: int | None):
    query = select(OrganizationRequisite).where(
        OrganizationRequisite.organization_id == organization_id,
        OrganizationRequisite.valid_to.is_(None),
    )
    if unit_id is None:
        query = query.where(OrganizationRequisite.unit_id.is_(None))
    else:
        query = query.where(OrganizationRequisite.unit_id == unit_id)
    return db.scalars(query.order_by(OrganizationRequisite.valid_from.desc())).first()


def main() -> None:
    payload = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    db = SessionLocal()
    try:
        case = db.scalar(
            select(ControlCase).where(ControlCase.case_number == CASE_NUMBER)
        )
        if case is None:
            raise SystemExit("заявка не найдена")

        # 1. Инспектор по заявке.
        for item in payload.get("inspectors") or []:
            exists = db.scalar(
                select(ControlCaseInspector).where(
                    ControlCaseInspector.control_case_id == case.id,
                    ControlCaseInspector.inspector_id == item["id"],
                )
            )
            if exists is None:
                db.add(
                    ControlCaseInspector(
                        control_case_id=case.id,
                        inspector_id=item["id"],
                        role=InspectorRole(item["role"]),
                    )
                )

        # 2. Участник дела — контролируемое лицо (организация и филиал).
        person = payload.get("controlled_person") or {}
        organization = db.get(Organization, case.controlled_organization_id)
        if organization is not None:
            unit_name = (person.get("unit") or {}).get("name")
            unit = db.get(OrganizationUnit, case.controlled_unit_id) if case.controlled_unit_id else None
            if unit is None:
                unit = _find_unit(db, organization.id, unit_name)
            requisite = _current_requisite(
                db, organization.id, unit.id if unit is not None else None
            )
            contact = db.scalars(
                select(OrganizationContact)
                .where(OrganizationContact.organization_id == organization.id)
                .order_by(OrganizationContact.id)
            ).first()
            signatory = db.scalars(
                select(OrganizationSignatory)
                .where(OrganizationSignatory.organization_id == organization.id)
                .order_by(OrganizationSignatory.id)
            ).first()
            exists = db.scalar(
                select(ControlCaseParty).where(
                    ControlCaseParty.control_case_id == case.id,
                    ControlCaseParty.party_kind == CasePartyKind.CONTROLLED,
                )
            )
            if exists is None:
                db.add(
                    ControlCaseParty(
                        control_case_id=case.id,
                        party_kind=CasePartyKind.CONTROLLED,
                        organization_id=organization.id,
                        unit_id=unit.id if unit is not None else None,
                        requisite_id=requisite.id if requisite is not None else None,
                        signatory_id=signatory.id if signatory is not None else None,
                        contact_id=contact.id if contact is not None else None,
                    )
                )

        # 3. Основания проведения: материал МУ и передача из интерфейса.
        for basis in payload.get("bases") or []:
            kind = CaseBaseKind(basis.get("kind"))
            document_date = basis.get("document_date")
            parsed = (
                datetime.fromisoformat(document_date) if document_date else None
            )
            exists = db.scalar(
                select(ControlCaseBase).where(
                    ControlCaseBase.control_case_id == case.id,
                    ControlCaseBase.kind == kind,
                )
            )
            if exists is None:
                db.add(
                    ControlCaseBase(
                        control_case_id=case.id,
                        kind=kind,
                        description=basis.get("description"),
                        document_date=parsed,
                        document_number=basis.get("document_number"),
                    )
                )

        db.commit()

        print("после восстановления:")
        for item in db.scalars(
            select(ControlCaseInspector).where(
                ControlCaseInspector.control_case_id == case.id
            )
        ):
            print(f"  инспектор: {item.inspector.full_name} ({item.role.value})")
        for item in db.scalars(
            select(ControlCaseParty).where(ControlCaseParty.control_case_id == case.id)
        ):
            print(f"  участник: {item.party_kind.value}, "
                  f"{item.organization.short_name if item.organization else None}, "
                  f"филиал: {item.unit.name if item.unit else None}, "
                  f"подписант: {item.signatory.full_name if item.signatory else None}")
        for item in db.scalars(
            select(ControlCaseBase).where(ControlCaseBase.control_case_id == case.id)
        ):
            print(f"  основание: {item.kind.value}, {item.document_date}, "
                  f"{item.description!r}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
