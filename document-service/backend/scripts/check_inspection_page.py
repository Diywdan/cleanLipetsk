"""Страница осмотра: работы вместо текста, и формы обеих страниц открываются."""
from __future__ import annotations

import http.cookiejar
import re
import urllib.parse
import urllib.request

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import ControlAction, Role, User, UserRole
from app.services import auth as auth_service

BASE = "http://127.0.0.1:8000"
EMAIL = "check-inspection@local"
PASSWORD = "check-inspection-2026"


def main() -> int:
    db = SessionLocal()
    user_id = None
    try:
        existing = db.scalar(select(User).where(User.email == EMAIL))
        if existing is not None:
            db.delete(existing)
            db.commit()
        user = User(
            full_name="Проверка осмотра",
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

        inspection = db.scalars(
            select(ControlAction)
            .where(ControlAction.control_case_id == 7)
            .order_by(ControlAction.id)
        ).first()
        print(f"осмотр: id={inspection.id}, вид={inspection.inspection_kind.value}")

        client = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
        )
        data = urllib.parse.urlencode(
            {"login": EMAIL, "password": PASSWORD}
        ).encode()
        client.open(
            urllib.request.Request(BASE + "/ui/login", data=data, method="POST")
        )

        for path, title in (
            (f"/ui/inspections/{inspection.id}", "страница осмотра"),
            ("/ui/cases/7/edit", "карточка заявки"),
        ):
            with client.open(BASE + path) as response:
                page = response.read().decode("utf-8", "replace")
            print()
            print(f"=== {title}: HTTP {response.status} ===")
            print(f"  textarea violation_description: "
                  f"{'ЕСТЬ' if 'name=\"violation_description\"' in page else 'нет'}")
            print(f"  блок работ: {'есть' if 'work-row-template' in page else 'нет'}")
            print(f"  вид нарушения: "
                  f"{'есть' if 'name=\"violation_type_id\"' in page else 'нет'}")
            match = re.search(r"const existing = (\[.*?\]);", page, re.S)
            print(f"  работы в форме: {match.group(1)[:120] if match else '—'}")
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
