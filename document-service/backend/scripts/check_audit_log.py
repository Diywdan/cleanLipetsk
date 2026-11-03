"""Что записано в журнале действий по тестовым пользователям."""
from __future__ import annotations

from sqlalchemy import text

from app.db.session import SessionLocal


def main() -> None:
    db = SessionLocal()
    try:
        rows = db.execute(
            text(
                """
                select a.id, a.actor_user_id, u.email, a.action, a.entity_table,
                       a.entity_id, a.created_at
                from audit_log a
                left join users u on u.id = a.actor_user_id
                where u.email like 'check-%'
                order by a.id
                """
            )
        )
        print("=== записи журнала по тестовым пользователям ===")
        for row in rows:
            print(f"  id={row.id} пользователь={row.email} "
                  f"действие={row.action!r} "
                  f"объект={row.entity_table}:{row.entity_id} "
                  f"когда={row.created_at:%Y-%m-%d %H:%M}")

        counts = db.execute(
            text(
                """
                select coalesce(u.email, '(пользователь удалён)') as who, count(*)
                from audit_log a
                left join users u on u.id = a.actor_user_id
                group by 1 order by 2 desc
                """
            )
        )
        print()
        print("=== журнал по всем пользователям ===")
        for who, count in counts:
            print(f"  {who:28} {count}")
        total = db.scalar(text("select count(*) from audit_log"))
        print(f"\nвсего записей в журнале: {total}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
