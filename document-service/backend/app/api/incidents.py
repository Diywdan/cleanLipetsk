"""Фасад обращений для интерфейса диспетчера.

Второй интерфейс — SPA «Чистый Липецк» — работает со своей моделью
обращения (инцидента): статус сигнала, источник, ответственные, таймлайн.
Своих данных у него нет, поэтому модель собирается здесь из наших: заявка,
её осмотры, выявленное нарушение, ответственные и журнал действий.

Документы формируются нашим сервисом: вместо PDF-заглушки, которая рисовалась
в браузере, интерфейс диспетчера просит собрать пакет и скачивает настоящие
бланки.

Названия полей и значения статусов — из контракта фронта
(docs/api-contract.md в его репозитории), чтобы правки на их стороне не
требовались.
"""

from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Body, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.errors import ApiError
from app.db.dependencies import get_db
from app.models import ControlCaseBase
from app.models import (
    AuditLog,
    ControlAction,
    ControlCase,
    Document,
    DocumentPackage,
    DocumentType,
    Violation,
)
from app.models.enums import CaseBaseKind, InspectionKind, InspectionResult, PhotoKind
from app.services import (
    areas,
    audit,
    auto_dates,
    case_state,
    crm_events,
    generation,
    inspections,
    ru,
    validation,
)


router = APIRouter(prefix="/incidents", tags=["incidents"])


# ── Соответствие состояний ──────────────────────────────────────────────────
# Их маршрут: NEW -> IN_PROGRESS -> VERIFICATION -> CLOSED, плюс
# KNM_ESCALATION, когда срок вышел и материалы уходят в надзорный контур.
# Наши состояния выводятся из осмотров и пакетов (case_state), поэтому
# переводим их в их статусы.

STATUS_NEW = "NEW"
STATUS_IN_PROGRESS = "IN_PROGRESS"
STATUS_VERIFICATION = "VERIFICATION"
STATUS_CLOSED = "CLOSED"
STATUS_ESCALATION = "KNM_ESCALATION"

# Источник сигнала: у нас он есть у обращения (справочник источников).
# Совпадающие коды переносим как есть, остальные показываем как «осмотр».
SOURCE_ALIASES = {
    "AI_CAMERA": "AI_CAMERA",
    "TSUR": "TSUR",
    "SED": "SED",
    "OMSU_CHAT": "OMSU_CHAT",
    "INSPECTION": "INSPECTION",
    "DELO_WEB": "DELO_WEB",
    "GOVERNOR_PORTAL": "GOVERNOR_PORTAL",
    "HOUSE_CHATS": "HOUSE_CHATS",
    "MAKS_CHAT": "MAKS_CHAT",
    "DRT_WEBSITE": "DRT_WEBSITE",
    "DIRECT_ORDER": "DIRECT_ORDER",
}
DEFAULT_SOURCE = "INSPECTION"

# Роль ответственного в их модели: содержание площадки — наша
# ответственная организация по заявке.
RESPONSIBLE_ROLE = "site_maintenance"

# Отметки, которые ставит интерфейс диспетчера. Отдельных полей в заявке они
# не требуют: живут основаниями мероприятия, поэтому их видно в карточке дела
# и в документах — «материалы переданы на КНМ» подтверждается бумагой.
MARK_ESCALATED = "передано на контрольно-надзорное мероприятие (интерфейс диспетчера)"
MARK_DISMISSED = "сигнал признан ложным (интерфейс диспетчера)"

# Срок устранения из их карточки: часы, которые выбирает инспектор.
DEADLINE_CHOICES = (24, 48, 72, 720)


def _find_case(db: Session, incident_id: str) -> ControlCase:
    """Ищет заявку по идентификатору обращения.

    В интерфейсе диспетчера идентификатор — это внутренний номер заявки
    (000123). Числа без ведущих нулей принимаем и как номер записи: так
    ссылки, сохранённые до появления номеров, продолжают работать.
    """

    key = (incident_id or "").strip()
    if not key:
        raise ApiError(status_code=404, message="Обращение не найдено")

    case = db.scalars(
        select(ControlCase).where(ControlCase.case_number == key)
    ).first()
    if case is None and key.isdigit():
        case = db.get(ControlCase, int(key))
    if case is None:
        raise ApiError(
            status_code=404, message=f"Обращение {incident_id} не найдено"
        )
    return case


def _marked(case: ControlCase, marker: str) -> bool:
    """Стоит ли на заявке отметка интерфейса диспетчера."""

    return any(
        base.kind == CaseBaseKind.OTHER and (base.description or "") == marker
        for base in case.bases
    )


def _mark(db: Session, case: ControlCase, marker: str) -> None:
    """Ставит отметку интерфейса диспетчера основанием мероприятия."""

    if _marked(case, marker):
        return
    db.add(
        ControlCaseBase(
            control_case_id=case.id,
            kind=CaseBaseKind.OTHER,
            description=marker,
        )
    )


def _primary_inspection(db: Session, case: ControlCase) -> ControlAction | None:
    return inspections.primary(db, case.id)


def _repeat_inspection(db: Session, case: ControlCase) -> ControlAction | None:
    return inspections.repeat(db, case.id)


def _violation(db: Session, case: ControlCase) -> Violation | None:
    return db.scalars(
        select(Violation)
        .where(Violation.control_case_id == case.id)
        .order_by(Violation.id)
    ).first()


def _status(db: Session, case: ControlCase) -> str:
    """Статус обращения в терминах интерфейса диспетчера.

    Статус выводится из наших данных и повторяет их маршрут: сигнал приняли
    (NEW), срок идёт у исполнителя (IN_PROGRESS), работу проверяют
    (VERIFICATION), дело закрыто (CLOSED), материалы ушли на контрольно-
    надзорное мероприятие (KNM_ESCALATION). Последний переход и есть точка
    стыковки с нашим обследованием.
    """

    if _marked(case, MARK_DISMISSED):
        return STATUS_CLOSED

    primary = _primary_inspection(db, case)
    if primary is None:
        # Осмотра ещё не было: обращение ждёт решения инспектора.
        return STATUS_NEW

    violation = _violation(db, case)
    # Предписание выводит дело из обычного цикла. Пока по заявке сформировано
    # первичное предписание и нет исполненного, дело находится в КНМ — даже
    # если нарушение устранено: судьбу решает предписание, а не уборка
    # площадки. Исполненное предписание появляется после повторного обхода с
    # результатом «нарушение устранено», тогда дело и закрывается.
    from sqlalchemy import text as _text

    kinds = set(
        db.scalars(
            _text(
                "select k.code from document_packages p "
                "join package_kinds k on k.id = p.package_kind_id "
                "where p.control_case_id = :case_id"
            ),
            {"case_id": case.id},
        ).all()
    )
    if "primary_prescription" in kinds and "executed_prescription" not in kinds:
        return STATUS_ESCALATION

    if violation is not None and violation.is_eliminated:
        return STATUS_CLOSED

    if _marked(case, MARK_ESCALATED):
        return STATUS_ESCALATION

    if violation is None:
        # Осмотр был, нарушения не выявлено: работа идёт.
        return STATUS_IN_PROGRESS

    repeat = _repeat_inspection(db, case)
    if repeat is not None and repeat.inspection_result == InspectionResult.FIXED:
        # Исполнитель отчитался об устранении, инспектор проверяет.
        return STATUS_VERIFICATION

    # Нарушение выявлено, срок идёт — либо уже вышел, и тогда инспектор может
    # передать материалы на КНМ: в интерфейсе диспетчера это кнопка
    # «Передать на КНМ», у нас по ней заводится выездное обследование.
    return STATUS_IN_PROGRESS


def _source(case: ControlCase) -> str:
    """Источник сигнала.

    Обращение связано с заявкой через основание мероприятия: оснований бывает
    несколько, поэтому берём первое, у которого есть обращение с источником.
    """

    for base in case.bases:
        appeal = base.appeal
        if appeal is None or appeal.source is None:
            continue
        code = (appeal.source.code or "").upper()
        if code in SOURCE_ALIASES:
            return SOURCE_ALIASES[code]
    return DEFAULT_SOURCE


def _priority(db: Session, case: ControlCase) -> str:
    due_on = case_state.control_due_on(db, case)
    if due_on is None:
        return "LOW"
    today = ru.to_display(datetime.now(timezone.utc)).date()
    if due_on < today:
        return "HIGH"
    if (due_on - today).days <= 3:
        return "MEDIUM"
    return "LOW"


def _uprava_id(db: Session, case: ControlCase) -> int:
    """Номер управы числом: в их карте он числовой."""

    for area in areas.case_areas(db, case):
        digits = "".join(symbol for symbol in (area.name or "") if symbol.isdigit())
        if digits:
            return int(digits)
    return 0


def _location(db: Session, case: ControlCase) -> dict:
    address = None
    if case.violations and case.violations[0].address is not None:
        address = case.violations[0].address
    if address is None and case.control_object is not None:
        address = case.control_object.address

    coordinates: list[float] | None = None
    if address is not None and address.latitude is not None and address.longitude is not None:
        # В их модели порядок как в Яндекс Картах: [долгота, широта].
        coordinates = [float(address.longitude), float(address.latitude)]

    return {
        "address": address.full_address if address is not None else "",
        # Адрес без геометки: координат нет, и метка на карте не ставится —
        # иначе она оказалась бы в точке 0, 0.
        "coordinates": coordinates,
        "upravaId": _uprava_id(db, case),
    }


def _organization(organization) -> dict | None:
    if organization is None:
        return None
    return {
        "id": str(organization.id),
        "name": organization.short_name or organization.name,
        "kind": "UK",
        "directorName": None,
        "phone": None,
        "email": None,
    }


def _responsibles(db: Session, case: ControlCase) -> list[dict]:
    """Ответственные: у нас это одна организация по заявке."""

    organization = case.responsible_organization or case.controlled_organization
    if organization is None:
        return []
    violation = _violation(db, case)
    # Повторность: сколько нарушений по этому адресу уже было.
    recidivism = 0
    if violation is not None and violation.address_id is not None:
        recidivism = len(
            list(
                db.scalars(
                    select(Violation).where(
                        Violation.address_id == violation.address_id
                    )
                )
            )
        )
    return [
        {
            "role": RESPONSIBLE_ROLE,
            "organization": _organization(organization),
            "confirmed": True,
            "recidivismCount": recidivism,
        }
    ]


def _iso(moment: datetime | None) -> str | None:
    if moment is None:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).isoformat()


def _history(db: Session, case: ControlCase, limit: int = 20) -> list[dict]:
    """Хроника дела: журнал действий по заявке и её документам."""

    events: list[dict] = []
    rows = list(
        db.scalars(
            select(AuditLog)
            .where(
                (AuditLog.entity_table == "control_cases")
                & (AuditLog.entity_id == case.id)
            )
            .order_by(AuditLog.id.desc())
            .limit(limit)
        )
    )
    for row in rows:
        events.append(
            {
                "id": str(row.id),
                "timestamp": _iso(row.created_at) or "",
                "title": row.action,
                "description": row.comment or "",
                "type": "INSPECTOR",
            }
        )
    return events


def _timeline(db: Session, case: ControlCase) -> dict:
    primary = _primary_inspection(db, case)
    violation = _violation(db, case)
    due_on = case_state.control_due_on(db, case)
    deadline = (
        datetime.combine(due_on, datetime.min.time(), tzinfo=timezone.utc)
        if isinstance(due_on, date)
        else None
    )
    closed_at = None
    resolution = None
    if violation is not None and violation.is_eliminated:
        closed_at = _iso(violation.eliminated_at) or _iso(case.actual_end_at)
        resolution = "FIXED"
    return {
        "createdAt": _iso(case.created_at) or "",
        "validatedAt": _iso(primary.started_at) if primary is not None else None,
        "deadlineAt": _iso(deadline),
        "closedAt": closed_at,
        "resolution": resolution,
        "history": _history(db, case),
    }


def _inspection_photo(inspection: ControlAction | None) -> str:
    """Снимок осмотра для карточки обращения.

    Отдаём исходный снимок: интерфейс диспетчера сам подписывает его — «обход
    инспектора», дата и время берутся из карточки осмотра, поэтому штамп с
    адресом и датой на самой картинке был бы вторым по счёту. Размеченная
    копия остаётся для документов и для нашего интерфейса.
    """

    if inspection is None:
        return ""
    original = inspections.photo_file(inspection, PhotoKind.ORIGINAL)
    marked = inspections.photo_file(inspection, PhotoKind.ANNOTATED)
    if original is None and marked is None:
        return ""
    kind = "original" if original is not None else "annotated"
    return f"/ui/inspections/{inspection.id}/photo/{kind}"


def _media(db: Session, case: ControlCase) -> dict:
    """Фотоматериал обращения.

    Первый обход — «было»: что зафиксировал инспектор. Второй — «стало»: что
    стало после устранения. Оба снимка маркируются адресом и датой осмотра,
    поэтому в карточке их можно сравнивать, а в документы они попадают с
    подписью.
    """

    primary = _primary_inspection(db, case)
    repeat = _repeat_inspection(db, case)
    after = _inspection_photo(repeat)

    # Интерфейс подписывает снимок «стало» данными фотоотчёта исполнителя,
    # поэтому отдаём его отдельно: время съёмки берётся из повторного осмотра,
    # иначе обе стороны сравнения подписывались бы временем первого обхода.
    report = None
    if repeat is not None and after:
        moment = repeat.started_at or repeat.created_at
        report = {
            "photoUrl": after,
            "takenAt": moment.isoformat() if moment is not None else None,
            "distanceM": None,
        }

    return {
        "photoBeforeUrl": _inspection_photo(primary),
        "photoAfterUrl": after or None,
        "report": report,
        "boundingBoxes": [],
    }


def incident(db: Session, case: ControlCase) -> dict:
    """Собирает обращение для интерфейса диспетчера."""

    primary = _primary_inspection(db, case)
    status = _status(db, case)
    return {
        "id": case.case_number or str(case.id),
        "status": status,
        "source": _source(case),
        "priority": _priority(db, case),
        "location": _location(db, case),
        "kp": None,
        "responsibles": _responsibles(db, case),
        "timeline": _timeline(db, case),
        "media": _media(db, case),
        # Поля сверх их контракта — для связки интерфейсов: адрес карточки в
        # сервисе документов и заведённое обследование. Их интерфейс лишние
        # поля игнорирует, а панель документов показывает ссылку.
        "serviceUrl": f"/ui/cases/{case.id}",
        "inspection": (
            {
                "id": primary.id,
                "startedAt": _iso(primary.started_at),
                "hasPhoto": inspections.photo_file(primary, PhotoKind.ANNOTATED)
                is not None
                or inspections.photo_file(primary, PhotoKind.ORIGINAL) is not None,
            }
            if primary is not None
            else None
        ),
        "knm": {
            "escalated": status == STATUS_ESCALATION,
            "dismissed": _marked(case, MARK_DISMISSED),
        },
    }


def _ready_package(db: Session, case: ControlCase) -> tuple[str | None, dict]:
    """Какой пакет собирается сейчас и что ему мешает.

    Правило выбора пакета общее с нашим интерфейсом
    (services/generation.available_packages), поэтому интерфейс диспетчера
    предлагает ровно те же документы.
    """

    available = generation.available_packages(db, case)
    if not available:
        return None, {"is_ready": False, "issues": [], "missing_templates": []}

    kind = available[0]["kind"]
    readiness = validation.check_readiness(db, case.id, kind.code)
    return kind.code, readiness.as_dict()


def _user_cases(db: Session) -> list[ControlCase]:
    statement = select(ControlCase).order_by(ControlCase.id.desc()).limit(200)
    statement = areas.visible_cases_statement(db, None, statement)
    return list(db.scalars(statement))


@router.get("")
def list_incidents(db: Session = Depends(get_db)) -> list[dict]:
    """Список обращений: все заявки, видимые текущему пользователю."""

    return [incident(db, case) for case in _user_cases(db)]


@router.get("/{incident_id}")
def get_incident(incident_id: str, db: Session = Depends(get_db)) -> dict:
    return incident(db, _find_case(db, incident_id))


@router.get("/{incident_id}/documents")
def incident_documents(incident_id: str, db: Session = Depends(get_db)) -> dict:
    """Документы последнего пакета и то, чего не хватает для сборки.

    Интерфейс диспетчера показывает это в карточке: список бланков с числом
    листов и причины, по которым пакет пока не собирается.
    """

    case = _find_case(db, incident_id)
    package = db.scalars(
        select(DocumentPackage)
        .where(DocumentPackage.control_case_id == case.id)
        .order_by(DocumentPackage.id.desc())
    ).first()

    documents: list[dict] = []
    if package is not None:
        rows = list(
            db.scalars(
                select(Document)
                .where(Document.package_id == package.id)
                .order_by(Document.id)
            )
        )
        for row in rows:
            document_type = db.get(DocumentType, row.document_type_id)
            documents.append(
                {
                    "id": row.id,
                    "code": document_type.code if document_type else "",
                    "title": document_type.name if document_type else "",
                    "number": row.number or "",
                    "issuedOn": row.document_date.isoformat()
                    if row.document_date
                    else None,
                    "pages": row.pages,
                    "downloadUrl": f"/api/documents/{row.id}/file",
                }
            )

    kind_code, readiness = _ready_package(db, case)
    missing = [issue["message"] for issue in readiness.get("issues", [])]
    missing += [
        f"нет шаблона документа: {code}"
        for code in readiness.get("missing_templates", [])
    ]

    return {
        "incidentId": case.case_number or str(case.id),
        "packageKind": kind_code,
        "packageId": package.id if package is not None else None,
        "builtAt": _iso(package.created_at) if package is not None else None,
        "archiveUrl": f"/api/packages/{package.id}/archive"
        if package is not None
        else None,
        "documents": documents,
        "canBuild": kind_code is not None and not missing,
        "missing": missing,
    }


@router.post("/{incident_id}/confirm")
def confirm_incident(
    incident_id: str, body: dict | None = Body(default=None), db: Session = Depends(get_db)
) -> dict:
    """Сигнал принят в работу: обращению ставится срок устранения.

    Срок выбирает инспектор в карточке (24, 48, 72 часа или 720 для «Дело-web»),
    и он же становится сроком исполнения заявки — по нему видно, когда
    спрашивать с исполнителя.
    """

    case = _find_case(db, incident_id)
    hours = (body or {}).get("deadlineHours") or 48
    try:
        hours = int(hours)
    except (TypeError, ValueError):
        hours = 48
    if hours not in DEADLINE_CHOICES:
        raise ApiError(
            status_code=422,
            message=(
                "Срок устранения выбирается из 24, 48, 72 часов или 720 часов"
            ),
        )

    moment = ru.to_display(datetime.now(timezone.utc))
    case.control_due_on = (moment + timedelta(hours=hours)).date()
    audit.record(
        db,
        actor=None,
        entity_table="control_cases",
        entity_id=case.id,
        action="update",
        comment=f"обращение принято в работу, срок устранения {hours} ч (интерфейс диспетчера)",
    )
    db.commit()
    return incident(db, case)


@router.post("/{incident_id}/dismiss")
def dismiss_incident(
    incident_id: str, body: dict | None = Body(default=None), db: Session = Depends(get_db)
) -> dict:
    """Сигнал признан ложным: дело закрывается без исполнителя."""

    case = _find_case(db, incident_id)
    reason = (body or {}).get("reason") or "причина не указана"
    _mark(db, case, MARK_DISMISSED)
    audit.record(
        db,
        actor=None,
        entity_table="control_cases",
        entity_id=case.id,
        action="update",
        comment=f"сигнал признан ложным: {reason} (интерфейс диспетчера)",
    )
    db.commit()
    return incident(db, case)


@router.post("/{incident_id}/approve")
def approve_incident(incident_id: str, db: Session = Depends(get_db)) -> dict:
    """Работа принята: нарушение считается устранённым."""

    case = _find_case(db, incident_id)
    violation = _violation(db, case)
    if violation is None:
        raise ApiError(
            status_code=409,
            message="По обращению не выявлено нарушение — принимать нечего",
        )
    violation.is_eliminated = True
    violation.eliminated_at = datetime.now(timezone.utc)
    audit.record(
        db,
        actor=None,
        entity_table="control_cases",
        entity_id=case.id,
        action="update",
        comment="нарушение признано устранённым (интерфейс диспетчера)",
    )
    db.commit()
    return incident(db, case)


@router.post("/{incident_id}/return")
def return_incident(
    incident_id: str, body: dict | None = Body(default=None), db: Session = Depends(get_db)
) -> dict:
    """Работа возвращена на доработку: срок не продлевается."""

    case = _find_case(db, incident_id)
    violation = _violation(db, case)
    if violation is None:
        raise ApiError(
            status_code=409, message="По обращению не выявлено нарушение"
        )
    violation.is_eliminated = False
    violation.eliminated_at = None
    comment = (body or {}).get("comment") or "без пояснения"
    audit.record(
        db,
        actor=None,
        entity_table="control_cases",
        entity_id=case.id,
        action="update",
        comment=f"работа возвращена на доработку: {comment} (интерфейс диспетчера)",
    )
    db.commit()
    return incident(db, case)


@router.post("/{incident_id}/escalate")
def escalate_incident(incident_id: str, db: Session = Depends(get_db)) -> dict:
    """Материалы переданы на КНМ — это и есть наше выездное обследование.

    Связка интерфейсов: инспектор в карточке обращения нажимает «Передать на
    КНМ», и по заявке заводится первичный осмотр — тот самый выход на объект,
    с которого начинается наш документооборот (фотоматериал, протокол осмотра,
    акт, предписание). Если осмотр уже заведён, второй не создаётся: материалы
    передаются по нему.
    """

    case = _find_case(db, incident_id)
    _mark(db, case, MARK_ESCALATED)

    created: ControlAction | None = None
    primary = _primary_inspection(db, case)
    if primary is None:
        allowed, reason = inspections.can_start(db, case.id, InspectionKind.PRIMARY)
        if not allowed:
            raise ApiError(status_code=409, message=reason)
        created = inspections.start(db, case, kind=InspectionKind.PRIMARY)

    audit.record(
        db,
        actor=None,
        entity_table="control_cases",
        entity_id=case.id,
        action="escalate",
        comment=(
            "материалы переданы на контрольно-надзорное мероприятие "
            "(интерфейс диспетчера)"
            + (f", заведено обследование №{created.id}" if created else "")
        ),
    )
    db.commit()
    if created is not None:
        # Осмотр завели: система сразу проставляет его длительность и даты
        # задания и решения — те же правила, что и при заведении из нашего
        # интерфейса.
        auto_dates.apply_after_inspection(db, case, created)
        db.commit()
    return incident(db, case)


@router.post("/{incident_id}/report")
def submit_report(incident_id: str) -> dict:
    """Фотоотчёт исполнителя.

    Отчёт присылает мастер управляющей компании из своего кабинета — это
    контур интерфейса диспетчера, у нас таких данных нет. Отвечаем понятной
    причиной, а не пустой ошибкой.
    """

    raise ApiError(
        status_code=409,
        message=(
            "Фотоотчёт исполнителя ведётся в интерфейсе диспетчера: "
            "в сервисе документов он не хранится"
        ),
    )


@router.post("/{incident_id}/act")
def issue_act(incident_id: str, request: Request, db: Session = Depends(get_db)) -> dict:
    """Сборка пакета документов по обращению.

    Это замена PDF-заглушке из интерфейса диспетчера: документы собираются
    нашим сервисом по официальным бланкам, с номерами и QR-кодом.
    """

    case = _find_case(db, incident_id)
    kind_code, readiness = _ready_package(db, case)
    if kind_code is None:
        raise ApiError(
            status_code=409,
            message=(
                "Пакет пока нельзя сформировать: по заявке ещё нет осмотра "
                "или для неё не настроен вид пакета документов"
            ),
        )

    problems = [issue["message"] for issue in readiness.get("issues", [])]
    problems += [
        f"нет шаблона документа: {code}"
        for code in readiness.get("missing_templates", [])
    ]
    if problems:
        raise ApiError(
            status_code=409,
            message="Пакет пока нельзя сформировать: " + "; ".join(problems),
        )

    result = generation.generate_package(db, case.id, package_kind_code=kind_code)
    if not result.missing_templates:
        package = db.get(DocumentPackage, result.package_id)
        if package is not None:
            actor = getattr(request.state, "user", None)
            crm_events.package_generated(
                case,
                package,
                len(result.created),
                actor_name=(actor.full_name if actor else None),
            )
    return incident(db, case)
