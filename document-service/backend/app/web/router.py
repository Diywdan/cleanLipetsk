"""Минимальная CRM: заявки, справочники и формирование пакета документов.

Страницы отдаются сервером (Jinja2) без сборки фронтенда: на этом сервере
нет Node, а оператору нужен работающий список заявок и контекстные действия,
а не одностраничное приложение.
"""

from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from io import BytesIO
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from PIL import Image
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db.dependencies import get_db
from app.models import (
    Address,
    Area,
    AdministrativeCase,
    ControlAction,
    ControlBody,
    ControlBodySignatory,
    ControlCase,
    ControlCaseBase,
    ControlCaseInspector,
    ControlCaseStatus,
    ControlForm,
    ControlKind,
    CaseTextOption,
    ControlObject,
    ControlObjectType,
    Decision,
    DecisionItem,
    Document,
    DocumentPackage,
    Inspector,
    NpaArticle,
    Organization,
    OrganizationContact,
    OrganizationRequisite,
    OrganizationRole,
    OrganizationSignatory,
    OrganizationUnit,
    PackageKind,
    Prescription,
    PrescriptionItem,
    PrescriptionStatus,
    User,
    Violation,
    ViolationProvision,
    ViolationType,
    ViolationTypeArticle,
    ViolationTypeWork,
    ViolationWork,
    Work,
)
from app.models.enums import (
    CaseBaseKind,
    ContactKind,
    ContactPurpose,
    ControlActionType,
    DecisionItemKind,
    FileKind,
    InspectionResult,
    InspectorRole,
    OrganizationKind,
    OrganizationRoleCode,
    OrganizationUnitKind,
    SignatoryBasisKind,
)
from app.services import archive, audit, crm_events, generation, storage, validation
from app.services import violation_text, violations
from app.services import geocoding
from app.services import addresses as address_service
from app.services import areas
from app.services import dictionaries as dictionary_service
from app.services import dictionary_admin
from app.services import auth
from app.services import case_state
from app.services import inspections as inspections_service
from app.services import labels
from app.services import numbers
from app.services import ru
from app.web import forms
from app.web.templating import templates


router = APIRouter(prefix="/ui", tags=["ui"])


def _actor(request: Request) -> User | None:
    """Кто выполняет действие — для журнала."""

    return getattr(request.state, "user", None)


def _log_dictionary(
    db: Session,
    request: Request,
    entity_table: str,
    comment: str,
    entity_id: int | None = None,
) -> None:
    """Запись в журнал об изменении справочника."""

    audit.record(
        db,
        actor=_actor(request),
        entity_table=entity_table,
        entity_id=entity_id,
        action="create",
        comment=comment,
    )


def _documents(db: Session, case_id: int) -> list[Document]:
    return list(
        db.scalars(
            select(Document)
            .join(DocumentPackage, Document.package_id == DocumentPackage.id)
            .where(DocumentPackage.control_case_id == case_id)
            .order_by(Document.id.desc())
        )
    )


def _last_package(db: Session, case_id: int) -> DocumentPackage | None:
    return db.scalars(
        select(DocumentPackage)
        .where(DocumentPackage.control_case_id == case_id)
        .order_by(DocumentPackage.id.desc())
    ).first()


def _responsible_organizations(db: Session) -> list[Organization]:
    """Организации, из которых выбирают ответственного за исполнение.

    В список попадают только действующие: архивные значения остаются в уже
    созданных заявках, но новых ссылок не получают.
    """

    return list(
        db.scalars(
            select(Organization)
            .where(Organization.is_active.is_(True))
            .order_by(Organization.short_name)
        )
    )


def _case_text_options(db: Session, kind: str) -> list:
    """Готовые формулировки цели или предмета заявки."""

    return list(
        db.scalars(
            select(CaseTextOption)
            .where(CaseTextOption.kind == kind, CaseTextOption.is_active.is_(True))
            .order_by(CaseTextOption.sort_order, CaseTextOption.id)
        )
    )


def _case_text_default(db: Session, kind: str) -> str | None:
    """Первая формулировка списка — её и подставляем в новую заявку."""

    options = _case_text_options(db, kind)
    return options[0].value if options else None


def _article_kinds(db: Session) -> dict[int, list[int]]:
    """Какие виды нарушений ссылаются на каждую норму."""

    result: dict[int, list[int]] = {}
    for link in db.scalars(select(ViolationTypeArticle)):
        result.setdefault(link.npa_article_id, []).append(link.violation_type_id)
    return result


def _work_kinds(db: Session) -> dict[int, list[int]]:
    """Какие виды нарушений ссылаются на каждую работу.

    По этой карте поле работ показывает короткий список для выбранного вида
    нарушения: у асфальта, грунта и бордюра свои виды, у уборки — свои.
    """

    result: dict[int, list[int]] = {}
    for link in db.scalars(select(ViolationTypeWork)):
        result.setdefault(link.work_id, []).append(link.violation_type_id)
    return result


def _requirement_text(violation, prescription) -> str | None:
    """Требование предписания из данных — то же, что попадёт в документ."""

    return violations.requirement_for(violation, prescription)


def _document_groups(db: Session, case: ControlCase) -> list[dict]:
    """Пакеты заявки по видам — только те, что возможны по её состоянию.

    Одним списком документы показывать нельзя: после пересборок в нём
    оказываются документы разных пакетов, и непонятно, что скачивать.
    Поэтому документы сгруппированы по видам пакетов, и показываются те
    виды, которые следуют из состояния заявки: пока сделан только первичный
    осмотр, в списке одно первичное предписание — остальные виды были бы
    предложением скачать то, чего по этой заявке быть не может.
    """

    available_codes = {
        item["kind"].code for item in _available_packages(db, case)
    }
    kinds = [
        kind
        for kind in db.scalars(
            select(PackageKind).order_by(PackageKind.sort_order, PackageKind.id)
        )
        if kind.code in available_codes
    ]
    packages = list(
        db.scalars(
            select(DocumentPackage)
            .where(DocumentPackage.control_case_id == case.id)
            .order_by(DocumentPackage.id.desc())
        )
    )
    latest: dict[int, DocumentPackage] = {}
    for package in packages:
        latest.setdefault(package.package_kind_id, package)

    groups: list[dict] = []
    for kind in kinds:
        package = latest.get(kind.id)
        documents = (
            list(
                db.scalars(
                    select(Document)
                    .where(Document.package_id == package.id)
                    # Документы собираются в порядке состава пакета,
                    # поэтому порядок создания и есть порядок в пакете.
                    .order_by(Document.id)
                )
            )
            if package is not None
            else []
        )
        groups.append({"kind": kind, "package": package, "documents": documents})
    return groups


def _text(form, name: str) -> str | None:
    return forms.clean(form.get(name))


@router.get("", response_class=HTMLResponse)
def cases_page(
    request: Request,
    db: Session = Depends(get_db),
    ok: str | None = None,
    err: str | None = None,
) -> HTMLResponse:
    statement = select(ControlCase).order_by(ControlCase.id.desc()).limit(200)
    # Если включено ограничение по управам, инспектор видит только заявки
    # по адресам своей управы.
    statement = areas.visible_cases_statement(
        db, getattr(request.state, "user", None), statement
    )
    cases = list(db.scalars(statement))
    rows = []
    today = ru.to_display(datetime.now(timezone.utc))
    for case in cases:
        due_on = case_state.control_due_on(db, case)
        rows.append(
            {
                "case": case,
                "documents": len(_documents(db, case.id)),
                # Состояние выводится из данных заявки, а не хранится полем.
                "state": case_state.state_title(db, case),
                "control_due_on": ru.date_short(due_on) if due_on else None,
                # Просроченную дату контроля видно в списке сразу.
                "overdue": bool(due_on and due_on < today.date()),
                "areas": [area.name for area in areas.case_areas(db, case)],
                "controlled": (
                    case.controlled_organization.short_name
                    if case.controlled_organization
                    else None
                ),
                "responsible": (
                    case.responsible_organization.short_name
                    if case.responsible_organization
                    else None
                ),
            }
        )
    return templates.TemplateResponse(
        request,
        "cases.html",
        {"rows": rows, "ok": ok, "err": err},
    )


@router.get("/cases/new", response_class=HTMLResponse)
def new_case_page(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    # Новая заявка заполняется по минимуму: что случилось, вид нарушения и
    # адрес. Остальное спросится позже — при подготовке документов.
    return _case_form(
        request, db, case=None, source=None, template="case_min.html"
    )


@router.get("/cases/{case_id}/copy", response_class=HTMLResponse)
def copy_case_page(
    request: Request, case_id: int, db: Session = Depends(get_db)
) -> HTMLResponse:
    case = db.get(ControlCase, case_id)
    if case is None:
        return RedirectResponse("/ui?err=Дело не найдено", status_code=303)
    return _case_form(request, db, case=None, source=case)


def _case_form(
    request: Request,
    db: Session,
    case: ControlCase | None,
    source: ControlCase | None,
    template: str = "case_form.html",
) -> HTMLResponse:
    """Форма создания заявки: пустая или заполненная данными другой заявки."""

    base = source or case
    action = None
    violation = None
    prescription = None
    decision = None
    basis = None
    inspector_link = None
    if base is not None:
        action = db.scalars(
            select(ControlAction)
            .where(ControlAction.control_case_id == base.id)
            .order_by(ControlAction.sequence_no)
        ).first()
        violation = db.scalars(
            select(Violation).where(Violation.control_case_id == base.id)
        ).first()
        prescription = db.scalars(
            select(Prescription).where(Prescription.control_case_id == base.id)
        ).first()
        decision = db.scalars(
            select(Decision).where(Decision.control_case_id == base.id)
        ).first()
        basis = db.scalars(
            select(ControlCaseBase).where(ControlCaseBase.control_case_id == base.id)
        ).first()
        inspector_link = db.scalars(
            select(ControlCaseInspector).where(
                ControlCaseInspector.control_case_id == base.id
            )
        ).first()

    prescription_item = None
    if prescription is not None:
        prescription_item = prescription.items[0] if prescription.items else None

    context = {
        "case": base,
        "is_copy": source is not None,
        "is_edit": source is None and case is not None,
        "control_kinds": list(db.scalars(select(ControlKind).order_by(ControlKind.name))),
        "control_forms": list(
            db.scalars(select(ControlForm).order_by(ControlForm.sort_order))
        ),
        "control_bodies": list(
            db.scalars(select(ControlBody).order_by(ControlBody.name))
        ),
        # В списки для выбора попадают только действующие значения: архивные
        # остаются в уже созданных заявках, но новых ссылок не получают.
        "organizations": list(
            db.scalars(
                select(Organization)
                .where(Organization.is_active.is_(True))
                .order_by(Organization.short_name)
            )
        ),
        "units": list(
            db.scalars(
                select(OrganizationUnit)
                .where(OrganizationUnit.is_active.is_(True))
                .order_by(OrganizationUnit.name)
            )
        ),
        "objects": list(
            db.scalars(
                select(ControlObject)
                .where(ControlObject.is_active.is_(True))
                .order_by(ControlObject.name)
            )
        ),
        "object_types": list(
            db.scalars(select(ControlObjectType).order_by(ControlObjectType.sort_order))
        ),
        "addresses": list(
            db.scalars(select(Address).order_by(Address.id.desc()).limit(200))
        ),
        # Подсказки при вводе адреса: последние введённые адреса.
        "address_options": address_service.suggestions(db, None, 50),
        "signatories": list(
            db.scalars(
                select(ControlBodySignatory)
                .where(
                    or_(
                        ControlBodySignatory.valid_to.is_(None),
                        ControlBodySignatory.valid_to >= date.today(),
                    )
                )
                .order_by(ControlBodySignatory.full_name)
            )
        ),
        "inspectors": list(
            db.scalars(
                select(Inspector)
                .where(Inspector.is_active.is_(True))
                .order_by(Inspector.full_name)
            )
        ),
        "violation_types": list(
            db.scalars(select(ViolationType).order_by(ViolationType.sort_order))
        ),
        # Цель и предмет выбираются из справочника: это длинные юридические
        # фразы. В новой заявке подставляется первое значение списка.
        "purposes": _case_text_options(db, "purpose"),
        "subjects": _case_text_options(db, "subject"),
        "default_purpose": _case_text_default(db, "purpose"),
        "default_subject": _case_text_default(db, "subject"),
        "articles": list(
            db.scalars(select(NpaArticle).order_by(NpaArticle.id))
        ),
        # Нормы, привязанные к видам нарушений. По этой карте поле
        # квалификации показывает короткий список для выбранного вида
        # нарушения, а «показать все нормы» возвращает справочник целиком:
        # непривязанную норму тоже должно быть можно выбрать.
        "article_kinds": _article_kinds(db),
        # Работы по нарушению: справочник и уже введённые строки. Описание
        # нарушения и требование предписания собираются из них.
        "works": list(
            db.scalars(
                select(Work)
                .where(Work.is_active.is_(True))
                .order_by(Work.sort_order, Work.name)
            )
        ),
        "work_kinds": _work_kinds(db),
        "violation_works": (
            [
                {
                    "work_id": item.work_id,
                    "quantity": (
                        float(item.quantity) if item.quantity is not None else ""
                    ),
                }
                for item in violation.works
            ]
            if violation is not None
            else []
        ),
        "work_actions": labels.options(
            list(violation_text.ACTIONS.keys()),
            {code: title for code, title in violation_text.ACTIONS.items()},
        ),
        "statuses": list(
            db.scalars(select(ControlCaseStatus).order_by(ControlCaseStatus.sort_order))
        ),
        "prescription_statuses": list(
            db.scalars(select(PrescriptionStatus).order_by(PrescriptionStatus.id))
        ),
        "basis_kinds": labels.options(
            [kind.value for kind in CaseBaseKind], labels.BASIS_KIND_TITLES
        ),
        "action_types": labels.options(
            [item.value for item in ControlActionType], labels.ACTION_TYPE_TITLES
        ),
        "action": action,
        "violation": violation,
        "violation_provisions": (
            [item.npa_article_id for item in violation.provisions]
            if violation is not None
            else []
        ),
        "prescription": prescription,
        "prescription_item": prescription_item,
        "decision": decision,
        "decision_item": (
            decision.items[0] if decision is not None and decision.items else None
        ),
        "basis": basis,
        "inspector_id": inspector_link.inspector_id if inspector_link else None,
    }
    return templates.TemplateResponse(request, template, context)


@router.post("/cases")
async def create_case(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    case = ControlCase()
    db.add(case)
    _apply_case_fields(case, form)
    # Внутренний номер заявки присваивает система: он сквозной для всех
    # пользователей, и вручную его не меняют.
    number = numbers.assign_case_number(db, case)
    # Цель и предмет — из справочника: в новой заявке подставляем первое
    # значение, если оператор ничего не выбрал.
    if not case.purpose:
        case.purpose = _case_text_default(db, "purpose")
    if not case.subject:
        case.subject = _case_text_default(db, "subject")
    db.flush()

    _save_nested(db, case, form)
    # Координаты адреса для карты — в фоне, чтобы не задерживать сохранение
    geocoding.schedule_for_case(case)
    audit.record(
        db,
        actor=_actor(request),
        entity_table="control_cases",
        entity_id=case.id,
        action="create",
        comment=f"создана заявка №{number}, мероприятие {case.erp_number or '—'}",
    )
    db.commit()
    return RedirectResponse(f"/ui/cases/{case.id}?ok=Заявка создана", status_code=303)


@router.get("/cases/{case_id}/edit", response_class=HTMLResponse)
def edit_case_page(
    request: Request, case_id: int, db: Session = Depends(get_db)
) -> HTMLResponse:
    case = db.get(ControlCase, case_id)
    if case is None:
        return RedirectResponse("/ui?err=Дело не найдено", status_code=303)
    return _case_form(request, db, case=case, source=None)


@router.post("/cases/{case_id}")
async def update_case(
    request: Request, case_id: int, db: Session = Depends(get_db)
):
    """Сохранение изменений уже созданной заявки."""

    case = db.get(ControlCase, case_id)
    if case is None:
        return RedirectResponse("/ui?err=Дело не найдено", status_code=303)

    before = audit.case_snapshot(case)
    form = await request.form()
    _apply_case_fields(case, form)
    _save_nested(db, case, form)
    # Координаты адреса для карты — в фоне, чтобы не задерживать сохранение
    geocoding.schedule_for_case(case)
    db.flush()

    changes = audit.field_changes(before, audit.case_snapshot(case))
    audit.record(
        db,
        actor=_actor(request),
        entity_table="control_cases",
        entity_id=case.id,
        action="update",
        comment=(
            "изменено полей: " + str(len(changes)) if changes else "сохранено без изменений"
        ),
        changes=changes or None,
    )
    db.commit()
    return RedirectResponse(
        f"/ui/cases/{case.id}?ok=Изменения сохранены", status_code=303
    )


def _apply_case_fields(case: ControlCase, form) -> None:
    """Скалярные поля дела: общие для создания и редактирования."""

    # Внутренний номер заявки здесь не читается: его присваивает система
    # (services/numbers.py) и вручную он не меняется — даже если поле
    # придёт в запросе, оно останется без последствий.
    case.erp_number = _text(form, "erp_number")
    # Номер акта — уточнение: пустое значение значит «печатать номер
    # мероприятия», поэтому пустую строку храним как отсутствие значения.
    case.act_number = _text(form, "act_number") or None
    case.control_kind_id = forms.parse_int(form.get("control_kind_id"))
    case.control_form_id = forms.parse_int(form.get("control_form_id"))
    case.control_body_id = forms.parse_int(form.get("control_body_id"))
    case.controlled_organization_id = forms.parse_int(
        form.get("controlled_organization_id")
    )
    case.controlled_unit_id = forms.parse_int(form.get("controlled_unit_id"))
    case.responsible_organization_id = forms.parse_int(
        form.get("responsible_organization_id")
    )
    case.responsible_unit_id = forms.parse_int(form.get("responsible_unit_id"))
    case.control_object_id = forms.parse_int(form.get("control_object_id"))
    case.purpose = _text(form, "purpose")
    case.subject = _text(form, "subject")
    case.status_id = forms.parse_int(form.get("status_id"))
    case.assignment_number = _text(form, "assignment_number")
    case.assignment_date = forms.parse_datetime(form.get("assignment_date"))
    case.assignment_approved_by_signatory_id = forms.parse_int(
        form.get("assignment_approved_by_signatory_id")
    )
    case.planned_start_at = forms.parse_datetime(form.get("planned_start_at"))
    case.planned_end_at = forms.parse_datetime(form.get("planned_end_at"))
    case.actual_start_at = forms.parse_datetime(form.get("actual_start_at"))
    case.actual_end_at = forms.parse_datetime(form.get("actual_end_at"))
    case.act_composed_at = forms.parse_datetime(form.get("act_composed_at"))
    # Срок исполнения заявки: до выдачи предписания это и есть дата контроля.
    case.control_due_on = forms.parse_date(form.get("control_due_on"))


def _resolve_address_id(db: Session, form, field: str) -> int | None:
    """Адрес в форме вводится строкой: запись находится или заводится сама.

    Отдельное поле с идентификатором поддерживается для программного
    интерфейса и проверок.
    """

    text = _text(form, field)
    if text:
        address = address_service.resolve(db, text)
        return address.id if address is not None else None
    return forms.parse_int(form.get(f"{field}_id"))


def _save_nested(db: Session, case: ControlCase, form) -> None:
    """Основание, инспектор, действие, нарушение, предписание и решение.

    Существующие записи обновляются, а не создаются заново: иначе каждое
    сохранение формы плодило бы дубли, и в документах поехали бы данные.
    """

    basis_kind = _text(form, "basis_kind")
    basis = db.scalars(
        select(ControlCaseBase)
        .where(ControlCaseBase.control_case_id == case.id)
        .order_by(ControlCaseBase.id)
    ).first()
    if basis_kind:
        if basis is None:
            basis = ControlCaseBase(
                control_case_id=case.id, kind=CaseBaseKind(basis_kind)
            )
            db.add(basis)
        basis.kind = CaseBaseKind(basis_kind)
        basis.document_number = _text(form, "basis_document_number")
        basis.document_date = forms.parse_datetime(form.get("basis_document_date"))
        basis.description = _text(form, "basis_description")
    elif basis is not None:
        db.delete(basis)

    inspector_id = forms.parse_int(form.get("inspector_id"))
    link = db.scalars(
        select(ControlCaseInspector)
        .where(ControlCaseInspector.control_case_id == case.id)
        .order_by(ControlCaseInspector.id)
    ).first()
    if inspector_id:
        if link is None:
            link = ControlCaseInspector(
                control_case_id=case.id,
                inspector_id=inspector_id,
                role=InspectorRole.LEADER,
            )
            db.add(link)
        link.inspector_id = inspector_id
    elif link is not None:
        db.delete(link)

    action_type = _text(form, "action_type") or ControlActionType.INSPECTION.value
    place_id = _resolve_address_id(db, form, "action_place_address")
    if place_id is None and case.control_object is not None:
        place_id = case.control_object.address_id
    started_at = forms.parse_datetime(form.get("action_started_at"))

    action = db.scalars(
        select(ControlAction)
        .where(ControlAction.control_case_id == case.id)
        .order_by(ControlAction.sequence_no)
    ).first()
    if started_at or place_id:
        if action is None:
            action = ControlAction(control_case_id=case.id, sequence_no=1)
            db.add(action)
        action.action_type = ControlActionType(action_type)
        action.started_at = started_at
        action.ended_at = forms.parse_datetime(form.get("action_ended_at"))
        action.place_address_id = place_id
        action.result_text = _text(form, "action_result_text")
        # Нарушение считается выявленным, если заполнены работы, вид
        # нарушения или его описание: отдельного текстового поля больше нет.
        action.is_violation_found = bool(
            _text(form, "violation_description")
            or forms.parse_int(form.get("violation_type_id"))
            or form.getlist("violation_work_ids")
        )
        db.flush()
    elif action is not None:
        db.delete(action)
        action = None

    violation_description = _text(form, "violation_description")
    violation_type_id = forms.parse_int(form.get("violation_type_id"))
    work_rows = forms.work_rows(form)
    violation = db.scalars(
        select(Violation)
        .where(Violation.control_case_id == case.id)
        .order_by(Violation.id)
    ).first()
    # Нарушение сохраняется, если заполнено любое его поле: работы, адрес,
    # вид нарушения или дата выявления. Описание больше не вводится вручную —
    # оно собирается из работ, вида нарушения и объекта контроля.
    if (
        violation_description
        or work_rows
        or _text(form, "violation_address")
        or violation_type_id
        or forms.parse_datetime(form.get("violation_detected_at"))
    ):
        # Описание в базе обязательно. Здесь же кладём собранный текст: он
        # печатается в документах и по нему ищут по заявкам.
        description = (
            violation_description
            or violations.description_for(db, case, work_rows, violation_type_id)
            or _text(form, "subject")
            or "нарушение не описано"
        )
        if violation is None:
            violation = Violation(control_case_id=case.id, description=description)
            db.add(violation)
        address_id = _resolve_address_id(db, form, "violation_address")
        if address_id is None and case.control_object is not None:
            address_id = case.control_object.address_id
        violation.violation_type_id = violation_type_id
        violation.description = description
        violation.detected_at = (
            forms.parse_datetime(form.get("violation_detected_at"))
            or case.actual_start_at
        )
        violation.address_id = address_id
        violation.control_action_id = action.id if action is not None else None
        db.flush()

        # Набор статей целиком приходит из формы, поэтому перебираем заново.
        for provision in list(violation.provisions):
            db.delete(provision)
        db.flush()
        for raw in form.getlist("violation_article_ids"):
            article_id = forms.parse_int(raw)
            if article_id:
                db.add(
                    ViolationProvision(
                        violation_id=violation.id, npa_article_id=article_id
                    )
                )

        # Работы с объёмами: тоже набором целиком, чтобы удаление строки в
        # форме убирало её и в базе.
        violations.save_works(db, violation, work_rows)
    elif violation is not None:
        db.delete(violation)
        violation = None

    prescription = db.scalars(
        select(Prescription)
        .where(Prescription.control_case_id == case.id)
        .order_by(Prescription.id)
    ).first()
    action_code = _text(form, "prescription_action_code")
    if (
        _text(form, "prescription_number")
        or action_code
        or _text(form, "prescription_requirement")
    ):
        if prescription is None:
            prescription = Prescription(control_case_id=case.id)
            db.add(prescription)
        prescription.number = _text(form, "prescription_number")
        prescription.issued_on = forms.parse_date(form.get("prescription_issued_on"))
        prescription.due_on = forms.parse_date(form.get("prescription_due_on"))
        prescription.status_id = forms.parse_int(form.get("prescription_status_id"))
        db.flush()

        requirement = _text(form, "prescription_requirement")
        item = prescription.items[0] if prescription.items else None
        if action_code or requirement:
            if item is None:
                item = PrescriptionItem(prescription_id=prescription.id, sequence_no=1)
                db.add(item)
            # Действие из списка: «восстановить», «устранить», «убрать». По
            # нему собирается требование; работы берутся из нарушения.
            item.action_code = action_code or violation_text.DEFAULT_ACTION
            item.requirement_text = requirement or None
            item.due_on = prescription.due_on
        elif item is not None:
            db.delete(item)
    elif prescription is not None:
        db.delete(prescription)
        prescription = None

    decision = db.scalars(
        select(Decision)
        .where(Decision.control_case_id == case.id)
        .order_by(Decision.id)
    ).first()
    decision_date = forms.parse_date(form.get("decision_date"))
    decision_item_text = _text(form, "decision_item_description")
    if decision_date or decision_item_text:
        if decision is None:
            decision = Decision(control_case_id=case.id)
            db.add(decision)
        decision.number = _text(form, "decision_number") or case.erp_number
        decision.decision_date = decision_date
        decision.decision_kind = _text(form, "decision_kind")
        decision.content = _text(form, "decision_content")
        decision.approved_by_signatory_id = case.assignment_approved_by_signatory_id
        decision.prepared_by_inspector_id = inspector_id
        db.flush()

        item = decision.items[0] if decision.items else None
        if decision_item_text:
            if item is None:
                item = DecisionItem(
                    decision_id=decision.id,
                    sequence_no=1,
                    kind=DecisionItemKind.ISSUE_PRESCRIPTION,
                )
                db.add(item)
            item.description = decision_item_text
        elif item is not None:
            db.delete(item)
    elif decision is not None:
        db.delete(decision)



@router.get("/cases/{case_id}/fill", response_class=HTMLResponse)
def case_fill(
    request: Request,
    case_id: int,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Экран данных для документов.

    Отдельная страница для делопроизводителя: что осталось заполнить, по
    блокам, со ссылками на поля — и кнопки сборки пакетов, которые сейчас
    доступны. Нужна, чтобы не искать недостающее по всей форме заявки и не
    возвращаться в карточку за кнопкой.
    """

    case = db.get(ControlCase, case_id)
    if case is None:
        return RedirectResponse("/ui?err=Дело не найдено", status_code=303)
    if not areas.can_view_case(db, getattr(request.state, "user", None), case):
        return RedirectResponse(
            "/ui?err=Заявка относится к чужой управе", status_code=303
        )

    available_packages = _available_packages(db, case)
    available_codes = [item["kind"].code for item in available_packages]
    package_kind = available_codes[0] if available_codes else "primary_prescription"

    check = validation.check_readiness(db, case_id, package_kind)
    readiness = _prepare_readiness(db, case, check.as_dict())

    return templates.TemplateResponse(
        request,
        "case_fill.html",
        {
            "case": case,
            "state": case_state.state_title(db, case),
            "control_due_on": case_state.control_due_on(db, case),
            "control_source": case_state.control_source(db, case),
            "readiness": readiness,
            "available_packages": available_packages,
            "can_build_packages": auth.can_build_packages(_actor(request)),
            "ok": None,
            "err": None,
        },
    )


@router.get("/cases/{case_id}", response_class=HTMLResponse)
def case_card(
    request: Request,
    case_id: int,
    db: Session = Depends(get_db),
    package_kind: str = "primary_prescription",
    ok: str | None = None,
    err: str | None = None,
) -> HTMLResponse:
    case = db.get(ControlCase, case_id)
    if case is None:
        return RedirectResponse("/ui?err=Дело не найдено", status_code=303)
    if not areas.can_view_case(db, getattr(request.state, "user", None), case):
        return RedirectResponse(
            "/ui?err=Заявка относится к чужой управе", status_code=303
        )

    package = _last_package(db, case_id)
    # Готовность показывается для того пакета, который сейчас доступен:
    # по состоянию заявки он один, и именно его оператор и соберёт.
    available_packages = _available_packages(db, case)
    available_codes = [item["kind"].code for item in available_packages]
    if package_kind not in available_codes:
        package_kind = available_codes[0] if available_codes else package_kind

    # Кнопка «Сохранить в папку» относится к текущему пакету — тому, который
    # следует из состояния заявки, а не к последнему собранному вообще.
    document_groups = _document_groups(db, case)
    package = max(
        (group["package"] for group in document_groups if group["package"]),
        key=lambda item: item.id,
        default=package,
    )
    check = validation.check_readiness(db, case_id, package_kind)
    readiness = _prepare_readiness(db, case, check.as_dict())
    return templates.TemplateResponse(
        request,
        "case_card.html",
        {
            "case": case,
            "state": case_state.state_title(db, case),
            "control_due_on": case_state.control_due_on(db, case),
            "control_source": case_state.control_source(db, case),
            "control_overdue": bool(
                case_state.control_due_on(db, case)
                and case_state.control_due_on(db, case)
                < ru.to_display(datetime.now(timezone.utc)).date()
            ),
            "documents": _documents(db, case_id),
            "document_groups": _document_groups(db, case),
            "package": package,
            "readiness": readiness,
            # Список «чего не хватает» в карточке по умолчанию не показывается:
            # документы формируются по требованию, и заявка без пакета — это
            # обычное состояние. Готовность видна на экране данных, а в
            # карточке появляется после попытки собрать пакет (см. ниже).
            "show_readiness": False,
            "details": _case_details(db, case_id),
            "package_kinds": _package_kinds(db),
            "available_packages": _available_packages(db, case),
            "can_build_packages": auth.can_build_packages(_actor(request)),
            "responsible_organizations": _responsible_organizations(db),
            "package_kind": package_kind,
            "inspections": inspections_service.inspections(db, case_id),
            "available_inspection_kind": inspections_service.available_kind(db, case_id),
            "administrative": db.scalars(
                select(AdministrativeCase).where(
                    AdministrativeCase.control_case_id == case_id
                )
            ).first(),
            # Событие правонарушения собирается из дат, а не вводится текстом.
            "administrative_circumstances": _administrative_circumstances(db, case_id),
            # Что подставится в «Приложение:», если поле не заполнили.
            "administrative_appendix_default": _appendix_default(db, case_id),
            # Адрес объекта контроля: он же место правонарушения по умолчанию.
            # Адреса для выбора места составления протокола: адрес управы
            # заявки, адреса органов контроля и уже выбранные адреса управ.
            "protocol_place_options": _protocol_place_options(db, case),
            "control_object_address": (
                case.control_object.address.full_address
                if case.control_object is not None
                and case.control_object.address is not None
                else None
            ),
            "show_administrative": _show_administrative(db, case),
            "ok": ok,
            "err": err,
        },
    )


def _readiness_issues(db: Session, case: ControlCase, readiness: dict) -> list[dict]:
    """Пункты готовности со ссылкой туда, где поле заполняется.

    Сообщение «не указано место составления протокола» заставляет искать поле
    по всей карточке. Поэтому каждому пункту находится место — осмотр, по
    которому собирается пакет, блок административного производства, реквизиты
    организации или форма заявки — и поле в этом месте. Ссылка ведёт на якорь
    #f-<имя поля>, по нему страница подсвечивает нужный ввод.
    """

    # Поля, у которых имя в форме отличается от имени в проверке.
    case_inputs = {
        "control_kind": "control_kind_id",
        "control_form": "control_form_id",
        "control_body": "control_body_id",
        "controlled_organization": "controlled_organization_id",
        "controlled_unit": "controlled_unit_id",
        "control_object": "control_object_id",
        "approver": "assignment_approved_by_signatory_id",
        "violations": "violation_description",
    }
    # Поля нарушения, предписания и решения в форме идут с приставкой,
    # а у некоторых имя отличается от имени в проверке.
    prefixed = {
        "prescription": ("prescription_", {"items": "prescription_requirement"}),
        "decision": ("decision_", {"items": "decision_item_description"}),
        "violation": (
            "violation_",
            {
                "description": "violation_description",
                "provisions": "violation_article_ids",
            },
        ),
    }

    issues: list[dict] = []
    for issue in readiness.get("issues", []):
        field_name = issue.get("field") or ""
        url = f"/ui/cases/{case.id}/edit"
        where = "карточка заявки"
        group = "Данные заявки"

        if field_name.startswith("administrative."):
            input_name = field_name.split(".", 1)[1]
            url = f"/ui/cases/{case.id}#f-{input_name}"
            where = "данные административного производства"
            group = "Административное производство"
        elif field_name.startswith("action."):
            parts = field_name.split(".")
            action_id = parts[1] if len(parts) > 1 and parts[1].isdigit() else None
            input_name = parts[2] if len(parts) > 2 else None
            if action_id is None:
                inspection = inspections_service.latest(db, case.id)
                action_id = str(inspection.id) if inspection is not None else None
            if action_id is not None:
                action = db.get(ControlAction, int(action_id))
                url = f"/ui/inspections/{action_id}"
                if input_name:
                    url += f"#f-{input_name}"
                where = (
                    f"осмотр №{action.sequence_no}"
                    if action is not None and action.sequence_no
                    else "осмотр"
                )
            group = "Осмотр"
        elif (
            field_name == "requisites"
            or field_name.startswith("requisites.")
            or field_name == "contacts"
        ):
            organization = case.controlled_organization
            if organization is not None:
                url = f"/ui/dictionaries/organizations/{organization.id}"
                where = f"реквизиты {organization.short_name}"
            group = "Контролируемое лицо"
        else:
            prefix, _, rest = field_name.partition(".")
            if prefix in prefixed:
                base, special = prefixed[prefix]
                input_name = special.get(rest, base + rest)
            else:
                input_name = case_inputs.get(prefix, field_name)
            url = f"/ui/cases/{case.id}/edit#f-{input_name}"
            # Блоки те же, что в форме заявки: делопроизводитель видит не
            # список из двух десятков пунктов, а «чего не хватает» по темам.
            group = {
                "control_object": "Объект контроля",
                "assignment": "Задание и сроки",
                "planned": "Задание и сроки",
                "actual": "Задание и сроки",
                "act_composed": "Задание и сроки",
                "approver": "Задание и сроки",
                "violation": "Нарушение и квалификация",
                "violations": "Нарушение и квалификация",
                "prescription": "Предписание",
                "decision": "Решение",
                "controlled": "Контролируемое лицо",
                "responsible": "Контролируемое лицо",
            }.get(prefix, "Данные заявки")

        issues.append({**issue, "url": url, "where": where, "group": group})
    return issues


def _prepare_readiness(db: Session, case: ControlCase, readiness: dict) -> dict:
    """Дополняет готовность ссылками: пункты — что мешает, замечания — что нет.

    Замечания не мешают собрать пакет (например, ещё нет номера из реестра
    контрольных мероприятий), но ведут туда же, где заполняется поле.
    """

    readiness["issues"] = _readiness_issues(db, case, readiness)
    readiness["warnings"] = _readiness_issues(
        db, case, {"issues": readiness.get("warnings", [])}
    )
    return readiness


def _case_details(db: Session, case_id: int) -> dict:
    """Основание, инспекторы, нарушение, предписание и решение для карточки."""

    basis = db.scalars(
        select(ControlCaseBase)
        .where(ControlCaseBase.control_case_id == case_id)
        .order_by(ControlCaseBase.id)
    ).first()
    inspectors = [
        link.inspector
        for link in db.scalars(
            select(ControlCaseInspector).where(
                ControlCaseInspector.control_case_id == case_id
            )
        )
        if link.inspector is not None
    ]
    action = db.scalars(
        select(ControlAction)
        .where(ControlAction.control_case_id == case_id)
        .order_by(ControlAction.sequence_no)
    ).first()
    violation = db.scalars(
        select(Violation)
        .where(Violation.control_case_id == case_id)
        .order_by(Violation.id)
    ).first()
    prescription = db.scalars(
        select(Prescription)
        .where(Prescription.control_case_id == case_id)
        .order_by(Prescription.id)
    ).first()
    decision = db.scalars(
        select(Decision)
        .where(Decision.control_case_id == case_id)
        .order_by(Decision.id)
    ).first()
    return {
        "basis": basis,
        # Названия значений вместо кодов: в карточке «inspection» и
        # «mu_material» оператору ни о чём не говорят.
        "basis_title": (
            labels.title(labels.BASIS_KIND_TITLES, basis.kind.value)
            if basis is not None
            else None
        ),
        "action_title": (
            labels.title(labels.ACTION_TYPE_TITLES, action.action_type.value)
            if action is not None
            else None
        ),
        "inspectors": inspectors,
        "action": action,
        "violation": violation,
        "areas": areas.case_areas(db, db.get(ControlCase, case_id)),
        "violation_provisions": (
            [provision.npa_article for provision in violation.provisions]
            if violation is not None
            else []
        ),
        # Работы с объёмами печатаются в карточке одной строкой: «асфальт –
        # 4 кв.м., грунт – 20 кв.м.». Из них собираются оба текста.
        "violation_works": (
            [
                {
                    "work": item.work,
                    "quantity": item.quantity,
                    "quantity_text": violation_text.quantity_text(
                        item.quantity,
                        item.work.unit if item.work is not None else None,
                    ),
                }
                for item in violation.works
            ]
            if violation is not None
            else []
        ),
        "prescription": prescription,
        "prescription_item": (
            prescription.items[0]
            if prescription is not None and prescription.items
            else None
        ),
        # Требование собирается из данных, а не берётся из введённого текста:
        # так в карточке видно ровно то, что попадёт в предписание.
        "prescription_requirement_text": _requirement_text(
            violation, prescription
        ),
        "decision": decision,
        "decision_item": (
            decision.items[0]
            if decision is not None and decision.items
            else None
        ),
    }


@router.post("/cases/{case_id}/packages")
async def create_package(
    request: Request, case_id: int, db: Session = Depends(get_db)
):
    """Сборка пакета документов из карточки заявки.

    Вид пакета приходит из формы: первичный, вторичный или об исполнении
    предписания. Уведомление о явке и протокол об административном
    правонарушении входят только во вторичный пакет — это задано составом
    пакетов в справочнике, а не кодом.
    """

    case = db.get(ControlCase, case_id)
    if case is None:
        return RedirectResponse("/ui?err=Дело не найдено", status_code=303)

    # Пакеты собирает делопроизводитель: инспектор делает осмотр, и это
    # разные работы. Проверка на сервере, а не только скрытой кнопкой —
    # иначе запрет обходится прямым запросом.
    if not auth.can_build_packages(_actor(request)):
        return RedirectResponse(
            f"/ui/cases/{case_id}?err="
            f"{quote('Пакеты документов собирает делопроизводитель')}",
            status_code=303,
        )

    form = await request.form()
    package_kind = _text(form, "package_kind") or "primary_prescription"
    kind = db.scalars(
        select(PackageKind).where(PackageKind.code == package_kind)
    ).first()
    if kind is None:
        return RedirectResponse("/ui?err=Неизвестный вид пакета", status_code=303)

    # Пакет можно собрать только тогда, когда он следует из состояния заявки:
    # первичный — по первичному осмотру, вторичный — когда нарушение не
    # устранено, об исполнении — когда устранено.
    available = {item["kind"].code for item in _available_packages(db, case)}
    if package_kind not in available:
        return RedirectResponse(
            f"/ui/cases/{case_id}?err={quote(f'Пакет «{kind.name}» сейчас недоступен')}",
            status_code=303,
        )

    check = validation.check_readiness(db, case_id, package_kind)
    if not check.is_ready:
        package = _last_package(db, case_id)
        readiness = _prepare_readiness(db, case, check.as_dict())
        return templates.TemplateResponse(
            request,
            "case_card.html",
            {
                "case": case,
                "state": case_state.state_title(db, case),
                "control_due_on": case_state.control_due_on(db, case),
                "control_source": case_state.control_source(db, case),
                "control_overdue": bool(
                    case_state.control_due_on(db, case)
                    and case_state.control_due_on(db, case)
                    < ru.to_display(datetime.now(timezone.utc)).date()
                ),
                "documents": _documents(db, case_id),
                "document_groups": _document_groups(db, case),
                "package": package,
                "readiness": readiness,
                # Пакет собирали — значит, список недостающего уместен именно
                # сейчас: показываем, чего не хватает, и ведём к полям.
                "show_readiness": True,
                "details": _case_details(db, case_id),
                "package_kinds": _package_kinds(db),
                "available_packages": _available_packages(db, case),
                "can_build_packages": auth.can_build_packages(_actor(request)),
                "responsible_organizations": _responsible_organizations(db),
                "package_kind": package_kind,
                "inspections": inspections_service.inspections(db, case_id),
                "available_inspection_kind": inspections_service.available_kind(
                    db, case_id
                ),
                "administrative": db.scalars(
                    select(AdministrativeCase).where(
                        AdministrativeCase.control_case_id == case_id
                    )
                ).first(),
                "show_administrative": _show_administrative(db, case),
                "ok": None,
                "err": f"Пакет «{kind.name}» не сформирован: заполнены не все поля",
            },
            status_code=409,
        )

    result = generation.generate_package(
        db, case_id, package_kind_code=package_kind
    )
    audit.record(
        db,
        actor=_actor(request),
        entity_table="document_packages",
        entity_id=result.package_id,
        action="generate",
        comment=(
            f"собран пакет «{kind.name}» по заявке {case.erp_number or case_id}: "
            f"документов {len(result.created)}"
        ),
    )
    db.commit()
    if not result.missing_templates:
        package = db.get(DocumentPackage, result.package_id)
        if package is not None:
            actor = _actor(request)
            crm_events.package_generated(
                case,
                package,
                len(result.created),
                actor_name=(actor.full_name if actor else None),
            )
    message = (
        f"Пакет «{kind.name}» №{result.package_id} сформирован: "
        f"документов {len(result.created)}"
    )
    return RedirectResponse(f"/ui/cases/{case_id}?ok={message}", status_code=303)


@router.post("/cases/{case_id}/responsible")
async def assign_responsible(
    request: Request, case_id: int, db: Session = Depends(get_db)
):
    """Ответственный за исполнение нарушения.

    Отдельное действие в карточке, а не поле в форме заявки: ответственного
    назначает делопроизводитель, и он нужен в том числе по заявке без
    документов — там, где предписания ещё нет. Автоматически система его не
    назначает: правило «адрес → управа → ответственный» появится позже.
    """

    case = db.get(ControlCase, case_id)
    if case is None:
        return RedirectResponse("/ui?err=Дело не найдено", status_code=303)

    if not auth.can_build_packages(_actor(request)):
        return RedirectResponse(
            f"/ui/cases/{case_id}?err="
            f"{quote('Ответственного за исполнение назначает делопроизводитель')}",
            status_code=303,
        )

    form = await request.form()
    organization_id = forms.parse_int(form.get("responsible_organization_id"))
    organization = (
        db.get(Organization, organization_id) if organization_id else None
    )
    case.responsible_organization_id = (
        organization.id if organization is not None else None
    )
    audit.record(
        db,
        actor=_actor(request),
        entity_table="control_cases",
        entity_id=case.id,
        action="update",
        comment=(
            f"ответственный за исполнение: "
            f"{organization.short_name if organization else 'снят'}"
        ),
    )
    db.commit()
    message = (
        f"Ответственный за исполнение: {organization.short_name}"
        if organization is not None
        else "Ответственный за исполнение снят"
    )
    return RedirectResponse(f"/ui/cases/{case_id}?ok={message}", status_code=303)


@router.post("/cases/{case_id}/prosecutor")
async def save_prosecutor_data(
    request: Request, case_id: int, db: Session = Depends(get_db)
):
    """Номер мероприятия и QR-код из прокуратуры.

    Оба значения выдаёт портал прокуратуры: система их не создаёт, а печатает
    в акте и предписании. Номер — текстом, QR-код — картинкой, подогнанной
    под место, зарезервированное в бланке. Пока данных нет, документы
    собираются с пустым местом, а после ввода пакет пересобирают заново.
    """

    case = db.get(ControlCase, case_id)
    if case is None:
        return RedirectResponse("/ui?err=Дело не найдено", status_code=303)

    if not auth.can_build_packages(_actor(request)):
        return RedirectResponse(
            f"/ui/cases/{case_id}?err="
            f"{quote('Номер и QR-код из прокуратуры вносит делопроизводитель')}",
            status_code=303,
        )

    form = await request.form()
    case.erp_number = _text(form, "erp_number")

    action = "номер обновлён"
    if _text(form, "remove_qr"):
        case.qr_file_id = None
        action = "QR-код убран"
    else:
        upload = form.get("qr")
        if upload is not None and getattr(upload, "filename", ""):
            data = await upload.read()
            if not data:
                return RedirectResponse(
                    f"/ui/cases/{case_id}?err={quote('Пустой файл')}",
                    status_code=303,
                )
            # Проверяем, что это действительно картинка: иначе сборка пакета
            # упадёт позже и не там, где ошибка на самом деле.
            try:
                with Image.open(BytesIO(data)) as image:
                    image.verify()
            except Exception:  # noqa: BLE001 — сообщение важнее типа ошибки
                return RedirectResponse(
                    f"/ui/cases/{case_id}?err="
                    f"{quote('Файл не читается как изображение')}",
                    status_code=303,
                )
            file = storage.save_bytes(
                db,
                data,
                getattr(upload, "filename", "qr.png"),
                kind=FileKind.ATTACHMENT,
                mime_type=getattr(upload, "content_type", None) or "image/png",
                commit=False,
            )
            case.qr_file_id = file.id
            action = "QR-код загружен"

    audit.record(
        db,
        actor=_actor(request),
        entity_table="control_cases",
        entity_id=case.id,
        action="update",
        comment=(
            f"{action}: номер {case.erp_number or 'не указан'}"
        ),
    )
    db.commit()
    return RedirectResponse(
        f"/ui/cases/{case_id}?ok="
        f"{quote('Данные из прокуратуры сохранены. Соберите пакет заново')}",
        status_code=303,
    )


@router.get("/cases/{case_id}/qr")
def case_qr(case_id: int, db: Session = Depends(get_db)) -> FileResponse:
    """Отдаёт загруженный QR-код из прокуратуры."""

    case = db.get(ControlCase, case_id)
    if case is None or case.qr_file is None:
        return RedirectResponse("/ui?err=QR-код не загружен", status_code=303)
    return FileResponse(
        path=storage.absolute_path(case.qr_file.storage_path),
        media_type=case.qr_file.mime_type or "image/png",
        # Адрес картинки не меняется при замене кода — браузер должен
        # спрашивать сервер, иначе покажет прежний код из своего кэша.
        headers={"Cache-Control": "no-cache"},
    )


@router.post("/cases/{case_id}/administrative")
async def save_administrative(
    request: Request, case_id: int, db: Session = Depends(get_db)
):
    """Данные административного производства по заявке.

    Нужны для вторичного пакета: без них уведомление о явке и протокол об
    административном правонарушении вышли бы с пустыми местами.
    """

    case = db.get(ControlCase, case_id)
    if case is None:
        return RedirectResponse("/ui?err=Дело не найдено", status_code=303)

    row = db.scalars(
        select(AdministrativeCase).where(
            AdministrativeCase.control_case_id == case_id
        )
    ).first()
    created = row is None
    if row is None:
        row = AdministrativeCase(control_case_id=case_id)
        db.add(row)

    form = await request.form()
    row.protocol_number = _text(form, "protocol_number")
    row.protocol_date = forms.parse_date(form.get("protocol_date"))
    row.protocol_place = _text(form, "protocol_place")
    row.appearance_date = forms.parse_date(form.get("appearance_date"))
    row.appearance_time = _text(form, "appearance_time")
    # Место явки и кабинет не заполняются в производстве: они берутся из
    # карточки управы. Поля в форме нет, поэтому и не перезаписываем.
    if "appearance_place" in form:
        row.appearance_place = _text(form, "appearance_place")
    if "appearance_office" in form:
        row.appearance_office = _text(form, "appearance_office")
    row.notice_number = _text(form, "notice_number")
    row.notice_date = forms.parse_date(form.get("notice_date"))
    # Статья по умолчанию: именно её печатают оба документа.
    row.offense_article = _text(form, "offense_article") or "частью 1 статьи 19.5"
    row.offense_date = forms.parse_date(form.get("offense_date"))
    row.offense_time = _text(form, "offense_time")
    row.offense_place = _text(form, "offense_place")
    # Текст события правонарушения больше не вводится: он собирается из дат
    # ниже. Поле в форме не показывается, поэтому и не перезаписывается —
    # прежний текст остаётся у заявок, заполненных до справочников.
    if "offense_description" in form:
        row.offense_description = _text(form, "offense_description")
    # Ранее выданное предписание: из этих полей собирается текст протокола
    # об административном правонарушении по ст. 19.5.
    row.prior_prescription_number = _text(form, "prior_prescription_number")
    row.prior_prescription_date = forms.parse_date(form.get("prior_prescription_date"))
    row.prior_prescription_due = forms.parse_date(form.get("prior_prescription_due"))
    row.prior_prescription_basis = _text(form, "prior_prescription_basis")
    row.representative_info = _text(form, "representative_info")
    row.appearance_note = _text(form, "appearance_note")
    # Приложение больше не заполняется: это всегда акт и протокол осмотра
    # нашего мероприятия, текст собирается в документе. Поле в форме не
    # показывается, поэтому и не перезаписывается.
    if "appendix_note" in form:
        row.appendix_note = _text(form, "appendix_note")

    audit.record(
        db,
        actor=_actor(request),
        entity_table="administrative_cases",
        entity_id=case_id,
        action="create" if created else "update",
        comment=(
            f"{'заполнены' if created else 'изменены'} данные административного "
            f"производства по заявке {case.erp_number or case_id}"
        ),
        changes=(
            {"номер протокола": {"было": None, "стало": row.protocol_number}}
            if created
            else None
        ),
    )
    db.commit()
    return RedirectResponse(
        f"/ui/cases/{case_id}?package_kind=repeated_prescription"
        "&ok=Данные административного производства сохранены",
        status_code=303,
    )


def _appendix_default(db: Session, case_id: int) -> str | None:
    """Что подставится в «Приложение:», если поле не заполнили."""

    case = db.get(ControlCase, case_id)
    if case is None:
        return None
    inspection = inspections_service.primary(db, case_id)
    date = (
        inspection.started_at if inspection is not None else case.actual_start_at
    )
    text = "акт выездного обследования и протокол осмотра"
    return f"{text} от {ru.date_short(date)}" if date else text


def _protocol_place_options(db: Session, case: ControlCase) -> list:
    """Адреса для выбора места составления протокола.

    Место протокола — адрес управы, по чьей территории заявка. Показываем
    адреса органов контроля и адреса управ, чтобы выбирать из справочника.
    """

    options: dict[int, object] = {}
    for area in areas.case_areas(db, case):
        if area.address is not None:
            options[area.address.id] = area.address
    if case.control_body is not None and case.control_body.address is not None:
        options[case.control_body.address.id] = case.control_body.address
    for body in db.scalars(select(ControlBody).order_by(ControlBody.name)):
        if body.address is not None:
            options[body.address.id] = body.address
    for area in db.scalars(select(Area).order_by(Area.name)):
        if area.address is not None:
            options[area.address.id] = area.address
    return sorted(options.values(), key=lambda item: item.full_address or "")


def _administrative_circumstances(db: Session, case_id: int) -> str | None:
    """Событие правонарушения — то же, что попадёт в протокол.

    Если оператор не заполнил данные ранее выданного предписания, берётся
    предписание этой же заявки: протокол по ст. 19.5 описывает именно его
    неисполнение, и в тексте стоят даты наших документов.
    """

    row = db.scalars(
        select(AdministrativeCase).where(AdministrativeCase.control_case_id == case_id)
    ).first()
    if row is None:
        return None
    prescription = db.scalars(
        select(Prescription)
        .where(Prescription.control_case_id == case_id)
        .order_by(Prescription.issued_on.desc())
    ).first()
    prior_date = row.prior_prescription_date or (
        prescription.issued_on if prescription is not None else None
    )
    prior_due = row.prior_prescription_due or (
        prescription.due_on if prescription is not None else None
    )
    inspection = inspections_service.primary(db, case_id)
    case = db.get(ControlCase, case_id)
    measure_date = (
        inspection.started_at
        if inspection is not None
        else (case.actual_start_at if case is not None else None)
    )
    return violation_text.administrative_circumstances(
        ru.date_short(prior_date),
        ru.date_short(prior_due),
        ru.date_short(measure_date),
    )


def _show_administrative(db: Session, case: ControlCase) -> bool:
    """Показывать ли блок административного производства.

    Уведомление о явке и протокол об административном правонарушении
    входят только во вторичное предписание, а оно следует из повторного
    осмотра с результатом «нарушение не устранено». В остальных состояниях
    блок только запутывает: заполнять в нём нечего.
    """

    repeat = inspections_service.repeat(db, case.id)
    return (
        repeat is not None
        and repeat.inspection_result == InspectionResult.NOT_FIXED
    )


def _available_packages(db: Session, case: ControlCase) -> list[dict]:
    """Какие пакеты можно собрать по состоянию заявки.

    Правило живёт в сервисе: тем же правилом пользуется программный
    интерфейс, чтобы интерфейс диспетчера предлагал те же пакеты.
    """

    return generation.available_packages(db, case)


def _package_kinds(db: Session) -> list[PackageKind]:
    """Виды пакетов для выбора в карточке заявки."""

    return list(db.scalars(select(PackageKind).order_by(PackageKind.sort_order)))


@router.post("/documents/{document_id}/pages")
async def set_document_pages(
    document_id: int, request: Request, db: Session = Depends(get_db)
):
    """Число листов документа: печатается в приложении к направлению."""

    document = db.get(Document, document_id)
    if document is None:
        return RedirectResponse("/ui?err=Документ не найден", status_code=303)
    form = await request.form()
    document.pages = forms.parse_int(form.get("pages"))
    _log_dictionary(
        db,
        request,
        "documents",
        f"число листов документа №{document.id}: {document.pages or '—'}",
        document.id,
    )
    db.commit()
    return RedirectResponse(
        f"/ui/cases/{document.package.control_case_id}?ok=Число листов сохранено",
        status_code=303,
    )


@router.post("/dictionaries/{kind}/{entity_id}/delete")
async def delete_dictionary_value(
    kind: str, entity_id: int, request: Request, db: Session = Depends(get_db)
):
    """Удаляет неиспользуемое значение, используемое — переводит в архив.

    Удалить значение, которое уже вошло в документы, нельзя: ссылка на него
    есть в заявках и снимках данных, и повторная сборка пакета сломалась бы.
    """

    model = dictionary_admin.model_for(kind)
    if model is None:
        return RedirectResponse("/ui/dictionaries?err=Неизвестный справочник", status_code=303)
    entity = db.get(model, entity_id)
    if entity is None:
        return RedirectResponse("/ui/dictionaries?err=Значение не найдено", status_code=303)

    title = dictionary_admin.TITLES.get(kind, "значение")
    label = _value_label(entity)
    result = dictionary_admin.delete_or_archive(db, entity)

    if result["action"] == "archived":
        where = dictionary_admin.describe_references(result["references"])
        _log_dictionary(
            db, request, kind,
            f"{title} «{label}» в архив: используется в ({where})",
            entity_id,
        )
        db.commit()
        return RedirectResponse(
            "/ui/dictionaries?ok="
            + quote(f"«{label}» уже используется ({where}) — переведено в архив"),
            status_code=303,
        )

    _log_dictionary(db, request, kind, f"{title} «{label}» удалён", entity_id)
    db.commit()
    return RedirectResponse(
        "/ui/dictionaries?ok=" + quote(f"«{label}» удалено"),
        status_code=303,
    )


@router.post("/dictionaries/{kind}/{entity_id}/restore")
async def restore_dictionary_value(
    kind: str, entity_id: int, request: Request, db: Session = Depends(get_db)
):
    """Возвращает значение из архива в списки."""

    model = dictionary_admin.model_for(kind)
    if model is None:
        return RedirectResponse("/ui/dictionaries?err=Неизвестный справочник", status_code=303)
    entity = db.get(model, entity_id)
    if entity is None:
        return RedirectResponse("/ui/dictionaries?err=Значение не найдено", status_code=303)

    label = _value_label(entity)
    dictionary_admin.restore(db, entity)
    _log_dictionary(
        db, request, kind, f"значение «{label}» возвращено из архива", entity_id
    )
    db.commit()
    return RedirectResponse(
        "/ui/dictionaries?ok=" + quote(f"«{label}» возвращено из архива"),
        status_code=303,
    )


def _value_label(entity) -> str:
    """Подпись значения для сообщений: у каждой модели своё «имя»."""

    for field in ("short_name", "full_name", "name", "full_address", "role"):
        value = getattr(entity, field, None)
        if value is None:
            continue
        if hasattr(value, "value"):
            return str(value.value)
        return str(value)
    return f"№{getattr(entity, 'id', '?')}"


@router.get("/dictionaries", response_class=HTMLResponse)
def dictionaries_page(
    request: Request,
    db: Session = Depends(get_db),
    q: str | None = None,
    ok: str | None = None,
    err: str | None = None,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "dictionaries.html",
        {
            "organizations": list(
                db.scalars(select(Organization).order_by(Organization.id.desc()))
            ),
            "units": list(
                db.scalars(select(OrganizationUnit).order_by(OrganizationUnit.id))
            ),
            "inspectors": list(
                db.scalars(select(Inspector).order_by(Inspector.id.desc()))
            ),
            "signatories": list(
                db.scalars(
                    select(ControlBodySignatory).order_by(ControlBodySignatory.id.desc())
                )
            ),
            "objects": list(
                db.scalars(select(ControlObject).order_by(ControlObject.id.desc()))
            ),
            "object_types": list(
                db.scalars(select(ControlObjectType).order_by(ControlObjectType.sort_order))
            ),
            # Адресов может быть много, поэтому их список ищется по части
            # строки: «московская 8» найдёт нужный адрес.
            "addresses": address_service.search(db, q),
            "address_query": q or "",
            "addresses_total": db.scalar(
                select(func.count()).select_from(Address)
            ),
            "addresses_archived": db.scalar(
                select(func.count())
                .select_from(Address)
                .where(Address.is_active.is_(False))
            ),
            "active_organizations": [
                item
                for item in db.scalars(
                    select(Organization)
                    .where(Organization.is_active.is_(True))
                    .order_by(Organization.short_name)
                )
            ],
            "active_objects": [
                item
                for item in db.scalars(
                    select(ControlObject)
                    .where(ControlObject.is_active.is_(True))
                    .order_by(ControlObject.name)
                )
            ],
            "control_bodies": list(db.scalars(select(ControlBody))),
            "ok": ok,
            "err": err,
        },
    )


@router.post("/dictionaries/organizations")
async def save_organization(request: Request, db: Session = Depends(get_db)):
    """Добавление и правка организации; реквизиты и почта заводятся сразу."""

    form = await request.form()
    organization = None
    existing = forms.parse_int(form.get("id"))
    if existing:
        organization = db.get(Organization, existing)
        if organization is None:
            return RedirectResponse(
                "/ui/dictionaries?err=Организация не найдена", status_code=303
            )

    organization = dictionary_service.save_organization(db, form, organization)
    if organization is None:
        return RedirectResponse(
            "/ui/dictionaries?err=Укажите наименование", status_code=303
        )

    _log_dictionary(
        db,
        request,
        "organizations",
        f"{'изменена' if existing else 'добавлена'} организация: "
        f"{organization.short_name}",
        organization.id,
    )
    db.commit()
    return RedirectResponse(
        f"/ui/dictionaries/organizations/{organization.id}?ok="
        + ("Сохранено" if existing else "Организация добавлена"),
        status_code=303,
    )


@router.get("/dictionaries/organizations/{organization_id}", response_class=HTMLResponse)
def organization_card(
    request: Request,
    organization_id: int,
    db: Session = Depends(get_db),
    ok: str | None = None,
    err: str | None = None,
) -> HTMLResponse:
    """Карточка организации: реквизиты, контакты, филиалы, представители."""

    organization = db.get(Organization, organization_id)
    if organization is None:
        return RedirectResponse("/ui/dictionaries?err=Организация не найдена", status_code=303)
    return templates.TemplateResponse(
        request,
        "organization.html",
        {
            "organization": organization,
            "requisites": list(
                db.scalars(
                    select(OrganizationRequisite)
                    .where(OrganizationRequisite.organization_id == organization_id)
                    .order_by(OrganizationRequisite.valid_from.desc())
                )
            ),
            "contacts": list(
                db.scalars(
                    select(OrganizationContact)
                    .where(OrganizationContact.organization_id == organization_id)
                    .order_by(OrganizationContact.id)
                )
            ),
            "units": list(
                db.scalars(
                    select(OrganizationUnit)
                    .where(OrganizationUnit.organization_id == organization_id)
                    .order_by(OrganizationUnit.id)
                )
            ),
            "representatives": list(
                db.scalars(
                    select(OrganizationSignatory)
                    .where(OrganizationSignatory.organization_id == organization_id)
                    .order_by(OrganizationSignatory.id)
                )
            ),
            "roles": list(
                db.scalars(
                    select(OrganizationRole)
                    .where(OrganizationRole.organization_id == organization_id)
                    .order_by(OrganizationRole.id)
                )
            ),
            "addresses": list(
                db.scalars(select(Address).order_by(Address.id.desc()).limit(200))
            ),
            "role_codes": [code.value for code in OrganizationRoleCode],
            "basis_kinds": labels.options(
                [kind.value for kind in SignatoryBasisKind],
                labels.SIGNATORY_BASIS_TITLES,
            ),
            "ok": ok,
            "err": err,
        },
    )


@router.post("/dictionaries/organizations/{organization_id}")
async def update_organization(
    request: Request, organization_id: int, db: Session = Depends(get_db)
):
    organization = db.get(Organization, organization_id)
    if organization is None:
        return RedirectResponse("/ui/dictionaries?err=Организация не найдена", status_code=303)
    form = await request.form()
    dictionary_service.save_organization(db, form, organization)
    _log_dictionary(
        db,
        request,
        "organizations",
        f"изменена организация: {organization.short_name}",
        organization.id,
    )
    db.commit()
    return RedirectResponse(
        f"/ui/dictionaries/organizations/{organization_id}?ok=Сохранено", status_code=303
    )


@router.post("/dictionaries/organizations/{organization_id}/requisites")
async def create_unit_requisites(
    organization_id: int, request: Request, db: Session = Depends(get_db)
):
    """Реквизиты филиала: без них акт по заявке с филиалом не соберётся."""

    organization = db.get(Organization, organization_id)
    if organization is None:
        return RedirectResponse("/ui/dictionaries?err=Организация не найдена", status_code=303)
    form = await request.form()
    unit_id = forms.parse_int(form.get("unit_id"))
    if unit_id is None:
        return RedirectResponse(
            f"/ui/dictionaries/organizations/{organization_id}?err=Выберите подразделение",
            status_code=303,
        )
    dictionary_service.save_requisites(db, organization, form, unit_id=unit_id)
    _log_dictionary(
        db,
        request,
        "organization_requisites",
        f"реквизиты подразделения №{unit_id} организации {organization.short_name}",
        unit_id,
    )
    db.commit()
    return RedirectResponse(
        f"/ui/dictionaries/organizations/{organization_id}?ok=Реквизиты подразделения сохранены",
        status_code=303,
    )


@router.post("/dictionaries/organizations/{organization_id}/units")
async def create_unit(
    request: Request, organization_id: int, db: Session = Depends(get_db)
):
    organization = db.get(Organization, organization_id)
    if organization is None:
        return RedirectResponse("/ui/dictionaries?err=Организация не найдена", status_code=303)
    form = await request.form()
    existing = forms.parse_int(form.get("id"))
    unit = db.get(OrganizationUnit, existing) if existing else None
    unit = dictionary_service.save_unit(db, organization, form, unit)
    if unit is None:
        return RedirectResponse(
            f"/ui/dictionaries/organizations/{organization_id}?err=Укажите название подразделения",
            status_code=303,
        )
    _log_dictionary(
        db,
        request,
        "organization_units",
        f"{'изменено' if existing else 'добавлено'} подразделение: {unit.name}",
        unit.id,
    )
    db.commit()
    return RedirectResponse(
        f"/ui/dictionaries/organizations/{organization_id}?ok=Подразделение сохранено",
        status_code=303,
    )


@router.post("/dictionaries/organizations/{organization_id}/representatives")
async def create_representative(
    request: Request, organization_id: int, db: Session = Depends(get_db)
):
    organization = db.get(Organization, organization_id)
    if organization is None:
        return RedirectResponse("/ui/dictionaries?err=Организация не найдена", status_code=303)
    form = await request.form()
    existing = forms.parse_int(form.get("id"))
    representative = (
        db.get(OrganizationSignatory, existing) if existing else None
    )
    representative = dictionary_service.save_representative(
        db, organization, form, representative
    )
    if representative is None:
        return RedirectResponse(
            f"/ui/dictionaries/organizations/{organization_id}?err=Укажите ФИО и должность",
            status_code=303,
        )
    _log_dictionary(
        db,
        request,
        "organization_signatories",
        f"{'изменён' if existing else 'добавлен'} представитель организации: "
        f"{representative.full_name}, {representative.position}",
        representative.id,
    )
    db.commit()
    return RedirectResponse(
        f"/ui/dictionaries/organizations/{organization_id}?ok=Представитель сохранён",
        status_code=303,
    )


@router.post("/dictionaries/organizations/{organization_id}/roles")
async def create_organization_role(
    request: Request, organization_id: int, db: Session = Depends(get_db)
):
    organization = db.get(Organization, organization_id)
    if organization is None:
        return RedirectResponse("/ui/dictionaries?err=Организация не найдена", status_code=303)
    form = await request.form()
    existing = forms.parse_int(form.get("id"))
    role = db.get(OrganizationRole, existing) if existing else None
    role = dictionary_service.save_role(db, organization, form, role)
    if role is None:
        return RedirectResponse(
            f"/ui/dictionaries/organizations/{organization_id}?err=Выберите роль",
            status_code=303,
        )
    _log_dictionary(
        db,
        request,
        "organization_roles",
        f"роль организации: {role.role.value}",
        role.id,
    )
    db.commit()
    return RedirectResponse(
        f"/ui/dictionaries/organizations/{organization_id}?ok=Роль сохранена",
        status_code=303,
    )


@router.post("/dictionaries/inspectors")
async def create_inspector(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    existing = forms.parse_int(form.get("id"))
    inspector = db.get(Inspector, existing) if existing else None
    inspector = dictionary_service.save_inspector(db, form, inspector)
    if inspector is None:
        return RedirectResponse(
            "/ui/dictionaries?err=Укажите ФИО и должность инспектора", status_code=303
        )
    _log_dictionary(
        db,
        request,
        "inspectors",
        f"{'изменён' if existing else 'добавлен'} инспектор: "
        f"{inspector.full_name}, {inspector.position}",
        inspector.id,
    )
    db.commit()
    return RedirectResponse("/ui/dictionaries?ok=Инспектор сохранён", status_code=303)


@router.post("/dictionaries/signatories")
async def create_signatory(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    existing = forms.parse_int(form.get("id"))
    signatory = db.get(ControlBodySignatory, existing) if existing else None
    signatory = dictionary_service.save_signatory(db, form, signatory)
    if signatory is None:
        return RedirectResponse(
            "/ui/dictionaries?err=Укажите орган контроля, ФИО и должность",
            status_code=303,
        )
    _log_dictionary(
        db,
        request,
        "control_body_signatories",
        f"{'изменено' if existing else 'добавлено'} утверждающее лицо: "
        f"{signatory.full_name}, {signatory.position}",
        signatory.id,
    )
    db.commit()
    return RedirectResponse("/ui/dictionaries?ok=Подписант сохранён", status_code=303)


@router.post("/dictionaries/addresses")
async def create_address(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    existing = forms.parse_int(form.get("id"))
    address = db.get(Address, existing) if existing else None
    address = dictionary_service.save_address(db, form, address)
    if address is None:
        return RedirectResponse("/ui/dictionaries?err=Укажите адрес", status_code=303)
    _log_dictionary(
        db,
        request,
        "addresses",
        f"{'изменён' if existing else 'добавлен'} адрес: {address.full_address}",
        address.id,
    )
    db.commit()
    return RedirectResponse("/ui/dictionaries?ok=Адрес сохранён", status_code=303)


@router.post("/dictionaries/objects")
async def create_object(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    existing = forms.parse_int(form.get("id"))
    control_object = db.get(ControlObject, existing) if existing else None
    control_object = dictionary_service.save_object(db, form, control_object)
    if control_object is None:
        return RedirectResponse(
            "/ui/dictionaries?err=Укажите вид и описание объекта", status_code=303
        )
    _log_dictionary(
        db,
        request,
        "control_objects",
        f"{'изменён' if existing else 'добавлен'} объект контроля: {control_object.name}",
        control_object.id,
    )
    db.commit()
    return RedirectResponse("/ui/dictionaries?ok=Объект сохранён", status_code=303)
