"""API дел для Диспетчерской (Oxana48/cleanLipetsk, docs/api-contract.md).

Пути и тела — как в контракте фронта: GET /incidents и POST /incidents/{id}/<действие>,
в ответе дело целиком. Права и переходы проверяет app/workflow.py.
"""

from __future__ import annotations

import html
import hmac
import re
from collections import Counter
from collections.abc import Callable
from typing import Any
from urllib.parse import urljoin, urlsplit

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import document_service, files, kp, media, workflow
from app.api.deps import require
from app.config import get_settings
from app.db import get_session, utc_now
from app.domain import audit, incident_view
from app.models import Case, CaseHistory, Executor, Kp, User, ViolationType
from app.schemas import (
    ConfirmIn,
    DismissIn,
    DocumentServiceDataIn,
    DocumentServiceFileLink,
    DocumentServiceGeneratedEvent,
    EmptyIn,
    ReportIn,
    ReturnIn,
)

router = APIRouter(prefix="/api/v1", tags=["incidents"])
READ = require("cases.read")
DS_DOCUMENT_PATH = re.compile(r"^/api/documents/\d+/file$")
PRIMARY_DOCUMENT_CODES = {"assignment", "decision"}


def _readiness_with_knm_package(
    readiness: dict[str, Any] | None,
    current: dict[str, Any] | None,
    package: dict[str, Any] | None = None,
    primary_package: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if readiness is None and not current and package is None and primary_package is None:
        return None
    result = dict(readiness or {})
    existing_package = current.get("knm_package") if current else None
    existing_primary_package = current.get("primary_package") if current else None
    if package is not None:
        result["knm_package"] = package
    elif existing_package is not None:
        result["knm_package"] = existing_package
    if primary_package is not None:
        result["primary_package"] = primary_package
    elif existing_primary_package is not None:
        result["primary_package"] = existing_primary_package
    return result


def _document_service_public_base() -> str | None:
    value = get_settings().document_service_public_url.strip()
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        return None
    return value.rstrip("/")


def _knm_package_from_response(package: Any, status: str) -> dict[str, Any]:
    if not isinstance(package, dict) or not isinstance(package.get("id"), int):
        raise HTTPException(
            status_code=502,
            detail="Сервис документов вернул некорректные данные сформированного пакета",
        )
    documents = package.get("documents")
    if not isinstance(documents, list):
        raise HTTPException(
            status_code=502,
            detail="Сервис документов вернул некорректный список документов пакета КНМ",
        )
    normalized_documents = []
    for document in documents:
        if not isinstance(document, dict):
            raise HTTPException(
                status_code=502,
                detail="Сервис документов вернул некорректные метаданные документа",
            )
        code = document.get("code")
        name = document.get("name")
        path = document.get("download_url")
        if not isinstance(code, str) or not isinstance(name, str):
            raise HTTPException(
                status_code=502,
                detail="Сервис документов вернул неполные метаданные документа",
            )
        if not isinstance(path, str) or not DS_DOCUMENT_PATH.fullmatch(path):
            raise HTTPException(
                status_code=502,
                detail="Сервис документов вернул некорректную ссылку на документ",
            )
        normalized_documents.append({
            "code": code,
            "name": name,
            "download_path": path,
        })
    return {
        "status": package.get("status") or status,
        "package_id": package["id"],
        "documents": normalized_documents,
    }


def _knm_package_view(case: Case) -> dict[str, Any] | None:
    readiness = case.document_service_readiness or {}
    package = readiness.get("knm_package")
    if not isinstance(package, dict):
        return None
    documents = package.get("documents")
    if not isinstance(documents, list):
        return None

    public_base = _document_service_public_base()
    public_url = f"{public_base}/" if public_base else ""

    view_documents = []
    seen_codes: set[str] = set()
    seen_names: set[str] = set()
    seen_paths: set[str] = set()
    for document in documents:
        if not isinstance(document, dict):
            continue
        code = document.get("code")
        name = document.get("name")
        path = document.get("download_path")
        normalized_name = " ".join(name.split()).casefold() if isinstance(name, str) else ""
        # Задание и Решение показаны отдельным списком первичных документов.
        # Составной пакет сервиса документов содержит их повторно, поэтому
        # в разделе КНМ оставляем только документы самого этапа КНМ.
        if (
            code in {"assignment", "decision"}
            or (isinstance(code, str) and code in seen_codes)
            or (normalized_name and normalized_name in seen_names)
            or (isinstance(path, str) and path in seen_paths)
        ):
            continue
        if isinstance(code, str):
            seen_codes.add(code)
        if normalized_name:
            seen_names.add(normalized_name)
        if isinstance(path, str):
            seen_paths.add(path)
        download_url = None
        if isinstance(path, str) and DS_DOCUMENT_PATH.fullmatch(path) and public_url:
            download_url = urljoin(public_url, path.lstrip("/"))
        view_documents.append({
            "code": code,
            "name": name,
            "downloadUrl": download_url,
        })
    return {
        "status": package.get("status"),
        "packageId": package.get("package_id"),
        "documents": view_documents,
    }


def _primary_package_from_response(package: Any) -> dict[str, Any] | None:
    if package is None:
        return None
    if not isinstance(package, dict) or not isinstance(package.get("id"), int):
        raise HTTPException(
            status_code=502,
            detail="Сервис документов вернул некорректные данные пакета Задания и Решения",
        )
    documents = package.get("documents")
    if not isinstance(documents, list):
        raise HTTPException(
            status_code=502,
            detail="Сервис документов вернул некорректный список документов Задания и Решения",
        )
    normalized_documents = []
    for document in documents:
        if not isinstance(document, dict):
            raise HTTPException(status_code=502, detail="Сервис документов вернул некорректный документ")
        document_id = document.get("id")
        code = document.get("code")
        name = document.get("name")
        path = document.get("download_url")
        if code not in PRIMARY_DOCUMENT_CODES:
            continue
        if (
            not isinstance(document_id, int)
            or not isinstance(code, str)
            or not isinstance(name, str)
            or not isinstance(path, str)
            or not DS_DOCUMENT_PATH.fullmatch(path)
            or path != f"/api/documents/{document_id}/file"
        ):
            raise HTTPException(
                status_code=502,
                detail="Сервис документов вернул некорректную ссылку на документ",
            )
        normalized_documents.append({
            "id": document_id,
            "code": code,
            "name": name,
            "download_path": path,
        })
    return {
        "status": "generated",
        "package_id": package["id"],
        "documents": normalized_documents,
    }


def _primary_package_view(case: Case) -> dict[str, Any] | None:
    readiness = case.document_service_readiness or {}
    package = readiness.get("primary_package")
    if not isinstance(package, dict) or not isinstance(package.get("documents"), list):
        return None
    documents = []
    for document in package["documents"]:
        if not isinstance(document, dict):
            continue
        code = document.get("code")
        if code not in PRIMARY_DOCUMENT_CODES:
            continue
        document_id = document.get("id")
        path = document.get("download_path")
        valid_path = (
            isinstance(document_id, int)
            and path == f"/api/documents/{document_id}/file"
        )
        documents.append({
            "code": code,
            "name": document.get("name"),
            "downloadUrl": (
                f"/api/v1/incidents/{case.id}/document-service/launch?document_id={document_id}"
                if valid_path
                else None
            ),
        })
    return {
        "status": package.get("status"),
        "packageId": package.get("package_id"),
        "documents": documents,
    }


def _record_primary_documents_generated(
    db: Session,
    case: Case,
    package: dict[str, Any] | None,
    occurred_at=None,
) -> None:
    if not isinstance(package, dict):
        return
    package_id = package.get("package_id")
    documents = package.get("documents")
    if not isinstance(package_id, int) or not isinstance(documents, list):
        return
    document_codes = {
        document.get("code")
        for document in documents
        if isinstance(document, dict)
    }
    if not {"assignment", "decision"}.issubset(document_codes):
        return

    event_id = f"document-package:{package_id}:generated"
    event = db.scalar(
        select(CaseHistory).where(CaseHistory.external_event_id == event_id)
    )
    if event is not None and event.case_id != case.id:
        raise HTTPException(status_code=409, detail="Идентификатор события уже использован")

    confirmation = db.scalar(
        select(CaseHistory)
        .where(CaseHistory.case_id == case.id, CaseHistory.action == "CONFIRM")
        .order_by(CaseHistory.at.desc(), CaseHistory.id.desc())
    )
    approver_name = (confirmation.actor_name if confirmation else None) or "не указан"
    if event is None:
        event = CaseHistory(
            at=occurred_at or utc_now(),
            action="DOCUMENTS_GENERATED",
            external_event_id=event_id,
        )
        case.history.append(event)
    event.title = "Задание и Решение сформированы"
    event.description = (
        f"Муниципальный служащий {approver_name} утвердил инцидент. "
        "Сгенерированы внутренние Задание и Решение."
    )
    event.actor_type = "SYSTEM"
    event.actor_name = approver_name
    db.flush()


@router.post("/internal/document-service/events", status_code=201)
def document_service_event(
    body: DocumentServiceGeneratedEvent,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_session),
) -> dict:
    """Принимает подписанное общим секретом событие о сформированном пакете."""
    expected = get_settings().document_service_token.get_secret_value()
    supplied = authorization.removeprefix("Bearer ") if authorization else ""
    if len(expected) < 32 or not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="Недействительный токен интеграции")

    if not body.crm_case_id.isdigit():
        raise HTTPException(status_code=404, detail="Дело CRM не найдено")
    case = db.get(Case, int(body.crm_case_id), with_for_update=True)
    if case is None or case.document_service_case_id != body.document_case_id:
        raise HTTPException(status_code=404, detail="Связанное дело CRM не найдено")

    confirmation = db.scalar(
        select(CaseHistory)
        .where(CaseHistory.case_id == case.id, CaseHistory.action == "CONFIRM")
        .order_by(CaseHistory.at.desc(), CaseHistory.id.desc())
    )
    approver_name = (
        (confirmation.actor_name if confirmation else None)
        or body.actor_name
        or "не указан"
    )
    extended = body.event_id.endswith(":extended")
    is_primary_package = (
        not extended
        and {"assignment", "decision"}.issubset(set(body.document_codes))
    )
    if is_primary_package:
        generated_docs = "Сгенерированы внутренние Задание и Решение."
    elif body.document_names:
        generated_docs = (
            "Сгенерированы документы: "
            + ", ".join(body.document_names)
            + "."
        )
    else:
        generated_docs = f"Сформировано документов: {body.documents_count}."
    description = (
        f"Сформирован пакет КНМ №{body.package_id}."
        if extended
        else f"Муниципальный служащий {approver_name} утвердил инцидент. {generated_docs}"
    )

    existing = db.scalar(
        select(CaseHistory).where(CaseHistory.external_event_id == body.event_id)
    )
    if existing is not None and existing.case_id != case.id:
        raise HTTPException(status_code=409, detail="Идентификатор события уже использован")

    case.document_service_status = "generated"
    if extended or body.documents:
        readiness = case.document_service_readiness or {}
        package_key = "knm_package" if extended else "primary_package"
        current_package = readiness.get(package_key)
        previous_documents = (
            current_package.get("documents", [])
            if isinstance(current_package, dict)
            and current_package.get("package_id") == body.package_id
            else []
        )
        previous_by_code = {
            document.get("code"): document
            for document in previous_documents
            if isinstance(document, dict) and isinstance(document.get("code"), str)
        } if isinstance(previous_documents, list) else {}
        event_documents = {document.code: document for document in body.documents}
        documents = []
        for index, code in enumerate(body.document_codes):
            document: dict[str, Any] = {"code": code}
            if index < len(body.document_names):
                document["name"] = body.document_names[index]
            supplied = event_documents.get(code)
            previous = previous_by_code.get(code, {})
            if supplied is not None:
                document.update({"id": supplied.id, "name": supplied.name, "download_path": supplied.download_url})
            elif previous.get("download_path"):
                document["id"] = previous.get("id")
                document["download_path"] = previous["download_path"]
            documents.append(document)
        case.document_service_readiness = _readiness_with_knm_package(
            None,
            case.document_service_readiness,
            {
                "status": "generated",
                "package_id": body.package_id,
                "documents": documents,
            } if extended else None,
            {
                "status": "generated",
                "package_id": body.package_id,
                "documents": documents,
            } if not extended else None,
        )
    if existing is None:
        existing = CaseHistory(
            at=body.occurred_at,
            action="DOCUMENTS_GENERATED",
            external_event_id=body.event_id,
        )
        case.history.append(existing)
    existing.action = "KNM_PACKAGE_GENERATED" if extended else "DOCUMENTS_GENERATED"
    existing.title = (
        f"Пакет №{body.package_id} сформирован"
        if extended
        else "Задание и Решение сформированы"
        if is_primary_package
        else "Документы сформированы"
    )
    existing.at = body.occurred_at
    existing.description = description
    existing.actor_type = "SYSTEM"
    existing.actor_name = "Сервис документов" if extended else approver_name
    return {"accepted": True, "duplicate": existing.id is not None}


def _file_url(request: Request) -> Callable[[str], str]:
    # Путь без хоста: за внешним nginx (https, другое имя) абсолютная ссылка указывала бы внутрь ЦОД
    return lambda name: request.url_for("get_file", name=name).path


def _visible(db: Session, user: User, case_id: int, lock: bool = False) -> Case:
    case = db.get(Case, case_id, with_for_update=lock)
    # Исполнитель видит только дела своей организации; чужое — как несуществующее
    if case is None or (user.executor_id and case.executor_id != user.executor_id):
        raise HTTPException(status_code=404, detail="Дело не найдено")
    return case


def _repeats(db: Session, addresses: set[str]) -> Counter:
    """Повторность: сколько ещё дел заведено по тому же адресу."""
    if not addresses:
        return Counter()
    rows = db.execute(
        select(Case.address, func.count()).where(Case.address.in_(addresses)).group_by(Case.address)
    ).all()
    return Counter({address: count - 1 for address, count in rows})


def _media_url(request: Request) -> Callable[[int, int], str]:
    return lambda case_id, index: request.url_for("get_case_media", case_id=case_id, index=index).path


def _kp_link(case: Case, card: Kp | None) -> dict[str, Any] | None:
    if not case.kp_id or card is None:
        return None
    return {
        "kpId": case.kp_id,
        "code": card.code,
        **({"registryNumber": card.registry_number} if card.registry_number else {}),
        "score": case.kp_score if case.kp_score is not None else 0.0,
        "method": case.kp_method or "manual",
    }


def _views(db: Session, cases: list[Case], request: Request) -> list[dict[str, Any]]:
    executors = {x.executor_id: x for x in db.scalars(select(Executor))}
    types = {t.type_violation_id: t for t in db.scalars(select(ViolationType))}
    repeats = _repeats(db, {c.address for c in cases if c.address})
    kp_ids = {c.kp_id for c in cases if c.kp_id}
    cards = {k.kp_id: k for k in db.scalars(select(Kp).where(Kp.kp_id.in_(kp_ids)))} if kp_ids else {}
    to_url, to_media = _file_url(request), _media_url(request)
    result = []
    for case in cases:
        item = incident_view(
            case,
            executors.get(case.executor_id),
            types.get(case.type_violation_id),
            repeats.get(case.address, 0) if case.address else 0,
            to_url,
            to_media,
            _kp_link(case, cards.get(case.kp_id)),
        )
        if (
            case.document_service_status
            or case.document_service_case_id
            or case.document_service_readiness
        ):
            public_url = _document_service_public_base()
            item["document_service"] = {
                "control_case_id": case.document_service_case_id,
                "status": case.document_service_status,
                "readiness": case.document_service_readiness,
                "url": (
                    f"{public_url}/ui/cases/{case.document_service_case_id}"
                    if public_url and case.document_service_case_id
                    else None
                ),
            }
        item["knmPackage"] = _knm_package_view(case)
        item["primaryPackage"] = _primary_package_view(case)
        result.append(item)
    return result


@router.get("/incidents")
def list_incidents(request: Request, status: str | None = None, db: Session = Depends(get_session),
                   user: User = Depends(READ)) -> list[dict]:
    query = select(Case)
    if status:
        query = query.where(Case.status == status)
    if user.executor_id:
        query = query.where(Case.executor_id == user.executor_id)
    cases = list(db.scalars(query.order_by(Case.created_at.desc(), Case.id.desc())))
    return _views(db, cases, request)


@router.get("/incidents/{case_id}")
def get_incident(case_id: int, request: Request, db: Session = Depends(get_session),
                 user: User = Depends(READ)) -> dict:
    return _views(db, [_visible(db, user, case_id)], request)[0]


def _act(db: Session, user: User, request: Request, case_id: int, action: str, payload: dict[str, Any]) -> dict:
    case = _visible(db, user, case_id, lock=True)
    workflow.apply_action(db, case, action, payload, user)
    if action == "CONFIRM" and payload.get("type_violation_id"):
        kp.link_case(db, case)  # инспектор сменил тип — площадка может стать (не)нужной
    db.flush()
    result = _views(db, [case], request)[0]
    if action == "CONFIRM":
        sync_result = _sync_document_service(db, case, optional=True)
        if sync_result is not None:
            result = _views(db, [case], request)[0]
    return result


def _sync_document_service(
    db: Session,
    case: Case,
    optional: bool = False,
    document_data: dict[str, Any] | None = None,
) -> dict | None:
    try:
        sync_result = document_service.sync_confirmed_case(
            case,
            document_data,
            check_knm_readiness=case.status == "KNM_ESCALATION",
        )
    except RuntimeError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    if sync_result is None:
        if optional:
            return None
        raise HTTPException(status_code=409, detail="Интеграция с сервисом документов не настроена")
    case.document_service_case_id = sync_result.get("control_case_id")
    case.document_service_status = sync_result.get("status")
    primary_package = _primary_package_from_response(sync_result.get("primary_package"))
    case.document_service_readiness = _readiness_with_knm_package(
        sync_result.get("readiness"),
        case.document_service_readiness,
        primary_package=primary_package,
    )
    _record_primary_documents_generated(db, case, primary_package)
    db.flush()
    public_base = _document_service_public_base()
    return {
        "control_case_id": case.document_service_case_id,
        "status": case.document_service_status,
        "readiness": case.document_service_readiness,
        "primaryPackage": _primary_package_view(case),
        "url": (
            f"{public_base}/ui/cases/{case.document_service_case_id}"
            if public_base and case.document_service_case_id
            else None
        ),
    }


@router.post("/incidents/{case_id}/document-service/sync")
def sync_document_service(
    case_id: int,
    request: Request,
    db: Session = Depends(get_session),
    user: User = Depends(require("cases.inspect")),
) -> dict:
    case = _visible(db, user, case_id, lock=True)
    _sync_document_service(db, case)
    return _views(db, [case], request)[0]


@router.get("/incidents/{case_id}/document-service/options")
def document_service_options(
    case_id: int,
    db: Session = Depends(get_session),
    user: User = Depends(require("cases.inspect")),
) -> dict:
    case = _visible(db, user, case_id)
    try:
        return document_service.get_case_options(case)
    except RuntimeError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@router.get("/incidents/{case_id}/document-service/launch", response_class=HTMLResponse)
def launch_document_service(
    case_id: int,
    request: Request,
    field: str | None = Query(default=None, max_length=100),
    document_id: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_session),
    user: User = Depends(require("cases.inspect")),
) -> HTMLResponse:
    case = _visible(db, user, case_id)
    if not case.document_service_case_id:
        raise HTTPException(status_code=409, detail="Мероприятие сервиса документов ещё не связано с делом")

    if document_id is not None:
        primary_package = (case.document_service_readiness or {}).get("primary_package")
        documents = primary_package.get("documents", []) if isinstance(primary_package, dict) else []
        if not any(
            isinstance(document, dict)
            and document.get("id") == document_id
            and document.get("download_path") == f"/api/documents/{document_id}/file"
            for document in documents
        ):
            raise HTTPException(status_code=404, detail="Документ не найден в пакете этого дела")

    service_url = _document_service_public_base()
    if not service_url:
        raise HTTPException(status_code=503, detail="Адрес сервиса документов не настроен")
    try:
        ticket = document_service.create_sso_ticket(
            case, user, issue_field=field, document_id=document_id
        )
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error

    action = f"{service_url}/ui/sso/consume"
    origin = urlsplit(service_url)
    form_action = html.escape(action, quote=True)
    safe_ticket = html.escape(ticket, quote=True)
    content = f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="referrer" content="no-referrer">
<title>Переход в сервис документов</title></head><body>
<p>Выполняется безопасный вход в сервис документов…</p>
<form id="sso" method="post" action="{form_action}">
  <input type="hidden" name="ticket" value="{safe_ticket}">
  <noscript><button type="submit">Продолжить</button></noscript>
</form><script>document.getElementById('sso').submit();</script>
</body></html>"""
    return HTMLResponse(
        content,
        headers={
            "Cache-Control": "no-store",
            "Referrer-Policy": "no-referrer",
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Content-Security-Policy": (
                f"default-src 'none'; script-src 'unsafe-inline'; "
                f"form-action {origin.scheme}://{origin.netloc}; base-uri 'none'; frame-ancestors 'none'"
            ),
        },
    )


@router.post("/incidents/{case_id}/document-service/data")
def save_document_service_data(
    case_id: int,
    body: DocumentServiceDataIn,
    request: Request,
    db: Session = Depends(get_session),
    user: User = Depends(require("cases.inspect")),
) -> dict:
    case = _visible(db, user, case_id, lock=True)
    _sync_document_service(
        db,
        case,
        document_data=body.model_dump(mode="json", exclude_unset=True),
    )
    return _views(db, [case], request)[0]


@router.post("/incidents/{case_id}/confirm")
def confirm(case_id: int, body: ConfirmIn, request: Request, db: Session = Depends(get_session),
            user: User = Depends(READ)) -> dict:
    return _act(db, user, request, case_id, "CONFIRM", body.model_dump())


@router.post("/incidents/{case_id}/dismiss")
def dismiss(case_id: int, body: DismissIn, request: Request, db: Session = Depends(get_session),
            user: User = Depends(READ)) -> dict:
    return _act(db, user, request, case_id, "DISMISS", body.model_dump())


@router.post("/incidents/{case_id}/report")
def report(case_id: int, body: ReportIn, request: Request, db: Session = Depends(get_session),
           user: User = Depends(READ)) -> dict:
    case = _visible(db, user, case_id, lock=True)
    # Права и статус — до сохранения фото, чтобы отказ не оставлял файлов-сирот
    denied = workflow.deny_reason("SUBMIT_REPORT", case, user, utc_now())
    if denied:
        raise HTTPException(status_code=denied[0], detail=denied[1])
    r = body.report
    stored = {
        "file": files.resolve_photo(r.photo_url),
        "taken_at": (r.taken_at or utc_now()).isoformat(),
        "coords": list(r.coords) if r.coords else None,
        "comment": r.comment,
    }
    return _act(db, user, request, case_id, "SUBMIT_REPORT", {"report": stored})


@router.post("/incidents/{case_id}/approve")
def approve(case_id: int, request: Request, body: EmptyIn | None = None, db: Session = Depends(get_session),
            user: User = Depends(READ)) -> dict:
    return _act(db, user, request, case_id, "APPROVE", {})


@router.post("/incidents/{case_id}/return")
def return_to_work(case_id: int, body: ReturnIn, request: Request, db: Session = Depends(get_session),
                   user: User = Depends(READ)) -> dict:
    return _act(db, user, request, case_id, "RETURN", body.model_dump())


@router.post("/incidents/{case_id}/escalate")
def escalate(case_id: int, request: Request, body: EmptyIn | None = None, db: Session = Depends(get_session),
             user: User = Depends(READ)) -> dict:
    return _act(db, user, request, case_id, "ESCALATE", {})


@router.post("/incidents/{case_id}/act")
def issue_act(case_id: int, request: Request, body: EmptyIn | None = None, db: Session = Depends(get_session),
              user: User = Depends(require("cases.inspect"))) -> dict:
    case = _visible(db, user, case_id)
    denied = workflow.deny_reason("ISSUE_ACT", case, user, utc_now())
    if denied:
        raise HTTPException(status_code=denied[0], detail=denied[1])
    if not case.document_service_case_id:
        raise HTTPException(
            status_code=409,
            detail="Мероприятие сервиса документов ещё не связано с делом",
        )

    # Release the read transaction before document-service sends its synchronous callback.
    db.commit()
    try:
        generated = document_service.continue_knm_package(case)
    except RuntimeError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error

    db.expire_all()
    case = _visible(db, user, case_id, lock=True)
    denied = workflow.deny_reason("ISSUE_ACT", case, user, utc_now())
    if denied:
        raise HTTPException(status_code=denied[0], detail=denied[1])

    readiness = generated.get("readiness")
    case.document_service_status = generated.get("status")
    case.document_service_readiness = _readiness_with_knm_package(
        readiness,
        case.document_service_readiness,
    )
    if generated.get("status") not in {"generated", "needs_input"}:
        raise HTTPException(
            status_code=502,
            detail="Сервис документов вернул неизвестный статус пакета КНМ",
        )
    if not isinstance(readiness, dict):
        raise HTTPException(
            status_code=502,
            detail="Сервис документов вернул некорректные данные готовности пакета КНМ",
        )
    if generated.get("status") != "generated":
        db.commit()
        raise HTTPException(
            status_code=422,
            detail="Пакет КНМ не сформирован. Обратите внимание на замечания",
        )

    package = generated.get("package")
    knm_package = _knm_package_from_response(package, generated["status"])
    case.document_service_readiness = _readiness_with_knm_package(
        readiness,
        case.document_service_readiness,
        knm_package,
    )
    package_id = knm_package["package_id"]

    event_id = f"document-package:{package_id}:extended"
    existing = db.scalar(
        select(CaseHistory).where(CaseHistory.external_event_id == event_id)
    )
    if existing is not None and existing.case_id != case.id:
        raise HTTPException(status_code=409, detail="Идентификатор события уже использован")
    if existing is None:
        case.history.append(
            CaseHistory(
                at=utc_now(),
                action="KNM_PACKAGE_GENERATED",
                title=f"Пакет №{package_id} сформирован",
                description=f"Сформирован пакет КНМ №{package_id}.",
                actor_type="SYSTEM",
                actor_name="Сервис документов",
                external_event_id=event_id,
            )
        )
    audit(
        db,
        user.username,
        "case.issue_act",
        "case",
        str(case.id),
        status_from=case.status,
        status_to=case.status,
    )
    db.flush()
    return _views(db, [case], request)[0]


# --- Фото и видео нарушения (app/media.py) ---


@router.get("/incidents/{case_id}/media/{index}", name="get_case_media")
def get_case_media(case_id: int, index: int, db: Session = Depends(get_session), user: User = Depends(READ)):
    case = _visible(db, user, case_id)
    return media.response(db, case, case.media or [], index)


# --- Файлы фотоотчётов ---


@router.post("/files", status_code=201)
async def upload_file(request: Request, file: UploadFile = File(...),
                      user: User = Depends(require("cases.report"))) -> dict:
    data = await file.read(get_settings().max_upload_bytes + 1)
    name = files.save_image(data)
    return {"url": _file_url(request)(name)}


@router.get("/files/{name}", name="get_file")
def get_file(name: str, _: User = Depends(READ)) -> FileResponse:
    return FileResponse(files.path_of(name), media_type=files.media_type(name),
                        headers={"Cache-Control": "private, max-age=86400"})
