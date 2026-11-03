"""Выгрузка пакета: архивом и сохранением в папку.

Оператору нужен весь пакет сразу и в отдельной папке по номеру дела, поэтому
и архив, и сохранение в папку дают одинаковый результат: те же имена файлов
с порядковым номером и ту же опись. Отметки времени внутри архива фиксированы:
одинаковый пакет даёт одинаковый файл, его можно сравнить по контрольной сумме.
"""

import io
import json
import zipfile
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ControlCase, Document, DocumentPackage
from app.services import storage


FORBIDDEN_IN_NAME = '\\/:*?"<>|'
# Фиксированная отметка времени внутри архива (минимальная дата ZIP).
ZIP_DATE = (1980, 1, 1, 0, 0, 0)


def safe_name(value: str | None, fallback: str) -> str:
    """Имя файла без символов, запрещённых в Windows."""

    if not value:
        return fallback
    cleaned = value
    for character in FORBIDDEN_IN_NAME:
        cleaned = cleaned.replace(character, "-")
    cleaned = " ".join(cleaned.split()).strip(" .")
    return cleaned or fallback


def document_filename(document: Document) -> str:
    """Имя файла документа при скачивании по одному.

    В архиве имена нумеруются по порядку пакета, а при скачивании одного
    документа номер не нужен: имя собирается из названия документа, даты
    и номера — иначе оператор получал бы файл «act.docx».
    """

    parts = [safe_name(document.document_type.name, document.document_type.code)]
    if document.document_date is not None:
        parts.append(f"от {document.document_date.strftime('%d.%m.%Y')}")
    if document.number:
        parts.append(f"№ {document.number}")
    return f"{safe_name(' '.join(parts), document.document_type.code)}.docx"


def _document_entries(
    db: Session, package: DocumentPackage
) -> list[tuple[Document, str]]:
    """Документы пакета и имена их файлов — те же, что попадут в архив."""

    documents = list(
        db.scalars(
            select(Document)
            .where(Document.package_id == package.id)
            .order_by(Document.id)
        )
    )
    entries: list[tuple[Document, str]] = []
    for index, document in enumerate(documents, start=1):
        if document.generated_file is None:
            continue
        filename = (
            f"{index:02d}_"
            f"{safe_name(document.document_type.name, document.document_type.code)}.docx"
        )
        entries.append((document, filename))
    return entries


def _entry_meta(document: Document, filename: str, index: int) -> dict:
    """Описание документа для описи пакета."""

    return {
        "order": index,
        "code": document.document_type.code,
        "name": document.document_type.name,
        "file": filename,
        "number": document.number,
        "document_date": (
            document.document_date.isoformat() if document.document_date else None
        ),
        "template": (
            f"{document.template.code} {document.template.version}"
            if document.template
            else None
        ),
        "sha256": document.generated_file.sha256,
        "size_bytes": document.generated_file.size_bytes,
        "snapshot_id": document.snapshot_id,
    }


def _entries(db: Session, package: DocumentPackage) -> list[tuple[str, bytes, dict]]:
    entries: list[tuple[str, bytes, dict]] = []
    for index, (document, filename) in enumerate(
        _document_entries(db, package), start=1
    ):
        entries.append(
            (
                filename,
                storage.read_bytes(document.generated_file),
                _entry_meta(document, filename, index),
            )
        )
    return entries


def package_folder(db: Session, package: DocumentPackage) -> str:
    case = db.get(ControlCase, package.control_case_id)
    if case is not None and case.erp_number:
        return safe_name(case.erp_number, f"case-{package.control_case_id}")
    return f"case-{package.control_case_id}"


def _manifest(package: DocumentPackage, documents: list[dict]) -> dict:
    """Опись пакета — одинаковая и в архиве, и при сохранении в папку."""

    return {
        "package_id": package.id,
        "case_id": package.control_case_id,
        "package_kind": package.package_kind.code,
        "built_at": datetime.now().isoformat(timespec="seconds"),
        "snapshot_id": package.snapshot_id,
        "documents": documents,
    }


def build_package_archive(
    db: Session, package: DocumentPackage
) -> tuple[bytes, str]:
    """Собирает ZIP с документами пакета.

    Возвращает содержимое архива и имя файла для скачивания.
    """

    folder = package_folder(db, package)
    entries = _entries(db, package)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for filename, data, _ in entries:
            info = zipfile.ZipInfo(f"{folder}/{filename}", date_time=ZIP_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)

    return buffer.getvalue(), f"{folder}.zip"


def package_file_list(db: Session, package: DocumentPackage) -> dict:
    """Список файлов пакета для сохранения в папку средствами браузера.

    Файлы не читаются: браузер скачает их сам по ссылкам. Имена и опись те же,
    что в архиве, поэтому результат не зависит от способа выгрузки.
    """

    files = []
    documents = []
    for index, (document, filename) in enumerate(
        _document_entries(db, package), start=1
    ):
        meta = _entry_meta(document, filename, index)
        documents.append(meta)
        files.append(
            {
                "name": filename,
                "url": f"/api/documents/{document.id}/file",
                "document_id": document.id,
                "sha256": document.generated_file.sha256,
                "size_bytes": document.generated_file.size_bytes,
                "meta": meta,
            }
        )

    return {
        "package_id": package.id,
        "case_id": package.control_case_id,
        "folder": package_folder(db, package),
        "files": files,
    }
