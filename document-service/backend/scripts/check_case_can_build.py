"""Задача 4: проверка готовности заявки через настоящий API.

Правильный путь перед сборкой — спросить систему, чего не хватает:
    GET /api/incidents/000073/documents -> {"canBuild": ..., "missing": [...]}

Запуск: PYTHONPATH=/app python scripts/check_case_can_build.py 000073
"""
from __future__ import annotations

import http.cookiejar
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import ControlCase, Role, User, UserRole
from app.services import auth as auth_service


BASE = "http://127.0.0.1:8000"
CHECK_EMAIL = "check-canbuild@local"
CHECK_PASSWORD = "check-canbuild-2026"


def make_client():
    jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def call(client, method: str, path: str, fields: dict | None = None):
    data = None
    headers = {}
    if fields is not None:
        data = urllib.parse.urlencode(fields, doseq=True).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    request = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    try:
        with client.open(request, timeout=180) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


def main() -> int:
    number = sys.argv[1] if len(sys.argv) > 1 else "000073"
    db = SessionLocal()
    user_id = None
    try:
        existing = db.scalar(select(User).where(User.email == CHECK_EMAIL))
        if existing is not None:
            db.delete(existing)
            db.commit()
        user = User(
            full_name="Проверка готовности",
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

        case = db.scalar(select(ControlCase).where(ControlCase.case_number == number))
        if case is None:
            print(f"заявка {number!r} не найдена")
            return 1
        incident_id = case.case_number or str(case.id)
        print(f"заявка id={case.id}, идентификатор обращения: {incident_id}")

        client = make_client()
        status, body = call(client, "POST", "/ui/login",
                            {"login": CHECK_EMAIL, "password": CHECK_PASSWORD})
        print(f"вход: HTTP {status}")

        status, body = call(client, "GET", f"/api/incidents/{incident_id}/documents")
        print(f"GET /api/incidents/{incident_id}/documents: HTTP {status}")
        if status != 200:
            print(body.decode("utf-8", "replace")[:400])
            return 1
        payload = json.loads(body)
        print(f"  packageKind: {payload.get('packageKind')!r}")
        print(f"  packageId: {payload.get('packageId')}")
        print(f"  canBuild: {payload.get('canBuild')}")
        print(f"  документов уже собрано: {len(payload.get('documents', []))}")
        missing = payload.get("missing", [])
        print(f"  не хватает ({len(missing)}):")
        for item in missing:
            print(f"    - {item}")
        return 0
    finally:
        if user_id is not None:
            user = db.get(User, user_id)
            if user is not None:
                db.delete(user)
                db.commit()
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
