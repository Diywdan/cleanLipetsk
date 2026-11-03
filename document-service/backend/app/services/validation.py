"""Проверка готовности дела к формированию пакета документов.

Официальный документ с пустым полем хуже, чем несформированный пакет,
поэтому перед сборкой проверяется, что все значения, которые шаблоны
подставляют, действительно заполнены. Проверка идёт по требованиям
шаблонов: если поле не заполнено, документ напечатает пустое место.
"""

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AdministrativeCase,
    ControlAction,
    ControlCase,
    ControlCaseBase,
    ControlCaseInspector,
    Decision,
    DocumentTemplate,
    DocumentType,
    OrganizationContact,
    OrganizationRequisite,
    PackageKind,
    PackageKindDocument,
    Prescription,
    Violation,
)
from app.models.enums import ContactKind, InspectionKind
from app.services.snapshots import _current_requisites


@dataclass
class Issue:
    """Что мешает собрать документ."""

    document: str | None
    field: str
    message: str


@dataclass
class Readiness:
    case_id: int
    package_kind: str
    documents: list[str] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)
    # Замечания, которые не мешают собрать пакет: например, ещё нет номера из
    # реестра контрольных мероприятий (его присваивает портал прокуратуры).
    # Документы в этом случае печатаются с пустым номером, а пакет
    # пересобирают, когда номер появится.
    warnings: list[Issue] = field(default_factory=list)
    missing_templates: list[str] = field(default_factory=list)

    @property
    def is_ready(self) -> bool:
        return not self.issues and not self.missing_templates

    def as_dict(self) -> dict:
        return {
            "case_id": self.case_id,
            "package_kind": self.package_kind,
            "documents": self.documents,
            "is_ready": self.is_ready,
            "issues": [
                {
                    "document": issue.document,
                    "field": issue.field,
                    "message": issue.message,
                }
                for issue in self.issues
            ],
            "warnings": [
                {
                    "document": issue.document,
                    "field": issue.field,
                    "message": issue.message,
                }
                for issue in self.warnings
            ],
            "missing_templates": self.missing_templates,
        }


def _require(
    readiness: Readiness,
    condition: bool,
    document: str | None,
    field_name: str,
    message: str,
) -> None:
    if not condition:
        readiness.issues.append(
            Issue(document=document, field=field_name, message=message)
        )


def _warn(
    readiness: Readiness,
    condition: bool,
    document: str | None,
    field_name: str,
    message: str,
) -> None:
    """Замечание, которое не мешает собрать пакет."""

    if not condition:
        readiness.warnings.append(
            Issue(document=document, field=field_name, message=message)
        )


def _inspection_for_package(
    db: Session,
    case_id: int,
    package_kind_code: str,
    actions: list[ControlAction],
) -> ControlAction | None:
    """Осмотр, по которому собирается пакет: первичный или последний.

    Правило то же, что и при сборке документов: первый пакет описывает
    первичный осмотр, вторичный и пакет об исполнении — последний.
    """

    if package_kind_code == "primary_prescription":
        for action in actions:
            if action.inspection_kind == InspectionKind.PRIMARY:
                return action
    return actions[-1] if actions else None


def check_readiness(
    db: Session,
    case_id: int,
    package_kind_code: str,
    only_codes: list[str] | None = None,
) -> Readiness:
    case = db.get(ControlCase, case_id)
    if case is None:
        raise ValueError(f"дело {case_id} не найдено")

    package_kind = db.scalar(
        select(PackageKind).where(PackageKind.code == package_kind_code)
    )
    if package_kind is None:
        raise ValueError(f"вид пакета {package_kind_code!r} не найден")

    package_composition = list(
        db.scalars(
            select(PackageKindDocument)
            .where(PackageKindDocument.package_kind_id == package_kind.id)
            .order_by(PackageKindDocument.sequence_no)
        )
    )
    if only_codes:
        available_codes = {item.document_type.code for item in package_composition}
        unknown_codes = sorted(set(only_codes) - available_codes)
        if unknown_codes:
            raise ValueError(
                f"документы не входят в пакет {package_kind_code}: {', '.join(unknown_codes)}"
            )
        composition = [
            item for item in package_composition
            if item.document_type.code in set(only_codes)
        ]
    else:
        composition = package_composition
    codes = [item.document_type.code for item in composition]
    readiness = Readiness(
        case_id=case_id, package_kind=package_kind_code, documents=codes
    )

    # Есть ли вообще шаблоны для этих документов.
    for item in composition:
        template = db.scalar(
            select(DocumentTemplate).where(
                DocumentTemplate.document_type_id == item.document_type_id,
                DocumentTemplate.is_active.is_(True),
            )
        )
        if template is None or template.file is None:
            readiness.missing_templates.append(item.document_type.code)

    # --- Общие данные дела -------------------------------------------------
    _require(readiness, case.control_kind_id is not None, None,
             "control_kind", "не указан вид муниципального контроля")
    _require(readiness, case.control_form_id is not None, None,
             "control_form", "не указана форма контрольного мероприятия")
    _require(readiness, case.control_body_id is not None, None,
             "control_body", "не указан орган контроля")
    _require(readiness, case.controlled_organization_id is not None, None,
             "controlled_organization", "не указано контролируемое лицо")
    _require(readiness, case.control_object_id is not None, None,
             "control_object", "не указан объект контроля")
    _require(readiness, case.assignment_approved_by_signatory_id is not None, None,
             "approver", "не указано лицо, утверждающее задание и решение")
    _require(readiness, case.assignment_date is not None, None,
             "assignment_date", "не указана дата задания")
    _require(readiness, case.planned_start_at is not None, None,
             "planned_start_at", "не указано планируемое начало мероприятия")
    _require(readiness, case.planned_end_at is not None, None,
             "planned_end_at", "не указано планируемое окончание мероприятия")
    _require(readiness, case.actual_start_at is not None, None,
             "actual_start_at", "не указано фактическое начало мероприятия")
    _require(readiness, case.actual_end_at is not None, None,
             "actual_end_at", "не указано фактическое окончание мероприятия")
    if "act" in codes:
        _require(readiness, case.act_composed_at is not None, "act",
                 "act_composed_at", "не указаны дата и время составления акта")
    # Номер из реестра контрольных мероприятий присваивает портал
    # прокуратуры, и он появляется не сразу. Пакет собирается и без него:
    # в бланке остаётся пустое место, а пакет пересобирают, когда номер
    # появится. Поэтому это замечание, а не запрет.
    _warn(readiness, case.erp_number is not None, None,
          "erp_number", "номер из реестра контрольных мероприятий ещё не указан — "
          "документы напечатаются с пустым номером, пакет можно пересобрать позже")

    bases = list(
        db.scalars(
            select(ControlCaseBase).where(ControlCaseBase.control_case_id == case_id)
        )
    )
    _require(readiness, bool(bases), "assignment", "bases",
             "не указано основание проведения мероприятия")

    # --- Инспекторы --------------------------------------------------------
    links = list(
        db.scalars(
            select(ControlCaseInspector).where(
                ControlCaseInspector.control_case_id == case_id
            )
        )
    )
    inspectors = [link.inspector for link in links if link.inspector is not None]
    inspector_document = (
        "assignment" if "assignment" in codes
        else "decision" if "decision" in codes
        else "act"
    )
    if (
        "assignment" in codes
        or "decision" in codes
        or "act" in codes
        or "inspection_protocol" in codes
    ):
        _require(readiness, bool(inspectors), inspector_document, "inspectors",
                 "не указаны инспекторы, проводившие мероприятие")
    for inspector in inspectors:
        if "assignment" in codes or "act" in codes or "inspection_protocol" in codes:
            _require(readiness, bool(inspector.phone), inspector_document,
                     f"inspector.{inspector.id}.phone",
                     f"у инспектора {inspector.full_name} не указан телефон")
            _require(readiness, bool(inspector.email), inspector_document,
                     f"inspector.{inspector.id}.email",
                     f"у инспектора {inspector.full_name} не указана почта")
        if "inspection_protocol" in codes:
            _require(readiness, bool(inspector.position_instrumental),
                     "inspection_protocol",
                     f"inspector.{inspector.id}.position_instrumental",
                     f"у инспектора {inspector.full_name} не заполнена "
                     "должность в творительном падеже (для протокола осмотра)")
            _require(readiness, bool(inspector.full_name_instrumental),
                     "inspection_protocol",
                     f"inspector.{inspector.id}.full_name_instrumental",
                     f"у инспектора {inspector.full_name} не заполнено ФИО "
                     "в творительном падеже (для протокола осмотра)")

    # --- Контролируемое лицо: реквизиты и контакты -------------------------
    organization = case.controlled_organization
    unit = case.controlled_unit
    requisite_document = (
        "assignment" if "assignment" in codes
        else "decision" if "decision" in codes
        else "act"
    )
    if (
        "assignment" in codes
        or "decision" in codes
        or "act" in codes
        or "inspection_protocol" in codes
        or "direction" in codes
    ) and organization is not None:
        unit_id = unit.id if unit is not None else None
        requisites = _current_requisites(db, organization.id, unit_id)
        _require(readiness, requisites is not None,
                 requisite_document, "requisites",
                 "у контролируемого лица не заполнены реквизиты")
        if requisites is not None:
            _require(readiness, bool(requisites.inn or organization.inn), requisite_document,
                     "requisites.inn", "у контролируемого лица не указан ИНН")
            _require(readiness, requisites.legal_address_id is not None,
                     requisite_document, "requisites.legal_address",
                     "у контролируемого лица не указан юридический адрес")
    if (
        "act" in codes
        or "inspection_protocol" in codes
        or "direction" in codes
    ) and organization is not None:
        contacts = list(
            db.scalars(
                select(OrganizationContact).where(
                    OrganizationContact.organization_id == organization.id,
                    OrganizationContact.kind == ContactKind.EMAIL,
                    OrganizationContact.is_active.is_(True),
                )
            )
        )
        _require(readiness, bool(contacts), "act", "contacts",
                 "у контролируемого лица не указана электронная почта")

        # Филиал печатается в бланках направления отдельным получателем.
        # Если он указан, у него обязаны быть и название, и своя почта:
        # блок напечатается целиком, а пустое место в нём недопустимо.
        if unit is not None:
            _require(readiness, bool(unit.name), "direction", "unit.name",
                     "у филиала контролируемого лица не указано название")
            unit_contacts = list(
                db.scalars(
                    select(OrganizationContact).where(
                        OrganizationContact.organization_id == organization.id,
                        OrganizationContact.unit_id == unit.id,
                        OrganizationContact.kind == ContactKind.EMAIL,
                        OrganizationContact.is_active.is_(True),
                    )
                )
            )
            _require(readiness, bool(unit_contacts), "direction", "unit.email",
                     "у филиала контролируемого лица не указана электронная почта")

    # --- Объект контроля ---------------------------------------------------
    if case.control_object is not None:
        object_document = "act" if "act" in codes else (codes[0] if codes else None)
        _require(readiness, bool(case.control_object.name), object_document,
                 "control_object.name", "у объекта контроля не заполнено описание")
        _require(readiness, bool(case.control_object.address_id), object_document,
                 "control_object.address", "у объекта контроля не указан адрес")

    # --- Контрольные действия ---------------------------------------------
    # Проверяется осмотр, по которому собирается пакет, а не все действия
    # дела: незаполненный повторный осмотр не должен мешать собрать первый
    # пакет, а осмотр, по которому пакет собирается, обязан быть заполнен.
    actions = list(
        db.scalars(
            select(ControlAction)
            .where(ControlAction.control_case_id == case_id)
            .order_by(ControlAction.sequence_no)
        )
    )
    _require(readiness, bool(actions), "act", "actions",
             "не указаны контрольные действия")

    inspection = _inspection_for_package(db, case_id, package_kind_code, actions)
    checked = [inspection] if inspection is not None else []
    for action in checked:
        _require(readiness, action.started_at is not None, "act",
                 f"action.{action.id}.started_at",
                 "у осмотра не указано начало")
        _require(readiness, action.ended_at is not None, "act",
                 f"action.{action.id}.ended_at",
                 "у осмотра не указано окончание")
        if "act" in codes or "inspection_protocol" in codes:
            _require(readiness, action.place_address_id is not None, "act",
                     f"action.{action.id}.place",
                     "у осмотра не указано место проведения")

    # --- Нарушения ---------------------------------------------------------
    violations = list(
        db.scalars(select(Violation).where(Violation.control_case_id == case_id))
    )
    if "inspection_protocol" in codes or "prescription" in codes:
        _require(readiness, bool(violations), "inspection_protocol",
                 "violations", "не указано выявленное нарушение")
    if "inspection_protocol" in codes or "prescription" in codes:
        for violation in violations:
            _require(readiness, bool(violation.description), "inspection_protocol",
                     f"violation.{violation.id}.description",
                     "у нарушения не заполнено описание")
            _require(readiness, bool(violation.provisions), "inspection_protocol",
                     f"violation.{violation.id}.provisions",
                     "у нарушения не указаны статьи нормативных актов")

    # --- Решение и предписание --------------------------------------------
    if "decision" in codes:
        decision = db.scalar(
            select(Decision).where(Decision.control_case_id == case_id)
        )
        _require(readiness, decision is not None, "decision", "decision",
                 "не заполнено решение по результатам мероприятия")
        if decision is not None:
            _require(readiness, decision.decision_date is not None, "decision",
                     "decision.decision_date", "у решения не указана дата")
            _require(readiness, bool(decision.items), "decision",
                     "decision.items", "у решения не указаны пункты")

    if "prescription" in codes:
        prescription = db.scalar(
            select(Prescription).where(Prescription.control_case_id == case_id)
        )
        _require(readiness, prescription is not None, "prescription",
                 "prescription", "не заполнено предписание")
        if prescription is not None:
            _require(readiness, bool(prescription.number), "prescription",
                     "prescription.number", "у предписания не указан номер")
            _require(readiness, prescription.issued_on is not None, "prescription",
                     "prescription.issued_on", "у предписания не указана дата")
            _require(readiness, prescription.due_on is not None, "prescription",
                     "prescription.due_on",
                     "у предписания не указан срок исполнения")
            _require(readiness, bool(prescription.items), "prescription",
                     "prescription.items",
                     "у предписания не указаны требования")

    # --- Административное производство -------------------------------------
    # Уведомление о явке и протокол об административном правонарушении
    # входят только во вторичный пакет, поэтому и проверяются только для него.
    if "appearance_notice" in codes or "administrative_protocol" in codes:
        administrative = db.scalars(
            select(AdministrativeCase).where(
                AdministrativeCase.control_case_id == case_id
            )
        ).first()
        _require(
            readiness,
            administrative is not None,
            "administrative_protocol",
            "administrative",
            "не заполнены данные административного производства",
        )
        if administrative is not None:
            checks = [
                ("protocol_number", "не указан номер протокола", "administrative_protocol"),

                ("appearance_date", "не указана дата явки для составления протокола", "appearance_notice"),
                ("appearance_time", "не указано время явки", "appearance_notice"),
                ("offense_article", "не указана статья КоАП", "administrative_protocol"),
            ]
            for field_name, message, document in checks:
                _require(
                    readiness,
                    bool(getattr(administrative, field_name)),
                    document,
                    f"administrative.{field_name}",
                    message,
                )
            # Дата протокола и место составления подставляются сами: дата — из
            # повторного осмотра, место — из адреса управы (или департамента).
            # Поэтому это замечания, а не запрет.
            _warn(
                readiness,
                administrative.protocol_date is not None,
                "administrative_protocol",
                "administrative.protocol_date",
                "дата протокола не заполнена — подставится дата повторного осмотра",
            )
            _warn(
                readiness,
                administrative.protocol_place is not None,
                "administrative_protocol",
                "administrative.protocol_place",
                "место составления протокола не выбрано — подставится адрес управы",
            )
            # Ранее выданное предписание: если этих полей нет, для протокола
            # берётся предписание самой заявки — протокол по ст. 19.5 описывает
            # именно его неисполнение. Поэтому это замечание, а не запрет.
            _warn(
                readiness,
                bool(administrative.prior_prescription_number),
                "administrative_protocol",
                "administrative.prior_prescription_number",
                "номер ранее выданного предписания не заполнен — подставится "
                "номер предписания этой заявки",
            )

    return readiness
