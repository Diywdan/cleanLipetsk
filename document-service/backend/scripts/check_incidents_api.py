"""Проверка фасада обращений для интерфейса диспетчера.

Интерфейс диспетчера (SPA «Чистый Липецк») работает со своей моделью
обращения. Проверка убеждается, что наш API отдаёт её из наших данных и что
кнопка «Сформировать акт и предписание» собирает настоящий пакет:

* список обращений: номер, статус, источник, приоритет, место, ответственные,
  таймлайн и снимок осмотра;
* документы: пока пакета нет — сборка возможна, после сборки — шесть
  документов со ссылками на скачивание и числом листов;
* сборка пакета по обращению и скачивание готового DOCX;
* неизвестное обращение — 404, а не пустой ответ.

За собой проверка убирает временного пользователя; пакет остаётся в заявке,
как и после обычной сборки из интерфейса.

Запуск внутри контейнера:
    PYTHONPATH=/app python scripts/check_incidents_api.py
"""

import http.cookiejar
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import ControlCase, DocumentPackage, Role, User, UserRole
from app.services import auth as auth_service


BASE = "http://127.0.0.1:8000"
CASE_ID = 7
CHECK_EMAIL = "check-incidents@local"
CHECK_PASSWORD = "check-incidents-2026"
STATUSES = {"NEW", "IN_PROGRESS", "VERIFICATION", "CLOSED", "KNM_ESCALATION"}


def make_client():
    jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar)), jar


def call(client, method: str, path: str, fields: dict | None = None):
    data = None
    headers = {}
    if fields is not None:
        data = urllib.parse.urlencode(fields, doseq=True).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    request = urllib.request.Request(
        BASE + path, data=data, method=method, headers=headers
    )
    try:
        with client.open(request, timeout=180) as response:
            body = response.read()
            return response.status, body, response.headers.get("content-type", "")
    except urllib.error.HTTPError as error:
        return error.code, error.read(), error.headers.get("content-type", "")


def main() -> int:
    db = SessionLocal()
    failures: list[str] = []
    user_id = None
    try:
        user = db.scalar(select(User).where(User.email == CHECK_EMAIL))
        if user is not None:
            db.delete(user)
            db.commit()
        user = User(
            full_name="Проверка обращений",
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

        case = db.get(ControlCase, CASE_ID)
        incident_id = case.case_number or str(case.id)
        print(f"--- заявка {CASE_ID}: идентификатор обращения {incident_id}")

        client, _ = make_client()
        call(client, "POST", "/ui/login", {"login": CHECK_EMAIL, "password": CHECK_PASSWORD})

        # --- 1. Без сессии обращения недоступны ---------------------------
        anonymous = urllib.request.build_opener()
        try:
            anonymous.open(BASE + "/api/incidents", timeout=30)
            failures.append("обращения отдаются без входа")
            print("--- без входа: доступно (плохо)")
        except urllib.error.HTTPError as error:
            print(f"--- без входа: HTTP {error.code} (ожидается 401)")
            if error.code != 401:
                failures.append("без сессии ожидался ответ 401")

        # --- 2. Список обращений ------------------------------------------
        status, body, _ = call(client, "GET", "/api/incidents")
        incidents = json.loads(body) if status == 200 else []
        print(f"--- GET /api/incidents: HTTP {status}, обращений {len(incidents)}")
        if status != 200 or not incidents:
            failures.append("список обращений не пришёл")
        ours = [item for item in incidents if item["id"] == incident_id]
        if not ours:
            failures.append(f"в списке нет нашей заявки {incident_id}")
        else:
            item = ours[0]
            checks = {
                "статус": item["status"] in STATUSES,
                "источник": bool(item.get("source")),
                "приоритет": item["priority"] in {"LOW", "MEDIUM", "HIGH"},
                "адрес": bool(item["location"].get("address")),
                "ответственные": bool(item.get("responsibles")),
                "таймлайн": bool(item["timeline"].get("createdAt")),
                "снимок осмотра": bool(item["media"].get("photoBeforeUrl")),
            }
            print(
                f"    статус {item['status']}, приоритет {item['priority']}, "
                f"источник {item['source']}, адрес: {item['location']['address'][:40]}"
            )
            for title, ok in checks.items():
                if not ok:
                    failures.append(f"в обращении нет поля: {title}")

        # --- 3. Документы до сборки --------------------------------------
        status, body, _ = call(client, "GET", f"/api/incidents/{incident_id}/documents")
        before = json.loads(body) if status == 200 else {}
        print(
            f"--- документы до сборки: HTTP {status}, "
            f"можно собрать: {before.get('canBuild')}, "
            f"пакет: {before.get('packageId')}, документов: {len(before.get('documents', []))}"
        )
        if status != 200:
            failures.append("не удалось получить состояние документов")

        # --- 4. Сборка пакета по обращению -------------------------------
        status, body, _ = call(client, "POST", f"/api/incidents/{incident_id}/act", {})
        print(f"--- POST /api/incidents/{incident_id}/act: HTTP {status}")
        if status != 200:
            failures.append(
                f"сборка пакета по обращению не прошла: HTTP {status} "
                f"{body.decode('utf-8', 'replace')[:200]}"
            )

        status, body, _ = call(client, "GET", f"/api/incidents/{incident_id}/documents")
        after = json.loads(body) if status == 200 else {}
        documents = after.get("documents", [])
        print(
            f"--- документы после сборки: пакет {after.get('packageId')}, "
            f"документов {len(documents)}, архив: {bool(after.get('archiveUrl'))}"
        )
        if len(documents) != 6:
            failures.append(f"в пакете {len(documents)} документов вместо 6")
        if not after.get("archiveUrl"):
            failures.append("нет ссылки на архив пакета")
        for document in documents:
            if not document.get("downloadUrl") or not document.get("title"):
                failures.append(f"документ {document.get('code')} без ссылки или названия")
            if document.get("code") == "act" and document.get("pages") != 3:
                failures.append(
                    f"у акта {document.get('pages')} листов вместо 3 (число листов должно считаться)"
                )

        # --- 5. Скачивание документа -------------------------------------
        if documents:
            status, body, content_type = call(
                client, "GET", documents[0]["downloadUrl"]
            )
            is_docx = body[:2] == b"PK"
            print(
                f"--- скачивание {documents[0]['code']}: HTTP {status}, "
                f"тип {content_type}, DOCX: {is_docx}, {len(body)} байт"
            )
            if status != 200 or not is_docx:
                failures.append("документ не скачивается как DOCX")

        # --- 6. Неизвестное обращение ------------------------------------
        status, _, _ = call(client, "GET", "/api/incidents/99999999")
        print(f"--- неизвестное обращение: HTTP {status} (ожидается 404)")
        if status != 404:
            failures.append("на неизвестное обращение ожидался 404")

        packages = list(
            db.scalars(
                select(DocumentPackage).where(DocumentPackage.control_case_id == CASE_ID)
            )
        )
        print(f"--- пакетов по заявке в базе: {len(packages)}")

        print("=== итог ===")
        if failures:
            for failure in failures:
                print("  ОШИБКА:", failure)
            return 1
        print("  обращения и документы отдаются интерфейсу диспетчера, пакет собирается")
        return 0
    finally:
        if user_id is not None:
            stored = db.get(User, user_id)
            if stored is not None:
                db.delete(stored)
            db.commit()
        print("временный пользователь удалён")
        db.close()


if __name__ == "__main__":
    sys.exit(main())
