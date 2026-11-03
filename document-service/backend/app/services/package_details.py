"""Serialized package and document metadata shared by API responses."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Document, DocumentPackage
from app.schemas.api import DocumentInfo, PackageDetail


def document_info(document: Document) -> DocumentInfo:
    return DocumentInfo(
        id=document.id,
        code=document.document_type.code,
        name=document.document_type.name,
        number=document.number,
        document_date=document.document_date,
        template=(
            f"{document.template.code} {document.template.version}"
            if document.template
            else None
        ),
        pages=document.pages,
        file_id=document.generated_file_id,
        sha256=document.generated_file.sha256 if document.generated_file else None,
        size_bytes=(
            document.generated_file.size_bytes if document.generated_file else None
        ),
        snapshot_id=document.snapshot_id,
        download_url=f"/api/documents/{document.id}/file",
    )


def package_detail(
    db: Session, package: DocumentPackage, missing: list[str] | None = None
) -> PackageDetail:
    documents = list(
        db.scalars(
            select(Document)
            .where(Document.package_id == package.id)
            .order_by(Document.id)
        )
    )
    return PackageDetail(
        id=package.id,
        case_id=package.control_case_id,
        package_kind=package.package_kind.code,
        status=package.status.value,
        snapshot_id=package.snapshot_id,
        created_at=package.created_at,
        documents=[document_info(document) for document in documents],
        missing_templates=missing or [],
    )
