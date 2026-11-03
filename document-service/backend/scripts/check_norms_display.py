"""Как выглядит список норм на странице заявки после правки."""
from __future__ import annotations

import http.cookiejar
import re
import urllib.error
import urllib.parse
import urllib.request

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import Role, User, UserRole
from app.services import auth as auth_service

BASE = "http://127.0.0.1:8000"
EMAIL = "check-norms@local"
PASSWORD = "check-norms-2026"


def call(client, method, path, fields=None):
    data = None
    headers = {}
    if fields is not None:
        data = urllib.parse.urlencode(fields, doseq=True).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    request = urllib.request.Request(BASE + path, data=data, method=method,
                                     headers=headers)
    try:
        with client.open(request, timeout=120) as response:
            return response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8", "replace")


def main() -> int:
    db = SessionLocal()
    user_id = None
    try:
        existing = db.scalar(select(User).where(User.email == EMAIL))
        if existing is not None:
            db.delete(existing)
            db.commit()
        user = User(
            full_name="Проверка норм",
            email=EMAIL,
            password_hash=auth_service.hash_password(PASSWORD),
            is_active=True,
        )
        db.add(user)
        db.flush()
        role = db.scalar(select(Role).where(Role.code == "manager"))
        db.add(UserRole(user_id=user.id, role_id=role.id))
        db.commit()
        user_id = user.id

        client = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
        )
        call(client, "POST", "/ui/login", {"login": EMAIL, "password": PASSWORD})

        for path in ("/ui/cases/7", "/ui/cases/7/edit"):
            status, html = call(client, "GET", path)
            print(f"=== {path}: HTTP {status} ===")
            if status != 200:
                print(html[:200])
                continue
            # Строка «Нормы:» на карточке и <optgroup> в форме.
            for match in re.finditer(r"Нормы:[^<]{0,400}", html):
                print("  " + " ".join(match.group(0).split())[:320])
            for match in re.finditer(r"<optgroup label=\"([^\"]+)\">", html):
                print(f"  optgroup: {match.group(1)}")
            for match in re.finditer(
                r"<option value=\"\d+\"[^>]*>\s*([^<]{0,120}?)\s*</option>", html
            ):
                print(f"  option: {match.group(1)!r}")
            print()
        return 0
    finally:
        if user_id is not None:
            try:
                db.rollback()
                user = db.get(User, user_id)
                if user is not None:
                    db.delete(user)
                    db.commit()
            except Exception:  # noqa: BLE001
                db.rollback()
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
