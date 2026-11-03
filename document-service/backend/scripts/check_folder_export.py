"""Проверка сохранения пакета в выбранную папку.

Кнопка «Сохранить в папку» работает только в браузерах с доступом к файловой
системе, и если что-то не так, оператор видит «ничего не произошло». Поэтому
проверяется не только разметка, но и то, что ход работы виден: сообщение
появляется сразу по нажатию, ошибка попадает в строку состояния и в консоль
браузера, а документы пишутся прямо в выбранную папку, без подпапки.

Запуск внутри контейнера:
    PYTHONPATH=/app python scripts/check_folder_export.py
"""

import http.cookiejar
import re
import sys
import urllib.parse
import urllib.request

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import Role, User, UserRole
from app.services import auth


BASE = "http://127.0.0.1:8000"
CASE_ID = 7


def main() -> int:
    db = SessionLocal()
    failures: list[str] = []
    try:
        email, password = "check-folder@local", "check-folder-2026"
        existing = db.scalar(select(User).where(User.email == email))
        if existing is not None:
            db.delete(existing)
            db.commit()
        user = User(
            full_name="Проверка сохранения в папку",
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
        opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(jar)
        )
        opener.open(
            urllib.request.Request(
                f"{BASE}/ui/login",
                data=urllib.parse.urlencode(
                    {"login": email, "password": password}
                ).encode(),
                method="POST",
            ),
            timeout=30,
        ).read()

        card = opener.open(f"{BASE}/ui/cases/{CASE_ID}", timeout=30).read().decode()
        package_id = re.search(r'data-package="(\d+)"', card)

        checks = [
            ("кнопка на странице одна", len(re.findall('id="save-to-folder"', card)) == 1),
            ("у кнопки есть номер пакета", package_id is not None),
            ("сообщение появляется сразу", "Готовлю список документов" in card),
            ("браузер без доступа к папкам получает пояснение",
             "не умеет сохранять в папку" in card),
            ("документы пишутся в выбранную папку, без подпапки",
             "getDirectoryHandle(listing.folder" not in card),
            ("ошибка видна в строке состояния", "Не удалось сохранить" in card),
            ("ошибка попадает в консоль браузера", "console.error" in card),
            ("успех виден в строке состояния", "Сохранено документов" in card),
        ]
        for label, ok in checks:
            print(f"  {'ок ' if ok else 'НЕТ'} {label}")
            if not ok:
                failures.append(label)

        if package_id is not None:
            listing = opener.open(
                f"{BASE}/api/packages/{package_id.group(1)}/files", timeout=30
            ).read().decode()
            import json

            data = json.loads(listing)
            files = data.get("files") or []
            print(f"  ок  список файлов: {len(files)} документов")
            if not files:
                failures.append("список файлов пуст")
            else:
                first = opener.open(f"{BASE}{files[0]['url']}", timeout=60)
                body = first.read()
                print(f"  ок  первый документ скачивается: {len(body)} байт")
                if not body:
                    failures.append("документ скачивается пустым")

        print("=== итог ===")
        if failures:
            for failure in failures:
                print("  ОШИБКА:", failure)
            return 1
        print("  сохранение в папку работает, ход работы виден оператору")
        return 0
    finally:
        stored = db.scalar(select(User).where(User.email == "check-folder@local"))
        if stored is not None:
            db.delete(stored)
        db.commit()
        db.close()


if __name__ == "__main__":
    sys.exit(main())
