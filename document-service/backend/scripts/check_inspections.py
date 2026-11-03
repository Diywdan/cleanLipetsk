"""Проверка осмотров: от кнопки в карточке до документов пакета.

Осмотр — отдельный шаг заявки, и проверять его надо не по отдельности,
а сцепкой:

* кнопка «Сделать осмотр» есть в карточке заявки (это путь оператора);
* повторный осмотр заводится копией первичного (место) и заканчивается
  результатом «устранено / устранено частично / не устранено»;
* фотография осмотра хранится двумя файлами — размеченной копией и
  исходным снимком, а надпись на ней содержит адрес и дату осмотра;
* документы пакета берут данные того осмотра, по которому собираются:
  первый пакет — первичного, вторичный — повторного, и в приложение
  к протоколу попадает только размеченный снимок этого осмотра.

Данные, которые проверка заводит, она же и убирает: демонстрационное дело
остаётся таким, каким было.

Запуск внутри контейнера:
    PYTHONPATH=/app python scripts/check_inspections.py
"""

import http.cookiejar
import io
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, time, timedelta

from PIL import Image
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import (
    ControlAction,
    ControlActionFile,
    ControlCase,
    Document,
    Role,
    User,
    UserRole,
)
from app.models.enums import FileKind, InspectionKind, InspectionResult, PhotoKind
from app.services import auth, generation, inspections, photo_marking, snapshots, storage
from app.services import ru


BASE = "http://127.0.0.1:8000"
CASE_ID = 7


def _local_date(value):
    local = ru.to_display(value)
    return local.date() if local is not None else None


def _post(opener, path: str, fields: dict) -> tuple[int, str]:
    """Отправляет форму так, как её отправил бы браузер."""

    request = urllib.request.Request(
        BASE + path,
        data=urllib.parse.urlencode(fields).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with opener.open(request, timeout=120) as response:
            return response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8", "replace")


def _get(opener, path: str) -> tuple[int, str]:
    """Открывает страницу так, как её открыл бы браузер."""

    try:
        with opener.open(BASE + path, timeout=120) as response:
            return response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8", "replace")


def _documents(db, package_id: int) -> dict[str, Document]:
    return {
        document.document_type.code: document
        for document in db.scalars(
            select(Document).where(Document.package_id == package_id)
        )
    }


def _login(db, email: str, password: str):
    user = db.scalar(select(User).where(User.email == email))
    if user is not None:
        db.delete(user)
        db.commit()
    user = User(
        full_name="Проверка осмотров",
        email=email,
        password_hash=auth.hash_password(password),
        is_active=True,
    )
    db.add(user)
    db.flush()
    role = db.scalar(select(Role).where(Role.code == "administrator"))
    db.add(UserRole(user_id=user.id, role_id=role.id))
    db.commit()

    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    opener.open(
        urllib.request.Request(
            f"{BASE}/ui/login",
            data=urllib.parse.urlencode({"login": email, "password": password}).encode(),
            method="POST",
        ),
        timeout=30,
    ).read()
    return user, opener


def main() -> int:
    db = SessionLocal()
    failures: list[str] = []
    repeat: ControlAction | None = None
    user: User | None = None
    try:
        case = db.get(ControlCase, CASE_ID)
        primary = inspections.primary(db, CASE_ID)
        if case is None or primary is None:
            print(f"нет дела {CASE_ID} или первичного осмотра в нём")
            return 1

        # --- Кнопка в карточке заявки: путь оператора --------------------
        # Кнопка показывается по состоянию: если первичного осмотра нет —
        # «Сделать осмотр», если первичный есть — «Сделать повторный осмотр»,
        # если оба сделаны — кнопки нет вовсе.
        for action in list(
            db.scalars(
                select(ControlAction).where(
                    ControlAction.control_case_id == CASE_ID,
                    ControlAction.inspection_kind == InspectionKind.REPEAT,
                )
            )
        ):
            db.delete(action)
        db.commit()

        email, password = "check-inspections@local", "check-inspections-2026"
        user, opener = _login(db, email, password)
        card = opener.open(f"{BASE}/ui/cases/{CASE_ID}", timeout=30).read().decode()

        available = inspections.available_kind(db, CASE_ID)
        expected_button = {
            InspectionKind.PRIMARY: "Сделать осмотр",
            InspectionKind.REPEAT: "Сделать повторный осмотр",
            None: None,
        }[available]
        button = expected_button is None or expected_button in card
        print(
            f"--- кнопка осмотра в карточке: "
            f"{expected_button or 'осмотры сделаны, кнопки нет'} → {button}"
        )
        if not button:
            failures.append(f"в карточке нет кнопки «{expected_button}»")

        # --- Первый пакет собирается по первичному осмотру ---------------
        first = generation.generate_package(
            db, CASE_ID, package_kind_code="primary_prescription"
        )
        first_docs = _documents(db, first.package_id)
        first_date = _local_date(primary.started_at)
        protocol = first_docs["inspection_protocol"]
        same = protocol.document_date == first_date
        print(
            f"--- первый пакет: документов {len(first_docs)}, "
            f"дата протокола {protocol.document_date} = дата первичного осмотра "
            f"{first_date}: {same}"
        )
        if not same:
            failures.append("протокол первичного пакета не взял дату первичного осмотра")

        # --- Повторный осмотр: копия первичного и результат ---------------
        repeat = inspections.start(db, case, kind=InspectionKind.REPEAT)
        moment = datetime.combine(
            (primary.started_at + timedelta(days=49)).astimezone(ru.DISPLAY_TZ).date(),
            time(10, 0),
            tzinfo=ru.DISPLAY_TZ,
        )
        repeat.started_at = moment
        repeat.ended_at = moment + timedelta(minutes=40)
        inspections.set_result(db, repeat, InspectionResult.NOT_FIXED)
        db.flush()
        copied = repeat.place_address_id == primary.place_address_id
        print(
            f"--- повторный осмотр: место скопировано из первичного: {copied}, "
            f"результат: {inspections.result_title(repeat)}, "
            f"нарушение найдено: {repeat.is_violation_found}"
        )
        if not copied:
            failures.append("повторный осмотр не скопировал место первичного")
        if repeat.inspection_result != InspectionResult.NOT_FIXED:
            failures.append("результат повторного осмотра не сохранился")
        if not repeat.is_violation_found:
            failures.append("при неустранённом нарушении не отмечено нарушение")

        # --- Фотография: разметка и отдельное хранение оригинала ----------
        address = (
            repeat.place_address.full_address
            if repeat.place_address is not None
            else None
        )
        image = Image.new("RGB", (1200, 900), (110, 120, 130))
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=90)
        original_bytes = buffer.getvalue()

        lines = inspections.annotation_lines(repeat, address)
        marked_bytes = photo_marking.mark_photo(original_bytes, lines, color="yellow")

        original_file = storage.save_bytes(
            db,
            original_bytes,
            "photo.jpg",
            kind=FileKind.PHOTO,
            mime_type="image/jpeg",
            commit=False,
        )
        db.add(
            ControlActionFile(
                control_action_id=repeat.id,
                file_id=original_file.id,
                photo_kind=PhotoKind.ORIGINAL,
                sequence_no=0,
            )
        )
        marked_file = storage.save_bytes(
            db,
            marked_bytes,
            "photo_marked.jpg",
            kind=FileKind.PHOTO,
            mime_type="image/jpeg",
            commit=False,
        )
        db.add(
            ControlActionFile(
                control_action_id=repeat.id,
                file_id=marked_file.id,
                photo_kind=PhotoKind.ANNOTATED,
                annotation_color="yellow",
                sequence_no=1,
                caption=" ".join(lines) or None,
            )
        )
        db.flush()
        db.refresh(repeat)
        # Файл размеченной копии: по нему проверяется повторная разметка —
        # тот же цвет даёт тот же файл.
        marked_file_id = marked_file.id

        kept_original = inspections.photo_file(repeat, PhotoKind.ORIGINAL)
        kept_marked = inspections.photo_file(repeat, PhotoKind.ANNOTATED)
        marked_ok = kept_marked is not None and len(marked_bytes) > 0
        original_kept = kept_original is not None and kept_original.id != kept_marked.id
        caption = kept_marked.caption if kept_marked else None
        date_in_caption = bool(caption and ru.date_short(repeat.started_at) in caption)
        print(
            f"--- фотография: размеченная копия есть: {marked_ok}, "
            f"оригинал сохранён отдельно: {original_kept}, "
            f"дата осмотра в подписи: {date_in_caption}"
        )
        if not marked_ok:
            failures.append("размеченная копия не сохранилась")
        if not original_kept:
            failures.append("исходный снимок не сохранён отдельно")
        if not date_in_caption:
            failures.append("в подписи к снимку нет даты осмотра")

        # --- Вторичный пакет берёт данные повторного осмотра --------------
        second = generation.generate_package(
            db, CASE_ID, package_kind_code="repeated_prescription"
        )
        second_docs = _documents(db, second.package_id)
        second_date = _local_date(repeat.started_at)
        protocol = second_docs["inspection_protocol"]
        same = protocol.document_date == second_date
        print(
            f"--- вторичный пакет: документов {len(second_docs)}, "
            f"дата протокола {protocol.document_date} = дата повторного осмотра "
            f"{second_date}: {same}"
        )
        if len(second_docs) != 8:
            failures.append(f"во вторичном пакете {len(second_docs)} документов вместо 8")
        if not same:
            failures.append("протокол вторичного пакета не взял дату повторного осмотра")

        context = snapshots.build_case_context(db, CASE_ID, inspection=repeat)
        photos = (context.get("protocol") or {}).get("photos") or []
        only_marked = (
            len(photos) == 1
            and photos[0].get("file_id") == (kept_marked.file_id if kept_marked else None)
        )
        print(
            f"--- снимков в протоколе вторичного пакета: {len(photos)} "
            f"(только размеченный снимок повторного осмотра: {only_marked})"
        )
        if not only_marked:
            failures.append(
                "в протокол попал не тот снимок: ожидался один размеченный "
                "снимок повторного осмотра"
            )

        result_title = context["inspection"]["result_title"]
        print(f"--- результат осмотра в данных пакета: {result_title}")
        if result_title != "нарушение не устранено":
            failures.append("результат осмотра не попал в данные пакета")

        # --- Повторная разметка тем же цветом -----------------------------
        # Файлы хранятся по sha256, поэтому разметка тем же цветом даёт ровно
        # тот же файл. Раньше повторное нажатие кнопки «Нанести разметку
        # заново» роняло страницу: вторая ссылка на файл нарушала уникальность
        # пары «осмотр + файл».
        remark_statuses = [
            _post(
                opener,
                f"/ui/inspections/{repeat.id}/photo/remark",
                {"annotation_color": "yellow"},
            )[0]
            for _ in range(2)
        ]
        db.expire_all()
        annotated = list(
            db.scalars(
                select(ControlActionFile).where(
                    ControlActionFile.control_action_id == repeat.id,
                    ControlActionFile.photo_kind == PhotoKind.ANNOTATED,
                )
            )
        )
        same_file = len(annotated) == 1 and annotated[0].file_id == marked_file_id
        print(
            f"--- разметка заново тем же цветом: HTTP {remark_statuses}, "
            f"размеченных копий: {len(annotated)}, файл тот же: {same_file}"
        )
        if remark_statuses != [200, 200]:
            failures.append(f"повторная разметка тем же цветом вернула {remark_statuses}")
        if not same_file:
            failures.append(
                "повторная разметка не оставила одну размеченную копию того же снимка"
            )

        # --- Адрес и дата на снимке, и снимок не берётся из кэша ----------
        # Адрес осмотра попадает в надпись на фотографии, а сама картинка
        # должна обновляться: адрес ссылки один и тот же, поэтому в него
        # добавляется отпечаток файла.
        db.expire_all()
        repeat = db.get(ControlAction, repeat.id)
        marked_now = inspections.photo_file(repeat, PhotoKind.ANNOTATED)
        original_now = inspections.photo_file(repeat, PhotoKind.ORIGINAL)
        expected_lines = inspections.annotation_lines(repeat, address)
        expected_marked = photo_marking.mark_photo(
            storage.read_bytes(original_now.file), expected_lines, color="yellow"
        )
        photo_matches = (
            marked_now is not None
            and storage.sha256_of(expected_marked) == marked_now.file.sha256
        )
        caption = marked_now.caption if marked_now is not None else None
        print(
            f"--- надпись на снимке: {expected_lines} | "
            f"картинка совпала с ожидаемой: {photo_matches}"
        )
        if not photo_matches:
            failures.append("на размеченном снимке нет адреса осмотра или даты")
        if not caption or address not in caption:
            failures.append("в подписи к снимку нет адреса осмотра")

        status, page = _get(opener, f"/ui/inspections/{repeat.id}")
        version = (marked_now.file.sha256[:12] if marked_now is not None else "")
        versioned = f"/ui/inspections/{repeat.id}/photo/annotated?v={version}" in page
        print(
            f"--- карточка осмотра: HTTP {status}, адрес снимка с отпечатком "
            f"файла: {versioned}"
        )
        if not versioned:
            failures.append("снимок отдаётся по неизменному адресу — браузер покажет кэш")

        print("=== итог ===")
        if failures:
            for failure in failures:
                print("  ОШИБКА:", failure)
            return 1
        print("  осмотр работает от кнопки в карточке до документов пакета")
        return 0
    finally:
        # Убираем за собой: тестовый осмотр и временного пользователя.
        if repeat is not None:
            action = db.get(ControlAction, repeat.id)
            if action is not None:
                db.delete(action)
        if user is not None:
            stored = db.scalar(select(User).where(User.email == user.email))
            if stored is not None:
                db.delete(stored)
        db.commit()
        db.close()


if __name__ == "__main__":
    sys.exit(main())
