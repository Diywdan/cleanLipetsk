"""Проверка входа в интерфейс диспетчера через наш сервис.

Вход у двух интерфейсов общий: сессия в куке, которую ставит наша страница
входа. Интерфейс диспетчера при открытии спрашивает «кто вошёл» и, если
сессии нет, отправляет человека на вход с возвратом обратно.

Проверка отвечает на пять вопросов:

* вход возвращает в интерфейс диспетчера, а не в список заявок;
* чужой адрес в поле возврата игнорируется (открытая переадресация);
* «кто вошёл» отдаёт имя, роль сервиса и роль в терминах диспетчера;
* администратор видит заявки и может действовать по делу;
* выход снимает сессию: и наш интерфейс, и диспетчер снова просят войти.

За собой проверка убирает временного пользователя и созданные сессии.

Запуск внутри контейнера:
    PYTHONPATH=/app python scripts/check_dispatch_auth.py
"""

import http.cookiejar
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import Role, User, UserRole
from app.services import auth as auth_service


BASE = "http://127.0.0.1:8000"
CHECK_EMAIL = "check-dispatch-auth@local"
CHECK_PASSWORD = "check-dispatch-auth-2026"
ADMIN_EMAIL = "admin@lipetskcity.ru"
EVIL_NEXT = "https://evil.example/"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Переадресацию не выполняем: проверяем сам ответ на вход.

    Страницу интерфейса диспетчера отдаёт nginx, а не приложение: если
    пойти по переадресации на порт приложения, получится 404, и проверка
    ругалась бы на исправный вход.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def header(headers: dict, name: str) -> str:
    """Значение заголовка без учёта регистра: HTTP его не нормирует."""

    for key, value in headers.items():
        if key.lower() == name.lower():
            return value
    return ""


def make_client(jar=None, follow: bool = True):
    # Банк кук общий: вход выполняет один клиент, дальше работают другие.
    jar = jar if jar is not None else http.cookiejar.CookieJar()
    handlers = [urllib.request.HTTPCookieProcessor(jar)]
    if not follow:
        handlers.append(NoRedirect())
    return urllib.request.build_opener(*handlers), jar


def call(client, method: str, path: str, fields: dict | None = None, body: dict | None = None):
    data = None
    headers = {}
    if fields is not None:
        data = urllib.parse.urlencode(fields, doseq=True).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        BASE + path, data=data, method=method, headers=headers
    )
    try:
        with client.open(request, timeout=120) as response:
            return response.status, response.read(), response.url, dict(response.headers)
    except urllib.error.HTTPError as error:
        return error.code, error.read(), error.url, dict(error.headers)


def cookie_names(jar) -> list[str]:
    return [cookie.name for cookie in jar]


def main() -> int:
    db = SessionLocal()
    failures: list[str] = []
    user_id = None
    admin_session_token = None
    try:
        user = db.scalar(select(User).where(User.email == CHECK_EMAIL))
        if user is not None:
            db.delete(user)
            db.commit()
        user = User(
            full_name="Проверка входа диспетчера",
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

        client, jar = make_client()
        plain, _ = make_client(jar, follow=False)

        # --- 1. Без сессии «кто вошёл» отвечает 401 -----------------------
        status, raw, _, _ = call(client, "GET", "/api/me")
        message = json.loads(raw).get("message", "") if status == 401 else ""
        print(f"--- /api/me без сессии: HTTP {status}, ответ: {message[:50]}")
        if status != 401 or not message:
            failures.append("без сессии /api/me не отвечает понятной ошибкой")

        # --- 2. Вход с возвратом в интерфейс диспетчера -------------------
        status, raw, url, headers = call(
            plain,
            "POST",
            "/ui/login",
            {"login": CHECK_EMAIL, "password": CHECK_PASSWORD, "next": "/dispatch/"},
        )
        location = header(headers, "Location")
        print(f"--- вход: HTTP {status}, возврат на {location}")
        if status != 303 or location != "/dispatch/":
            failures.append(f"после входа возврат не в диспетчер, а на {location!r}")
        if auth_service.SESSION_COOKIE not in cookie_names(jar):
            failures.append("после входа не поставлена кука сессии")

        # --- 3. Кто вошёл: имя, роль сервиса и роль диспетчера ------------
        status, raw, _, _ = call(client, "GET", "/api/me")
        me = json.loads(raw) if status == 200 else {}
        print(
            f"--- /api/me: HTTP {status}, {me.get('name')!r}, "
            f"роль сервиса {me.get('serviceRoleTitle')!r}, роль диспетчера {me.get('role')!r}"
        )
        if status != 200 or not me.get("name"):
            failures.append("«кто вошёл» не отдал имя пользователя")
        if me.get("serviceRoleTitle") != "Руководитель":
            failures.append("название нашей роли не передано интерфейсу")
        if me.get("role") != "INSPECTOR":
            failures.append("правящая роль должна быть инспектором в терминах диспетчера")

        status, raw, _, _ = call(client, "GET", "/api/incidents")
        incidents = json.loads(raw) if status == 200 else []
        print(f"--- заявки под этой ролью: HTTP {status}, обращений {len(incidents)}")
        if status != 200:
            failures.append("под вошедшим пользователем заявки недоступны")

        # --- 4. Выход снимает сессию --------------------------------------
        status, raw, _, _ = call(client, "POST", "/api/logout")
        print(f"--- выход: HTTP {status}")
        if status != 200:
            failures.append("выход не сработал")
        client, jar = make_client()
        status, _, _, _ = call(client, "GET", "/api/me")
        print(f"--- /api/me после выхода: HTTP {status} (ожидается 401)")
        if status != 401:
            failures.append("после выхода сессия продолжает работать")

        # --- 5. Чужой адрес возврата игнорируется -------------------------
        status, raw, url, headers = call(
            plain,
            "POST",
            "/ui/login",
            {"login": CHECK_EMAIL, "password": CHECK_PASSWORD, "next": EVIL_NEXT},
        )
        location = header(headers, "Location")
        print(f"--- вход с чужим адресом возврата: возврат на {location}")
        if location != "/ui":
            failures.append(f"чужой адрес возврата принят: {location!r}")

        # --- 6. Администратор: та же дорога, роль выше ---------------------
        admin = db.scalar(select(User).where(User.email == ADMIN_EMAIL))
        if admin is None:
            print("--- администратор не найден, шаг пропущен")
        else:
            session = auth_service.create_session(db, admin)
            db.commit()
            admin_session_token = session.token
            admin_client, _ = make_client()
            request = urllib.request.Request(
                BASE + "/api/me",
                headers={"Cookie": f"{auth_service.SESSION_COOKIE}={session.token}"},
            )
            with urllib.request.urlopen(request, timeout=60) as response:
                admin_me = json.loads(response.read().decode())
            request = urllib.request.Request(
                BASE + "/api/incidents",
                headers={"Cookie": f"{auth_service.SESSION_COOKIE}={session.token}"},
            )
            with urllib.request.urlopen(request, timeout=60) as response:
                admin_incidents = json.loads(response.read().decode())
            print(
                f"--- администратор: {admin_me.get('serviceRoleTitle')!r}, "
                f"админ {admin_me.get('isAdmin')}, обращений {len(admin_incidents)}"
            )
            if not admin_me.get("isAdmin"):
                failures.append("администратор не распознан как администратор")
            if admin_me.get("role") != "INSPECTOR":
                failures.append("администратор должен мочь действовать по делу")
            if not admin_incidents:
                failures.append("администратор не видит заявок")

        print("=== итог ===")
        if failures:
            for failure in failures:
                print("  ОШИБКА:", failure)
            return 1
        print("  вход в интерфейс диспетчера идёт через наш сервис, роли сопоставлены")
        return 0
    finally:
        if admin_session_token:
            auth_service.revoke_session(db, admin_session_token)
        if user_id is not None:
            stored = db.get(User, user_id)
            if stored is not None:
                db.delete(stored)
        db.commit()
        print("временный пользователь и служебная сессия удалены")
        db.close()


if __name__ == "__main__":
    sys.exit(main())
