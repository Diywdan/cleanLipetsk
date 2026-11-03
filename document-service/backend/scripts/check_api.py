"""Проверка HTTP API: вход -> готовность дела -> пакет -> файлы и архив.

Программный интерфейс закрыт сессией, поэтому скрипт сначала убеждается,
что анонимный запрос получает 401, затем входит под временным пользователем
и выполняет всю проверку. Временный пользователь удаляется в конце.

Запуск внутри контейнера:
    PYTHONPATH=/app python scripts/check_api.py
"""

import hashlib
import http.cookiejar
import io
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import ControlCase, Role, User, UserRole
from app.services import auth as auth_service


BASE = "http://127.0.0.1:8000"
CHECK_EMAIL = "check-api@local"
CHECK_PASSWORD = "check-api-password-2026"

# Демонстрационное дело, по которому проверяется программный интерфейс: в нём
# заполнены все поля и собран первичный пакет. «Последняя заявка в базе» здесь
# не годится: заявка без документов и не должна проходить проверку готовности.
DEMO_CASE_ID = 7


def make_client():
    jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar)), jar


def call(client, method: str, path: str, body: dict | None = None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(
        BASE + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"} if data else {},
    )
    try:
        with client.open(request, timeout=240) as response:
            return response.status, response.read(), response.headers
    except urllib.error.HTTPError as error:
        return error.code, error.read(), error.headers


def ensure_check_user(db) -> int:
    user = db.scalar(select(User).where(User.email == CHECK_EMAIL))
    if user is not None:
        db.delete(user)
        db.commit()
    user = User(
        full_name="Проверка API",
        email=CHECK_EMAIL,
        password_hash=auth_service.hash_password(CHECK_PASSWORD),
        is_active=True,
    )
    db.add(user)
    db.flush()
    role = db.scalar(select(Role).where(Role.code == "administrator"))
    if role is not None:
        db.add(UserRole(user_id=user.id, role_id=role.id))
    db.commit()
    return user.id


def main() -> int:
    db = SessionLocal()
    failures: list[str] = []
    check_user_id = None
    try:
        demo_case = db.get(ControlCase, DEMO_CASE_ID)
        if demo_case is None:
            print(f"нет демонстрационного дела {DEMO_CASE_ID}")
            return 1
        case_id = demo_case.id
        check_user_id = ensure_check_user(db)

        anon, _ = make_client()
        status, raw, _ = call(anon, "GET", "/api/cases")
        print(f"--- анонимный доступ к /api/cases: HTTP {status} (ожидается 401)")
        if status != 401:
            failures.append(f"программный интерфейс доступен без входа: HTTP {status}")

        status, raw, _ = call(anon, "GET", "/health")
        print(f"--- /health без входа: HTTP {status} (живость остаётся открытой)")
        if status != 200:
            failures.append("/health требует входа — сломается мониторинг")

        client, jar = make_client()
        data = urllib.parse.urlencode(
            {"login": CHECK_EMAIL, "password": CHECK_PASSWORD}
        ).encode("utf-8")
        request = urllib.request.Request(
            BASE + "/ui/login",
            data=data,
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with client.open(request, timeout=60) as response:
            print(f"--- вход: HTTP {response.status}, {response.url}")
        if auth_service.SESSION_COOKIE not in [cookie.name for cookie in jar]:
            failures.append("сессия не выдана")

        status, raw, _ = call(client, "GET", "/api/cases")
        print(f"--- список дел под сессией: HTTP {status}")
        if status != 200:
            failures.append(f"список дел вернул {status}")

        status, raw, _ = call(client, "GET", f"/api/cases/{case_id}/readiness")
        readiness = json.loads(raw)
        print(
            f"--- готовность дела {case_id}: HTTP {status}, "
            f"готово={readiness['is_ready']}, замечаний={len(readiness['issues'])}"
        )
        if not readiness["is_ready"]:
            failures.append("демонстрационное дело не проходит проверку готовности")

        status, raw, _ = call(
            client, "POST", f"/api/cases/{case_id}/packages",
            {"package_kind": "primary_prescription"},
        )
        print(f"--- формирование первичного пакета: HTTP {status}")
        package = None
        if status != 201:
            failures.append(f"POST пакета вернул {status}: {raw[:200]}")
        else:
            package = json.loads(raw)
            print("    пакет:", package["id"], "| документов:", len(package["documents"]))

        if package:
            first = package["documents"][0]
            status, file_bytes, headers = call(client, "GET", first["download_url"])
            digest = hashlib.sha256(file_bytes).hexdigest()
            print(
                f"--- скачивание {first['code']}: HTTP {status}, {len(file_bytes)} байт, "
                f"sha256 совпал: {digest == first['sha256']}"
            )
            if digest != first["sha256"] or not file_bytes.startswith(b"PK"):
                failures.append("скачанный документ не совпал с сохранённым")

            status, archive_bytes, headers = call(
                client, "GET", f"/api/packages/{package['id']}/archive"
            )
            print(f"--- архив пакета: HTTP {status}, {len(archive_bytes)} байт")
            if status != 200:
                failures.append(f"архив не получен: {status}")
            else:
                with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
                    names = archive.namelist()
                print("    папка:", names[0].split("/")[0], "| файлов:", len(names))
                if len(names) != len(package["documents"]):
                    failures.append("в архиве не столько файлов, сколько документов в пакете")

                # Сохранение в папку должно давать ровно то же содержимое,
                # что и архив: те же имена файлов и та же папка.
                status, raw, _ = call(
                    client, "GET", f"/api/packages/{package['id']}/files"
                )
                listing = json.loads(raw)
                archive_files = {
                    name.split("/", 1)[1] for name in names if "/" in name
                }
                listing_files = {item["name"] for item in listing["files"]}
                print(
                    f"--- список файлов для сохранения в папку: HTTP {status}, "
                    f"папка {listing['folder']}, документов {len(listing['files'])}"
                )
                if status != 200:
                    failures.append(f"список файлов пакета вернул {status}")
                if listing_files != archive_files:
                    failures.append(
                        "имена файлов для папки не совпали с архивом: "
                        f"{sorted(listing_files ^ archive_files)}"
                    )
                if listing["folder"] != names[0].split("/")[0]:
                    failures.append("папка для сохранения не совпала с папкой архива")
                if "manifest" in listing:
                    failures.append("опись пакета больше не нужна, а она отдаётся")

        empty_case = ControlCase()
        db.add(empty_case)
        db.commit()
        empty_id = empty_case.id
        try:
            status, raw, _ = call(client, "GET", f"/api/cases/{empty_id}/readiness")
            issues = json.loads(raw)["issues"]
            print(f"--- пустое дело {empty_id}: замечаний {len(issues)}")
            if not issues:
                failures.append("пустое дело признано готовым")

            status, raw, _ = call(
                client, "POST", f"/api/cases/{empty_id}/packages",
                {"package_kind": "primary_prescription"},
            )
            print(f"--- сборка пустого дела: HTTP {status} (ожидается 422)")
            if status != 422:
                failures.append(f"пустое дело собралось: HTTP {status}")
        finally:
            db.delete(empty_case)
            db.commit()

        status, raw, _ = call(client, "GET", "/api/cases/999999")
        print(f"--- несуществующее дело: HTTP {status}")
        if status != 404:
            failures.append(f"ожидался 404, получен {status}")

        print("=== итог ===")
        if failures:
            for failure in failures:
                print("  ОШИБКА:", failure)
            return 1
        print("  все проверки API пройдены")
        return 0
    finally:
        if check_user_id is not None:
            user = db.get(User, check_user_id)
            if user is not None:
                db.delete(user)
                db.commit()
                print("временный пользователь удалён")
        db.close()


if __name__ == "__main__":
    sys.exit(main())
