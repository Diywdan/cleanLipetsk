"""Опыт: удаляем пакет, смотрим, что скажет интерфейсу, и собираем заново.

Вопрос был прямой: появится ли кнопка сборки, если пакет удалить, а данные
оставить. Проверяем на живой заявке: удалить пакет, спросить
/api/incidents/<номер>/documents, собрать пакет заново.

Работает только на заявке 122313 — чтобы не тронуть чужие данные.

Запуск: PYTHONPATH=/app python scripts/try_rebuild_flow.py 122313
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
EMAIL = "check-flow-probe@local"
PASSWORD = "check-flow-probe-2026"
ALLOWED = {"122313"}


def call(client, method: str, path: str, fields: dict | None = None):
    data = None
    headers = {}
    if fields is not None:
        data = urllib.parse.urlencode(fields, doseq=True).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    request = urllib.request.Request(BASE + path, data=data, method=method,
                                     headers=headers)
    try:
        with client.open(request, timeout=300) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


def ask(client, number: str, label: str) -> dict:
    status, body = call(client, "GET", f"/api/incidents/{number}/documents")
    payload = json.loads(body) if status == 200 else {}
    print(f"--- {label}: HTTP {status} ---")
    print(f"  packageKind={payload.get('packageKind')!r} "
          f"packageId={payload.get('packageId')} "
          f"canBuild={payload.get('canBuild')} "
          f"документов={len(payload.get('documents', []))}")
    print(f"  missing={payload.get('missing') or 'пусто'}")
    if not payload.get("packageId"):
        print("  кнопка: «Собрать пакет документов»"
              if payload.get("canBuild") else "  кнопка: недоступна")
    else:
        print("  кнопка: «Пересобрать пакет»"
              if payload.get("canBuild") else "  кнопка: недоступна")
    return payload


def main() -> int:
    number = sys.argv[1] if len(sys.argv) > 1 else "122313"
    if number not in ALLOWED:
        print(f"опыт разрешён только для заявок {sorted(ALLOWED)}")
        return 1

    db = SessionLocal()
    user_id = None
    try:
        existing = db.scalar(select(User).where(User.email == EMAIL))
        if existing is not None:
            db.delete(existing)
            db.commit()
        user = User(
            full_name="Опыт с кнопкой сборки",
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
        client = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
        )
        call(client, "POST", "/ui/login", {"login": EMAIL, "password": PASSWORD})

        before = list(
            db.scalars(
                select(DocumentPackage)
                .where(DocumentPackage.control_case_id == case.id)
                .order_by(DocumentPackage.id)
            )
        )
        print(f"заявка {number}: пакетов до опыта {len(before)} "
              f"{[p.id for p in before]}")
        ask(client, number, "шаг 1: как есть")

        # Шаг 2: удаляем все пакеты заявки.
        for package in before:
            db.delete(package)
        db.commit()
        print(f"\nпакеты удалены, данные заявки не тронуты")

        after_delete = ask(client, number, "шаг 2: после удаления пакетов")

        # Шаг 3: собираем заново — так интерфейс и делает по кнопке.
        status, body = call(client, "POST", f"/api/incidents/{number}/act", {})
        print(f"\nPOST /api/incidents/{number}/act: HTTP {status}")
        rebuilt = ask(client, number, "шаг 3: после сборки по кнопке")

        left = list(
            db.scalars(
                select(DocumentPackage)
                .where(DocumentPackage.control_case_id == case.id)
                .order_by(DocumentPackage.id)
            )
        )
        print(f"\nпакетов стало: {len(left)} {[p.id for p in left]}")
        print(f"было: {[p.id for p in before]}")
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
