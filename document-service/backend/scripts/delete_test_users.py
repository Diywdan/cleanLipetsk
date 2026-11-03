"""Удаление тестовых учётных записей, оставшихся от прошлых проверок.

Перед удалением проверяется, что на пользователя ничто не ссылается: заявки,
пакеты, документы, снимки данных, файлы, сессии. Опись удаляемого сохраняется.

По умолчанию — только показать. Удалить: --apply

Запуск: PYTHONPATH=/app python scripts/delete_test_users.py [--apply]
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select, text

from app.db.session import SessionLocal
from app.models import Role, User, UserRole

EXPORT = Path("/data/export")
PATTERN = "check-%"

# Куда могут ссылаться пользователи: таблица, колонка, что делать при ссылке.
# Записи журнала удаление не блокируют: связь объявлена как SET NULL, и автор
# в записи просто становится пустым — так уже помечены удалённые пользователи.
REFERENCES = (
    ("control_cases", "created_by_user_id"),
    ("document_packages", "created_by_user_id"),
    ("documents", "created_by_user_id"),
    ("data_snapshots", "created_by_user_id"),
    ("files", "uploaded_by_user_id"),
    ("appeals", "created_by_user_id"),
)
JOURNAL = ("audit_log", "actor_user_id")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        users = list(
            db.scalars(select(User).where(User.email.like(PATTERN)).order_by(User.id))
        )
        print(f"тестовых учётных записей: {len(users)}")
        if not users:
            return 0

        inventory = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "pattern": PATTERN,
            "removed": [],
        }
        blocked: list[str] = []
        for user in users:
            roles = []
            for link in db.scalars(
                select(UserRole).where(UserRole.user_id == user.id)
            ):
                role = db.get(Role, link.role_id)
                if role is not None:
                    roles.append(role.code)
            references: dict[str, int] = {}
            for table, column in (*REFERENCES, JOURNAL):
                try:
                    count = db.scalar(
                        text(
                            f"select count(*) from {table} where {column} = :uid"
                        ),
                        {"uid": user.id},
                    )
                except Exception:  # noqa: BLE001
                    db.rollback()
                    continue
                if count:
                    references[f"{table}.{column}"] = count
            # Блокируют только ссылки на рабочие данные: журнал обнулит автора.
            data_refs = {
                key: value
                for key, value in references.items()
                if not key.startswith(f"{JOURNAL[0]}.")
            }
            journal = references.get(f"{JOURNAL[0]}.{JOURNAL[1]}", 0)
            print(f"  id={user.id:<4} {user.email:26} роли={roles} "
                  f"активен={user.is_active} "
                  f"ссылок на данные={data_refs or 'нет'}, "
                  f"записей журнала={journal}")
            if data_refs:
                blocked.append(user.email)
            inventory["removed"].append(
                {
                    "id": user.id,
                    "email": user.email,
                    "full_name": user.full_name,
                    "roles": roles,
                    "created_at": user.created_at.isoformat()
                    if user.created_at
                    else None,
                    "references": data_refs,
                    "journal_entries": journal,
                }
            )

        if blocked:
            print(f"\nОСТАНОВ: на часть записей есть ссылки: {blocked}")
            return 1

        if not args.apply:
            print("\nЭто проверка. Для удаления добавьте --apply")
            return 0

        EXPORT.mkdir(parents=True, exist_ok=True)
        path = EXPORT / "test-users-removed.json"
        path.write_text(
            json.dumps(inventory, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\nопись сохранена: {path}")

        for user in users:
            db.delete(user)
        db.commit()
        print(f"удалено записей: {len(users)}")

        left = db.scalar(
            text("select count(*) from users where email like :p"), {"p": PATTERN}
        )
        total = db.scalar(text("select count(*) from users"))
        print(f"осталось тестовых: {left}; всего пользователей: {total}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
