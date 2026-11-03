"""Документы пакета: скачивание файла и снимок данных."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db.dependencies import get_db
from app.models import DataSnapshot, Document
from app.services import archive, storage


router = APIRouter(prefix="/documents", tags=["documents"])

DOCX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)


@router.get("/{document_id}/file")
def download_document(document_id: int, db: Session = Depends(get_db)) -> FileResponse:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail=f"документ {document_id} не найден")
    if document.generated_file is None:
        raise HTTPException(status_code=409, detail="у документа нет файла")

    path = storage.absolute_path(document.generated_file.storage_path)
    if not path.exists():
        raise HTTPException(status_code=410, detail="файл отсутствует в хранилище")

    return FileResponse(
        path,
        media_type=document.generated_file.mime_type or DOCX_MEDIA_TYPE,
        filename=archive.document_filename(document),
    )


@router.get("/{document_id}")
def get_document(document_id: int, db: Session = Depends(get_db)) -> dict:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail=f"документ {document_id} не найден")
    return {
        "id": document.id,
        "package_id": document.package_id,
        "code": document.document_type.code,
        "name": document.document_type.name,
        "number": document.number,
        "document_date": document.document_date,
        "status": document.status.code if document.status else None,
        "template": (
            {
                "code": document.template.code,
                "version": document.template.version,
                "sha256": document.template.file.sha256
                if document.template.file
                else None,
            }
            if document.template
            else None
        ),
        "pages": document.pages,
        "generated_at": document.generated_at,
        "file": (
            {
                "id": document.generated_file.id,
                "name": document.generated_file.original_name,
                "size_bytes": document.generated_file.size_bytes,
                "sha256": document.generated_file.sha256,
                "storage_path": document.generated_file.storage_path,
            }
            if document.generated_file
            else None
        ),
        "snapshot_id": document.snapshot_id,
        "download_url": f"/api/documents/{document.id}/file",
    }


@router.get("/{document_id}/snapshot")
def get_document_snapshot(
    document_id: int, db: Session = Depends(get_db)
) -> dict:
    """Снимок данных, из которого собран документ.

    По нему документ можно пересобрать: значения не зависят от текущего
    состояния справочников.
    """

    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail=f"документ {document_id} не найден")
    snapshot = db.get(DataSnapshot, document.snapshot_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="у документа нет снимка")
    return {
        "id": snapshot.id,
        "entity_kind": snapshot.entity_kind.value,
        "schema_version": snapshot.schema_version,
        "sha256": snapshot.sha256,
        "created_at": snapshot.created_at,
        "payload": snapshot.payload,
    }
