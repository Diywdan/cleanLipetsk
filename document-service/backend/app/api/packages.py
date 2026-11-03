"""Формирование пакетов документов и сведения о шаблонах."""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.dependencies import get_db
from app.models import (
    ControlCase,
    DocumentPackage,
    DocumentTemplate,
    DocumentType,
    PackageKind,
)
from app.schemas.api import DocumentTypeInfo, PackageDetail
from app.schemas.api import PackageGenerateRequest
from app.services import (
    archive,
    audit,
    crm_events,
    generation,
    package_details,
    validation,
)


router = APIRouter(tags=["packages"])


@router.post(
    "/cases/{case_id}/packages",
    response_model=PackageDetail,
    status_code=201,
)
def generate_package(
    case_id: int,
    body: PackageGenerateRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> PackageDetail:
    """Формирует пакет документов по контрольному мероприятию.

    Перед сборкой проверяется готовность дела: незаполненное поле дало бы
    пустое место в официальном документе.
    """

    if db.get(ControlCase, case_id) is None:
        raise HTTPException(status_code=404, detail=f"дело {case_id} не найдено")

    if not body.skip_validation:
        try:
            readiness = validation.check_readiness(
                db, case_id, body.package_kind, only_codes=body.only_codes
            )
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        if not readiness.is_ready:
            raise HTTPException(status_code=422, detail=readiness.as_dict())

    try:
        result = generation.generate_package(
            db,
            case_id,
            package_kind_code=body.package_kind,
            only_codes=body.only_codes,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    if result.missing_templates and not body.allow_incomplete:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "для части документов не зарегистрирован шаблон",
                "missing_templates": result.missing_templates,
                "package_id": result.package_id,
            },
        )

    package = db.get(DocumentPackage, result.package_id)
    audit.record(
        db,
        actor=getattr(request.state, "user", None),
        entity_table="document_packages",
        entity_id=result.package_id,
        action="generate",
        comment=(
            f"пакет {body.package_kind} по делу {case_id} через API: "
            f"документов {len(result.created)}"
        ),
    )
    db.commit()
    if not result.missing_templates:
        crm_events.package_generated(
            db.get(ControlCase, case_id),
            package,
            len(result.created),
            actor_name=(
                getattr(request.state, "user", None).full_name
                if getattr(request.state, "user", None)
                else None
            ),
        )
    return package_details.package_detail(db, package, result.missing_templates)


@router.get("/packages/{package_id}", response_model=PackageDetail)
def get_package(package_id: int, db: Session = Depends(get_db)) -> PackageDetail:
    package = db.get(DocumentPackage, package_id)
    if package is None:
        raise HTTPException(status_code=404, detail=f"пакет {package_id} не найден")
    return package_details.package_detail(db, package)


@router.get("/cases/{case_id}/packages", response_model=list[PackageDetail])
def list_packages(case_id: int, db: Session = Depends(get_db)) -> list[PackageDetail]:
    packages = db.scalars(
        select(DocumentPackage)
        .where(DocumentPackage.control_case_id == case_id)
        .order_by(DocumentPackage.id.desc())
    )
    return [package_details.package_detail(db, package) for package in packages]


@router.get("/document-types", response_model=list[DocumentTypeInfo])
def list_document_types(db: Session = Depends(get_db)) -> list[DocumentTypeInfo]:
    """Какие документы пакета готовы к формированию (есть ли шаблон)."""

    result: list[DocumentTypeInfo] = []
    for document_type in db.scalars(
        select(DocumentType).order_by(DocumentType.sort_order, DocumentType.code)
    ):
        versions = list(
            db.scalars(
                select(DocumentTemplate.version)
                .where(
                    DocumentTemplate.document_type_id == document_type.id,
                    DocumentTemplate.is_active.is_(True),
                )
                .order_by(DocumentTemplate.id)
            )
        )
        result.append(
            DocumentTypeInfo(
                code=document_type.code,
                name=document_type.name,
                uses_external_number=document_type.uses_external_number,
                template_versions=versions,
            )
        )
    return result


@router.get("/cases/{case_id}/readiness")
def case_readiness(
    case_id: int,
    package_kind: str = "primary_prescription",
    db: Session = Depends(get_db),
) -> dict:
    """Что мешает собрать пакет: незаполненные поля и отсутствующие шаблоны."""

    if db.get(ControlCase, case_id) is None:
        raise HTTPException(status_code=404, detail=f"дело {case_id} не найдено")
    try:
        readiness = validation.check_readiness(db, case_id, package_kind)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return readiness.as_dict()


@router.get("/packages/{package_id}/files")
def package_files(package_id: int, db: Session = Depends(get_db)) -> dict:
    """Список файлов пакета для сохранения в папку средствами браузера.

    Возвращает те же имена и ту же опись, что и архив: результат не зависит
    от того, скачал оператор ZIP или сохранил файлы в выбранную папку.
    """

    package = db.get(DocumentPackage, package_id)
    if package is None:
        raise HTTPException(status_code=404, detail=f"пакет {package_id} не найден")
    return archive.package_file_list(db, package)


@router.get("/packages/{package_id}/archive")
def download_archive(package_id: int, db: Session = Depends(get_db)) -> Response:
    """Пакет одним ZIP-архивом: папка по номеру дела, документы и опись."""

    package = db.get(DocumentPackage, package_id)
    if package is None:
        raise HTTPException(status_code=404, detail=f"пакет {package_id} не найден")
    data, filename = archive.build_package_archive(db, package)
    if not data:
        raise HTTPException(status_code=409, detail="в пакете нет сформированных файлов")
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/package-kinds")
def list_package_kinds(db: Session = Depends(get_db)) -> list[dict]:
    """Виды пакетов и их состав."""

    kinds = db.scalars(select(PackageKind).order_by(PackageKind.sort_order))
    return [
        {
            "code": kind.code,
            "name": kind.name,
            "documents": [item.document_type.code for item in kind.documents],
        }
        for kind in kinds
    ]
