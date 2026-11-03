"""Ответ интерфейсу диспетчера: появится ли кнопка сборки пакета.

Печатает ровно те поля, по которым интерфейс решает, что показывать:
canBuild, missing, packageId, packageKind, documents.
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
from app.models import ControlCase, DocumentPackage, Role, User, UserRole
from app.services import auth as auth_service

BASE = "http://127.0.0.1:8000"
EMAIL = "check-button@local"
PASSWORD = "check-button-2026"


def call(client, method: str, path: str, fields: dict | None = None):
    data = None
    headers = {}
    if fields is not None:
        data = urllib.parse.urlencode(fields, doseq=True).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    request = urllib.request.Request(BASE + path, data=data, method=method,
                                     headers=headers)
    try:
        with client.open(request, timeout=120) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


def report(label: str, payload: dict) -> None:
    print(f"--- {label} ---")
    print(f"  packageKind = {payload.get('packageKind')!r}")
    print(f"  packageId   = {payload.get('packageId')}")
    print(f"  canBuild    = {payload.get('canBuild')}")
    print(f"  документов  = {len(payload.get('documents', []))}")
    missing = payload.get("missing", [])
    print(f"  missing     = {missing if missing else 'пусто'}")
    if not payload.get("packageId") and payload.get("canBuild"):
        print("  кнопка интерфейса: «Собрать пакет документов» — показать")
    elif payload.get("packageId") and payload.get("canBuild"):
        print("  кнопка интерфейса: «Пересобрать пакет» — показать")
    else:
        print("  кнопка интерфейса: сборка недоступна")


def main() -> int:
    number = sys.argv[1] if len(sys.argv) > 1 else "122313"
    db = SessionLocal()
    user_id = None
    try:
        existing = db.scalar(select(User).where(User.email == EMAIL))
        if existing is not None:
            db.delete(existing)
            db.commit()
        user = User(
            full_name="Проверка кнопки сборки",
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

        case = db.scalar(select(ControlCase).where(ControlCase.case_number == number))
        if case is None:
            print(f"заявка {number!r} не найдена")
            return 1
        packages = list(
            db.scalars(
                select(DocumentPackage)
                .where(DocumentPackage.control_case_id == case.id)
                .order_by(DocumentPackage.id)
            )
        )
        print(f"заявка {number} (id={case.id}): пакетов в базе {len(packages)} "
              f"{[p.id for p in packages]}")
        print(f"идентификатор обращения в интерфейсе: {case.case_number!r}")
        print()

        client = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
        )
        status, _ = call(client, "POST", "/ui/login",
                         {"login": EMAIL, "password": PASSWORD})
        print(f"вход: HTTP {status}")

        status, body = call(client, "GET", f"/api/incidents/{number}/documents")
        print(f"GET /api/incidents/{number}/documents: HTTP {status}")
        if status != 200:
            print(body.decode("utf-8", "replace")[:300])
            return 1
        payload = json.loads(body)
        report(f"сейчас (в базе {len(packages)} пакетов)", payload)
        print()
        print("Что изменится, если пакет удалить:")
        print("  packageId станет пустым — интерфейс покажет не «Пересобрать», "
              "а «Собрать пакет документов».")
        print("  canBuild от пакета не зависит: он складывается из вида пакета "
              "по осмотрам и проверки готовности данных.")
        return 0
    finally:
        if user_id is not None:
            try:
                db.rollback()
                user = db.get(User, user_id)
                if user is not None:
                    db.delete(user)
                    db.commit()
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                print(f"временного пользователя убрать не удалось: {exc}")
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
