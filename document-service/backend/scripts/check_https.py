"""Проверка защищённого доступа: HTTPS через nginx, заголовки, флаг Secure.

Скрипт ходит в приложение не напрямую, а через nginx по HTTPS (внутри сети
docker compose) и проверяет, что защищённый канал действительно работает:
страницы отдаются, сессионная кука уходит с флагом Secure, по HTTP остаётся
только переадресация на HTTPS и проверка Let's Encrypt.

Запуск внутри контейнера backend:
    PYTHONPATH=/app python scripts/check_https.py
"""

import http.cookiejar
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import Role, User, UserRole
from app.services import auth as auth_service


HTTPS = "https://nginx"
HTTP = "http://nginx"
CHECK_EMAIL = "check-https@local"
CHECK_PASSWORD = "check-https-password-2026"


def make_client():
    jar = http.cookiejar.CookieJar()
    context = ssl._create_unverified_context()  # сертификат временный
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(jar),
        urllib.request.HTTPSHandler(context=context),
    )
    return opener, jar


def request(client, method: str, url: str, fields: dict | None = None):
    data = None
    headers = {}
    if fields is not None:
        data = urllib.parse.urlencode(fields).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with client.open(req, timeout=120) as response:
            return response.status, response.read().decode("utf-8", "replace"), response
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8", "replace"), error


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
            full_name="Проверка HTTPS",
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
        user_id = user.id

        anon, _ = make_client()

        status, body, response = request(anon, "GET", f"{HTTPS}/health")
        print(f"--- HTTPS /health: HTTP {status}, ответ {body.strip()[:60]}")
        if status != 200:
            failures.append(f"HTTPS /health вернул {status}")
        hsts = response.headers.get("Strict-Transport-Security")
        print(f"--- заголовок HSTS: {hsts or 'НЕТ'}")
        if not hsts:
            failures.append("нет заголовка Strict-Transport-Security")

        status, body, _ = request(anon, "GET", f"{HTTPS}/ui/login")
        print(f"--- HTTPS страница входа: HTTP {status}")
        if status != 200 or "Войти" not in body:
            failures.append("страница входа по HTTPS не отдаётся")

        client, jar = make_client()
        status, body, response = request(
            client, "POST", f"{HTTPS}/ui/login",
            {"login": CHECK_EMAIL, "password": CHECK_PASSWORD},
        )
        cookies = {cookie.name: cookie for cookie in jar}
        session = cookies.get(auth_service.SESSION_COOKIE)
        print(
            f"--- вход по HTTPS: HTTP {status}, кука выдана: {session is not None}, "
            f"Secure: {session.secure if session else '—'}"
        )
        if session is None:
            failures.append("сессионная кука не выдана по HTTPS")
        elif not session.secure:
            failures.append("кука сессии ушла без флага Secure")

        status, body, _ = request(client, "GET", f"{HTTPS}/ui")
        print(f"--- HTTPS список заявок под сессией: HTTP {status}")
        if status != 200:
            failures.append("под сессией по HTTPS список заявок не открылся")

        # По HTTP приложение недоступно: только переадресация и Let's Encrypt.
        # Здесь идём через http.client: urllib сам пошёл бы по переадресации,
        # и мы увидели бы 200 вместо 301.
        import http.client

        plain, _ = make_client()
        connection = http.client.HTTPConnection("nginx", 80, timeout=30)
        connection.request("GET", "/health")
        plain_response = connection.getresponse()
        plain_status = plain_response.status
        location = plain_response.getheader("Location") or ""
        plain_response.read()
        connection.close()
        print(f"--- HTTP /health: HTTP {plain_status}, Location: {location or '—'}")
        if plain_status != 301:
            failures.append(f"по HTTP /health отвечает {plain_status}, а не переадресацией")
        elif not location.startswith("https://"):
            failures.append("переадресация ведёт не на HTTPS")

        status, body, _ = request(
            plain, "GET", f"{HTTP}/.well-known/acme-challenge/no-such-file"
        )
        print(f"--- HTTP проверка Let's Encrypt: HTTP {status} (ожидается 404)")

        print("=== итог ===")
        if failures:
            for failure in failures:
                print("  ОШИБКА:", failure)
            return 1
        print("  защищённый доступ работает: HTTPS, HSTS, флаг Secure, переадресация")
        return 0
    finally:
        if user_id is not None:
            user = db.get(User, user_id)
            if user is not None:
                db.delete(user)
                db.commit()
                print("временный пользователь удалён")
        db.close()


if __name__ == "__main__":
    sys.exit(main())
