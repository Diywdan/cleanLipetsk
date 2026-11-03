"""Демонстрационный набор данных по разобранным документам.

Создаёт дело, полностью заполненное так, как в примерах первичного пакета:
АО «РИР Энерго» в лице филиала «Липецкая генерация», земельный участок на
ул. Теперика, д. 3, выявленное нарушение и предписание со сроком.

Запуск внутри контейнера:  python scripts/seed_demo.py
Повторный запуск ничего не дублирует.
"""

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models import (
    Address,
    ControlAction,
    ControlActionFile,
    ControlBody,
    ControlBodySignatory,
    ControlBodyUnit,
    ControlCase,
    ControlCaseBase,
    ControlCaseInspector,
    ControlCaseStatus,
    ControlForm,
    ControlKind,
    ControlObject,
    ControlObjectType,
    Decision,
    DecisionItem,
    Inspector,
    NpaArticle,
    Organization,
    OrganizationContact,
    OrganizationRequisite,
    OrganizationRole,
    OrganizationSignatory,
    OrganizationUnit,
    Prescription,
    PrescriptionItem,
    PrescriptionStatus,
    StoredFile,
    Violation,
    ViolationProvision,
    ViolationType,
)
from app.models.enums import (
    CaseBaseKind,
    ContactKind,
    ContactPurpose,
    ControlActionType,
    DecisionItemKind,
    FileKind,
    InspectorRole,
    OrganizationKind,
    OrganizationRoleCode,
    OrganizationUnitKind,
    SignatoryBasisKind,
)
from app.services import storage

MSK = timezone(timedelta(hours=3))

ORG_NAME = "АО «РИР Энерго»"
ORG_INN = "6829012680"
UNIT_NAME = "филиал АО «РИР Энерго»-«Липецкая генерация»"
BODY_NAME = "Департамент развития территории администрации города Липецка"
UNIT_BODY = "Управление муниципального контроля"
ERP_NUMBER = "48001704800001509034"
INSPECTOR_NAME = "Комолых Евгения Юрьевна"
APPROVER_NAME = "Инютина Т.Н."

DEMO_ADDRESSES = [
    "398600, Липецкая область, г Липецк, ул. Московская, д 8 а",
    "119017, г. Москва, вн. тер. г. Муниципальный округ Якиманка, "
    "ул. Большая Ордынка, д. 40, стр. 1",
    "г. Липецк, ул. Теперика, д.3",
]

# Снимок, который прикладывается к протоколу осмотра.
DEMO_PHOTO = Path("/app/scripts/fixtures/demo_photo.png")


def get_or_create_address(db: Session, full: str, **kwargs) -> Address:
    address = db.scalar(select(Address).where(Address.full_address == full))
    if address is None:
        address = Address(full_address=full, **kwargs)
        db.add(address)
        db.flush()
    return address


def reset(db: Session) -> None:
    """Удаляет демонстрационные данные, не трогая справочники и орган контроля."""

    case = db.scalar(select(ControlCase).where(ControlCase.erp_number == ERP_NUMBER))
    if case is not None:
        db.delete(case)

    organization = db.scalar(select(Organization).where(Organization.inn == ORG_INN))
    if organization is not None:
        db.delete(organization)

    db.flush()

    for control_object in db.scalars(
        select(ControlObject).where(
            ControlObject.address_id.in_(
                select(Address.id).where(Address.full_address.in_(DEMO_ADDRESSES))
            )
        )
    ):
        db.delete(control_object)

    inspector = db.scalar(
        select(Inspector).where(Inspector.full_name == INSPECTOR_NAME)
    )
    if inspector is not None:
        db.delete(inspector)

    approver = db.scalar(
        select(ControlBodySignatory).where(
            ControlBodySignatory.full_name == APPROVER_NAME
        )
    )
    if approver is not None:
        db.delete(approver)

    db.flush()

    for full in DEMO_ADDRESSES:
        address = db.scalar(select(Address).where(Address.full_address == full))
        if address is not None:
            db.delete(address)

    # Файлы фотоматериала не связаны с делом каскадом — удаляем явно.
    if DEMO_PHOTO.exists():
        demo_file = db.scalar(
            select(StoredFile).where(StoredFile.original_name == DEMO_PHOTO.name)
        )
        if demo_file is not None:
            db.delete(demo_file)

    db.commit()


def main() -> None:
    db = SessionLocal()
    try:
        if "--reset" in sys.argv:
            reset(db)
            print("демонстрационные данные удалены")

        existing = db.scalar(
            select(ControlCase).where(ControlCase.erp_number == ERP_NUMBER)
        )
        if existing is not None:
            print(f"дело уже существует: id={existing.id}")
            return

        body = db.scalar(select(ControlBody).where(ControlBody.name == BODY_NAME))
        if body is None:
            raise SystemExit("нет органа контроля — сначала примените миграции")

        body_unit = db.scalar(
            select(ControlBodyUnit).where(
                ControlBodyUnit.control_body_id == body.id,
                ControlBodyUnit.name == UNIT_BODY,
            )
        )

        inspector = db.scalar(
            select(Inspector).where(Inspector.full_name == "Комолых Евгения Юрьевна")
        )
        if inspector is None:
            inspector = Inspector(
                control_body_unit_id=body_unit.id if body_unit else None,
                full_name="Комолых Евгения Юрьевна",
                position=(
                    "главный консультант управления муниципального контроля "
                    "департамента развития территории администрации города Липецка"
                ),
                # Творительный падеж для протокола осмотра: склонение ФИО
                # морфологией в официальных документах даёт ошибки.
                full_name_instrumental="Комолых Евгенией Юрьевной",
                position_instrumental=(
                    "Главным консультантом управления муниципального контроля "
                    "департамента развития территории администрации города Липецка"
                ),
                phone="38-77-75",
                email="komolykheyu@lipetskcity.ru",
            )
            db.add(inspector)
            db.flush()

        approver = db.scalar(
            select(ControlBodySignatory).where(
                ControlBodySignatory.full_name == "Инютина Т.Н."
            )
        )
        if approver is None:
            approver = ControlBodySignatory(
                control_body_id=body.id,
                unit_id=body_unit.id if body_unit else None,
                full_name="Инютина Т.Н.",
                position=(
                    "Заместитель председателя департамента развития территории "
                    "администрации города Липецка"
                ),
                # В акте должность утверждающего стоит в родительном падеже:
                # «в соответствии с заданием заместителя председателя …».
                position_genitive=(
                    "заместителя председателя департамента развития территории "
                    "администрации города Липецка"
                ),
                short_name_genitive="Инютиной Т.Н.",
                is_primary=True,
                valid_from=date(2026, 1, 1),
            )
            db.add(approver)
            db.flush()

        address_legal = get_or_create_address(
            db,
            "398600, Липецкая область, г Липецк, ул. Московская, д 8 а",
            postal_code="398600",
            region="Липецкая область",
            locality="г. Липецк",
            street="ул. Московская",
            house="8 а",
        )
        address_head = get_or_create_address(
            db,
            "119017, г. Москва, вн. тер. г. Муниципальный округ Якиманка, "
            "ул. Большая Ордынка, д. 40, стр. 1",
            postal_code="119017",
            region="г. Москва",
            street="ул. Большая Ордынка",
            house="40",
            structure="1",
        )
        address_object = get_or_create_address(
            db,
            "г. Липецк, ул. Теперика, д.3",
            locality="г. Липецк",
            street="ул. Теперика",
            house="3",
        )

        organization = db.scalar(
            select(Organization).where(Organization.inn == ORG_INN)
        )
        if organization is None:
            organization = Organization(
                kind=OrganizationKind.LEGAL_ENTITY,
                short_name=ORG_NAME,
                full_name=ORG_NAME,
                inn=ORG_INN,
            )
            db.add(organization)
            db.flush()

            db.add(
                OrganizationRequisite(
                    organization_id=organization.id,
                    inn=ORG_INN,
                    legal_address_id=address_head.id,
                    valid_from=date(2026, 1, 1),
                )
            )
            db.add(
                OrganizationContact(
                    organization_id=organization.id,
                    kind=ContactKind.EMAIL,
                    purpose=ContactPurpose.DOCUMENT_DELIVERY,
                    value="tula@quadra.ru",
                )
            )
            db.add(
                OrganizationRole(
                    organization_id=organization.id,
                    role=OrganizationRoleCode.REGIONAL_OPERATOR,
                    valid_from=date(2026, 1, 1),
                )
            )
            db.add(
                OrganizationSignatory(
                    organization_id=organization.id,
                    full_name="Законный представитель",
                    position="Генеральный директор",
                    basis_kind=SignatoryBasisKind.CHARTER,
                    is_primary=True,
                    valid_from=date(2026, 1, 1),
                )
            )

        unit = db.scalar(
            select(OrganizationUnit).where(
                OrganizationUnit.organization_id == organization.id,
                OrganizationUnit.name == UNIT_NAME,
            )
        )
        if unit is None:
            unit = OrganizationUnit(
                organization_id=organization.id,
                kind=OrganizationUnitKind.BRANCH,
                name=UNIT_NAME,
                address_id=address_legal.id,
            )
            db.add(unit)
            db.flush()

            db.add(
                OrganizationRequisite(
                    organization_id=organization.id,
                    unit_id=unit.id,
                    inn=ORG_INN,
                    legal_address_id=address_legal.id,
                    valid_from=date(2026, 1, 1),
                )
            )
            db.add(
                OrganizationContact(
                    organization_id=organization.id,
                    unit_id=unit.id,
                    kind=ContactKind.EMAIL,
                    purpose=ContactPurpose.DOCUMENT_DELIVERY,
                    value="knc@lipetsk.quadra.ru",
                )
            )
            db.add(
                OrganizationSignatory(
                    organization_id=organization.id,
                    unit_id=unit.id,
                    full_name="Директор филиала",
                    position="Директор филиала",
                    basis_kind=SignatoryBasisKind.TRUST,
                    is_primary=True,
                    valid_from=date(2026, 1, 1),
                )
            )

        object_type = db.scalar(
            select(ControlObjectType).where(ControlObjectType.code == "land_plot")
        )
        control_object = db.scalar(
            select(ControlObject).where(ControlObject.address_id == address_object.id)
        )
        if control_object is None:
            control_object = ControlObject(
                object_type_id=object_type.id,
                # Формулировки для бланков: именительный и родительный падеж.
                name=(
                    "земельный участок, расположенный по адресу: "
                    "г. Липецк, ул. Теперика, д.3"
                ),
                name_genitive=(
                    "Земельного участка, расположенного по адресу: "
                    "г. Липецк, ул. Теперика, д.3"
                ),
                address_id=address_object.id,
                operating_organization_id=organization.id,
                attributes={"работы": "аварийному ремонту теплоснабжения"},
            )
            db.add(control_object)
            db.flush()

        status = db.scalar(
            select(ControlCaseStatus).where(ControlCaseStatus.code == "completed")
        )
        kind = db.scalar(
            select(ControlKind).where(ControlKind.code == "municipal_improvement")
        )
        form = db.scalar(
            select(ControlForm).where(ControlForm.code == "field_survey")
        )

        case = ControlCase(
            control_kind_id=kind.id,
            control_form_id=form.id,
            control_body_id=body.id,
            controlled_organization_id=organization.id,
            controlled_unit_id=unit.id,
            control_object_id=control_object.id,
            # Ответственный за устранение выбирается вручную; в примере это
            # то же лицо, что и контролируемое.
            responsible_organization_id=organization.id,
            responsible_unit_id=unit.id,
            purpose=(
                "Оценка соблюдения контролируемым лицом обязательных требований "
                "действующего законодательства, проверка фактов, изложенных в "
                "материале МУ «Управление главного смотрителя г. Липецка» "
                "№ 7975-39-01-10 от 15.09.2026"
            ),
            subject="Соблюдение обязательных требований действующего законодательства",
            status_id=status.id if status else None,
            result="violations_found",
            planned_start_at=datetime(2026, 9, 22, 8, 30, tzinfo=MSK),
            planned_end_at=datetime(2026, 9, 22, 17, 30, tzinfo=MSK),
            actual_start_at=datetime(2026, 9, 22, 8, 30, tzinfo=MSK),
            actual_end_at=datetime(2026, 9, 22, 13, 0, tzinfo=MSK),
            # Обследование закончено в 13:00, акт составлен в 17:00 —
            # это разные моменты, поэтому поле отдельное.
            act_composed_at=datetime(2026, 9, 22, 17, 0, tzinfo=MSK),
            erp_number=ERP_NUMBER,
            erp_code=ERP_NUMBER,
            erp_url=(
                "https://proverki.gov.ru/portal/public-search?erp=" + ERP_NUMBER
            ),
            assignment_number="б/н",
            assignment_date=datetime(2026, 9, 21, 0, 0, tzinfo=MSK),
            assignment_approved_by_signatory_id=approver.id,
        )
        db.add(case)
        db.flush()

        db.add(
            ControlCaseInspector(
                control_case_id=case.id,
                inspector_id=inspector.id,
                role=InspectorRole.LEADER,
            )
        )
        db.add(
            ControlCaseBase(
                control_case_id=case.id,
                kind=CaseBaseKind.MU_MATERIAL,
                document_number="7975-39-01-10",
                document_date=datetime(2026, 9, 15, 0, 0, tzinfo=MSK),
                description=(
                    "МУ «Управление главного смотрителя г. Липецка»"
                ),
            )
        )

        action = ControlAction(
            control_case_id=case.id,
            sequence_no=1,
            action_type=ControlActionType.INSPECTION,
            started_at=datetime(2026, 9, 22, 12, 20, tzinfo=MSK),
            ended_at=datetime(2026, 9, 22, 12, 45, tzinfo=MSK),
            place_address_id=address_object.id,
            result_text=(
                "Выездное обследование проведено, по результатам составлен "
                "протокол осмотра"
            ),
            is_violation_found=True,
        )
        db.add(action)
        db.flush()

        # Фотоматериал к протоколу осмотра: снимок с датой, временем и местом
        # съёмки. Именно он печатается приложением к протоколу.
        if DEMO_PHOTO.exists():
            photo = storage.save_bytes(
                db,
                DEMO_PHOTO.read_bytes(),
                DEMO_PHOTO.name,
                kind=FileKind.PHOTO,
                captured_at=datetime(2026, 9, 22, 12, 30, tzinfo=MSK),
                commit=False,
            )
            photo.caption = "Общий вид участка после земляных работ"
            photo.address_id = address_object.id
            db.add(
                ControlActionFile(
                    control_action_id=action.id,
                    file_id=photo.id,
                    caption="Общий вид участка после земляных работ",
                    sequence_no=1,
                )
            )
            db.flush()
        else:
            print(f"нет файла снимка {DEMO_PHOTO} — протокол будет без фотоматериала")

        violation_type = db.scalar(
            select(ViolationType).where(
                ViolationType.code == "unrestored_improvement"
            )
        )
        violation = Violation(
            control_case_id=case.id,
            control_action_id=action.id,
            violation_type_id=violation_type.id if violation_type else None,
            description=(
                "На земельном участке, расположенном по адресу: г. Липецк, "
                "ул. Теперика, д.3, не восстановлено нарушенное благоустройство "
                "в полном объёме после производства земляных работ, а именно: "
                "асфальт – 4 кв.м., грунт – 20 кв.м., дорожный бордюр – 4 шт."
            ),
            detected_at=datetime(2026, 9, 22, 12, 30, tzinfo=MSK),
            address_id=address_object.id,
        )
        db.add(violation)
        db.flush()

        for template in (
            "пункт 5.2 части 5 статьи 5",
            "часть 7 статьи 14",
            "часть 12 статьи 14",
        ):
            article = db.scalar(
                select(NpaArticle).where(
                    NpaArticle.reference_template == template,
                    NpaArticle.valid_to.is_(None),
                )
            )
            if article is not None:
                db.add(
                    ViolationProvision(
                        violation_id=violation.id,
                        npa_article_id=article.id,
                    )
                )

        decision = Decision(
            control_case_id=case.id,
            number=ERP_NUMBER,
            decision_date=date(2026, 9, 22),
            decision_kind="по результатам контрольного мероприятия",
            content=(
                "По результатам проведённого выездного обследования принято "
                "решение: выдать предписание об устранении нарушений."
            ),
            approved_by_signatory_id=approver.id,
            prepared_by_inspector_id=inspector.id,
        )
        db.add(decision)
        db.flush()
        db.add(
            DecisionItem(
                decision_id=decision.id,
                sequence_no=1,
                kind=DecisionItemKind.ISSUE_PRESCRIPTION,
                description="выдать предписание об устранении нарушений",
            )
        )

        prescription_status = db.scalar(
            select(PrescriptionStatus).where(PrescriptionStatus.code == "primary")
        )
        prescription = Prescription(
            control_case_id=case.id,
            number=ERP_NUMBER,
            issued_on=date(2026, 9, 22),
            due_on=date(2026, 10, 5),
            status_id=prescription_status.id if prescription_status else None,
        )
        db.add(prescription)
        db.flush()
        db.add(
            PrescriptionItem(
                prescription_id=prescription.id,
                sequence_no=1,
                requirement_text=(
                    "В целях соблюдения требований действующего законодательства, "
                    "а именно: в соответствии с пунктом 5.2. части 5 статьи 5, "
                    "частями 7 и 12 статьи 14 Правил благоустройства территорий "
                    "города Липецка, утверждённых решением Липецкого городского "
                    "Совета депутатов от 28.11.2024 №836, обеспечить восстановление "
                    "нарушенного благоустройства в полном объёме после производства "
                    "земляных работ по адресу: г. Липецк, ул. Теперика, д.3, "
                    "а именно: восстановить асфальт – 4 кв.м., грунт – 20 кв.м., "
                    "дорожный бордюр – 4 шт."
                ),
                due_on=date(2026, 10, 5),
            )
        )

        db.commit()
        print(f"создано дело id={case.id}, предписание id={prescription.id}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
