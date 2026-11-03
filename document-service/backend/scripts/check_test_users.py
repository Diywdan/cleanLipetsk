"""Тестовые пользователи: кто это, когда заходил и есть ли на них ссылки."""
from __future__ import annotations

from sqlalchemy import func, select, text

from app.db.session import SessionLocal
from app.models import Role, User, UserRole


SQL = """
select
    conrelid::regclass as child_table,
    conname,
    confdeltype
from pg_constraint
where contype = 'f' and confrelid = 'users'::regclass
order by 1
"""

MEANING = {
    "a": "NO ACTION",
    "r": "RESTRICT",
    "c": "CASCADE",
    "n": "SET NULL",
    "d": "SET DEFAULT",
}


def main() -> None:
    db = SessionLocal()
    try:
        print("=== кто ссылается на пользователей ===")
        for row in db.execute(text(SQL)):
            print(f"  {str(row.child_table):28} {row.conname:52} "
                  f"{MEANING.get(row.confdeltype, row.confdeltype)}")

        print()
        users = list(
            db.scalars(select(User).where(User.email.like("check-%")).order_by(User.id))
        )
        print(f"=== тестовые пользователи: {len(users)} ===")
        for user in users:
            roles = [
                db.get(Role, link.role_id).code
                for link in db.scalars(
                    select(UserRole).where(UserRole.user_id == user.id)
                )
                if db.get(Role, link.role_id) is not None
            ]
            print(f"  id={user.id:<4} {user.email:28} {user.full_name!r} "
                  f"роли={roles} активен={user.is_active} "
                  f"создан={user.created_at:%Y-%m-%d %H:%M}")

        if not users:
            return

        ids = [user.id for user in users]
        print()
        print("=== ссылки на этих пользователей ===")
        for table, column in (
            ("control_cases", "created_by_user_id"),
            ("document_packages", "created_by_user_id"),
            ("documents", "created_by_user_id"),
            ("data_snapshots", "created_by_user_id"),
            ("files", "uploaded_by_user_id"),
            ("audit_log", "user_id"),
        ):
            try:
                count = db.scalar(
                    text(
                        f"select count(*) from {table} where {column} = any(:ids)"
                    ),
                    {"ids": ids},
                )
            except Exception as exc:  # noqa: BLE001
                print(f"  {table}.{column}: таблицы нет ({type(exc).__name__})")
                continue
            print(f"  {table}.{column}: {count}")

        print()
        print("=== всего пользователей в системе ===")
        total = db.scalar(select(func.count()).select_from(User))
        print(f"  {total}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
