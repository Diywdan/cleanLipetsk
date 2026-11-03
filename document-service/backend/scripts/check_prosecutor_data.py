"""Проверка номера и QR-кода из прокуратуры.

Номер мероприятия и QR-код выдаёт портал прокуратуры: система их не создаёт.
Номер печатается в акте и предписании, QR-код — картинкой, подогнанной под
место, зарезервированное в бланке. Проверка отвечает на три вопроса:

* документы собираются без этих данных: в бланке пустое место, а не «None»;
* номер, внесённый в карточке, попадает в акт и предписание;
* загруженный QR-код печатается картинкой того же размера, что был в бланке.

Проверка идёт по демонстрационной заявке: данные о номере и коде она
возвращает на место, а временного пользователя удаляет.

Запуск внутри контейнера:
    PYTHONPATH=/app python scripts/check_prosecutor_data.py
"""

import http.cookiejar
import io
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from lxml import etree
from PIL import Image
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import (
    ControlCase,
    Document,
    DocumentPackage,
    DocumentType,
    Prescription,
    Role,
    User,
    UserRole,
)
from app.services import auth as auth_service
from app.services import generation, storage


BASE = "http://127.0.0.1:8000"
CASE_ID = 7
CHECK_EMAIL = "check-prosecutor@local"
CHECK_PASSWORD = "check-prosecutor-2026"
QR_NUMBER = "48009999999999999999"
# Размер QR-кода, зарезервированный в бланках: 3.39 см. В DOCX размер
# записан в EMU, поэтому сравниваем именно это число.
QR_EXTENT_EMU = str(int(generation.QR_CODE_SIZE_CM * 360000))

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
WP = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}"


def q(tag: str) -> str:
    return f"{W}{tag}"


def make_client():
    jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar)), jar


def multipart(fields: dict, files: dict) -> tuple[bytes, str]:
    """Собирает тело запроса с файлом так, как его отправил бы браузер."""

    boundary = "----check" + uuid.uuid4().hex
    body = b""
    for name, value in fields.items():
        body += (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'
        ).encode("utf-8")
    for name, (filename, content, mime) in files.items():
        body += (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
            f"Content-Type: {mime}\r\n\r\n"
        ).encode("utf-8")
        body += content + b"\r\n"
    body += f"--{boundary}--\r\n".encode("utf-8")
    return body, f"multipart/form-data; boundary={boundary}"


def upload(client, path: str, fields: dict, files: dict):
    body, content_type = multipart(fields, files)
    request = urllib.request.Request(
        BASE + path,
        data=body,
        method="POST",
        headers={"Content-Type": content_type},
    )
    try:
        with client.open(request, timeout=120) as response:
            return response.status, response.read().decode("utf-8", "replace"), response.url
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8", "replace"), error.url


def qr_image() -> bytes:
    """Простая картинка вместо кода прокуратуры: важны размер и встраивание."""

    image = Image.new("RGB", (300, 300), (255, 255, 255))
    for x in range(0, 300, 30):
        for y in range(0, 300, 30):
            if (x // 30 + y // 30) % 2 == 0:
                for dx in range(20):
                    for dy in range(20):
                        image.putpixel((x + dx, y + dy), (0, 0, 0))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def document_bytes(db, package_id: int, code: str) -> bytes:
    row = db.execute(
        select(Document)
        .join(DocumentType, Document.document_type_id == DocumentType.id)
        .where(Document.package_id == package_id, DocumentType.code == code)
    ).scalars().first()
    return storage.read_bytes(row.generated_file)


def document_text(data: bytes) -> str:
    document = etree.fromstring(
        __import__("zipfile").ZipFile(io.BytesIO(data)).read("word/document.xml")
    )
    return "".join(node.text or "" for node in document.iter(q("t")))


def qr_extents(data: bytes) -> list[str]:
    """Размеры картинок в документе: по ним видно, что QR встал на место."""

    import zipfile

    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        document = etree.fromstring(archive.read("word/document.xml"))
    sizes = []
    for drawing in document.iter(q("drawing")):
        extent = drawing.find(f"{WP}inline/{WP}extent")
        if extent is not None:
            sizes.append(extent.get("cx"))
    return sizes


def main() -> int:
    db = SessionLocal()
    failures: list[str] = []
    user_id = None
    case = db.get(ControlCase, CASE_ID)
    if case is None:
        print(f"нет демонстрационной заявки {CASE_ID}")
        return 1

    # Данные заявки, которые проверка меняет: вернём их на место в конце.
    saved_number, saved_qr = case.erp_number, case.qr_file_id

    try:
        user = db.scalar(select(User).where(User.email == CHECK_EMAIL))
        if user is not None:
            db.delete(user)
            db.commit()
        user = User(
            full_name="Проверка прокуратуры",
            email=CHECK_EMAIL,
            password_hash=auth_service.hash_password(CHECK_PASSWORD),
            is_active=True,
        )
        db.add(user)
        db.flush()
        role = db.scalar(select(Role).where(Role.code == "manager"))
        db.add(UserRole(user_id=user.id, role_id=role.id))
        db.commit()
        user_id = user.id

        client, _ = make_client()
        upload(client, "/ui/login", {"login": CHECK_EMAIL, "password": CHECK_PASSWORD}, {})

        # --- 1. Без номера и QR: в бланке пустое место, а не «None» --------
        case.erp_number = None
        case.qr_file_id = None
        db.commit()

        package = generation.generate_package(
            db, CASE_ID, package_kind_code="primary_prescription"
        )
        act = document_bytes(db, package.package_id, "act")
        prescription = document_bytes(db, package.package_id, "prescription")
        act_text = document_text(act)
        prescription_text = document_text(prescription)
        none_leaked = "None" in act_text or "None" in prescription_text
        qr_in_act = QR_EXTENT_EMU in qr_extents(act)
        qr_in_prescription = QR_EXTENT_EMU in qr_extents(prescription)
        print(
            f"--- без данных прокуратуры: пакет {package.package_id}, "
            f"«None» в тексте: {none_leaked}, QR в акте: {qr_in_act}, "
            f"QR в предписании: {qr_in_prescription}"
        )
        if none_leaked:
            failures.append("в документах печатается «None» вместо пустого номера")
        if qr_in_act or qr_in_prescription:
            failures.append("в документах остался нарисованный QR-код из бланка")

        # --- 2. Номер и QR вносит делопроизводитель через карточку --------
        image = qr_image()
        status, html, url = upload(
            client,
            f"/ui/cases/{CASE_ID}/prosecutor",
            {"erp_number": QR_NUMBER},
            {"qr": ("qr.png", image, "image/png")},
        )
        db.refresh(case)
        saved_ok = (
            case.erp_number == QR_NUMBER
            and case.qr_file_id is not None
            and case.qr_file is not None
            and case.qr_file.sha256 == storage.sha256_of(image)
        )
        print(
            f"--- загрузка через карточку: HTTP {status}, номер и файл сохранены: {saved_ok}"
        )
        if not saved_ok:
            failures.append("номер и QR-код из карточки не сохранились")

        # --- 3. Пакет заново: номер в тексте, QR нужного размера ----------
        rebuilt = generation.generate_package(
            db, CASE_ID, package_kind_code="primary_prescription"
        )
        act = document_bytes(db, rebuilt.package_id, "act")
        prescription = document_bytes(db, rebuilt.package_id, "prescription")
        act_text = document_text(act)
        prescription_text = document_text(prescription)
        in_act = QR_NUMBER in act_text
        in_prescription = QR_NUMBER in prescription_text
        qr_in_act = qr_extents(act).count(QR_EXTENT_EMU)
        qr_in_prescription = qr_extents(prescription).count(QR_EXTENT_EMU)
        print(
            f"--- после ввода: пакет {rebuilt.package_id}, номер в акте: {in_act}, "
            f"номер в предписании: {in_prescription}, "
            f"QR размера 3.39 см: акт {qr_in_act}, предписание {qr_in_prescription}"
        )
        if not in_act or not in_prescription:
            failures.append("номер мероприятия не попал в акт или предписание")
        if qr_in_act != 1 or qr_in_prescription != 1:
            failures.append("QR-код не встал в акт и предписание нужного размера")

        # --- 4. Убрать код: в бланке снова пустое место -------------------
        status, html, url = upload(
            client,
            f"/ui/cases/{CASE_ID}/prosecutor",
            {"erp_number": QR_NUMBER, "remove_qr": "1"},
            {},
        )
        db.refresh(case)
        removed = case.qr_file_id is None and case.erp_number == QR_NUMBER
        print(f"--- убрать QR-код: HTTP {status}, код снят: {removed}")
        if not removed:
            failures.append("QR-код не убирается из карточки")

        # --- 5. Уточнение номеров: свой номер у акта и у предписания ------
        # Номер мероприятия подставляется в оба документа, но каждый можно
        # поправить отдельно: поле номера акта и номер в карточке предписания.
        saved_act_number = case.act_number
        prescription = db.scalars(
            select(Prescription).where(Prescription.control_case_id == CASE_ID)
        ).first()
        saved_prescription_number = (
            prescription.number if prescription is not None else None
        )
        case.act_number = "АКТ-СВОЙ-НОМЕР"
        if prescription is not None:
            prescription.number = "ПРЕД-СВОЙ-НОМЕР"
        db.commit()

        corrected = generation.generate_package(
            db, CASE_ID, package_kind_code="primary_prescription"
        )
        act_text = document_text(document_bytes(db, corrected.package_id, "act"))
        prescription_text = document_text(
            document_bytes(db, corrected.package_id, "prescription")
        )
        act_own = "АКТ-СВОЙ-НОМЕР" in act_text and QR_NUMBER not in act_text
        prescription_own = "ПРЕД-СВОЙ-НОМЕР" in prescription_text
        print(
            f"--- уточнение номеров: пакет {corrected.package_id}, "
            f"у акта свой номер: {act_own}, у предписания свой: {prescription_own}"
        )
        if not act_own:
            failures.append("свой номер акта не печатается в акте")
        if not prescription_own:
            failures.append("свой номер предписания не печатается в предписании")

        case.act_number = saved_act_number
        if prescription is not None:
            prescription.number = saved_prescription_number
        db.commit()

        print("=== итог ===")
        if failures:
            for failure in failures:
                print("  ОШИБКА:", failure)
            return 1
        print("  номер и QR-код из прокуратуры работают, без них документы собираются")
        return 0
    finally:
        case = db.get(ControlCase, CASE_ID)
        if case is not None:
            case.erp_number = saved_number
            case.qr_file_id = saved_qr
        db.commit()
        if user_id is not None:
            stored = db.get(User, user_id)
            if stored is not None:
                db.delete(stored)
            db.commit()
        print("данные заявки восстановлены, временный пользователь удалён")
        db.close()


if __name__ == "__main__":
    sys.exit(main())
