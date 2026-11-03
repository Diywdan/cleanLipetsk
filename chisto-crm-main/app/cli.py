"""Обслуживание из командной строки: python -m app.cli <команда>.

В контейнере: docker compose exec crm python -m app.cli agency-accounts
Реестр КП:    docker compose exec crm python -m app.cli kp-import-utko /data/utko/details.jsonl --complete
Коды ГЖИ:     docker compose exec crm python -m app.cli kp-codes-gzhi /data/gzhi/codes.csv
Фото дел:     docker compose exec crm python -m app.cli media-cache
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import secrets
from collections import Counter
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import kp, media
from app.db import session_scope
from app.domain import audit
from app.main import run_migrations
from app.models import Case, Executor, Role, User
from app.security import hash_password
from app.seed import seed_all

# Сотрудники ДРТ видят дела по всем ведомствам — у них нет организации.
DRT_ACCOUNTS = {
    "drt": ("ДРТ — инспектор", "inspector"),
    "rukovodstvo": ("ДРТ — руководство", "manager"),
}


def _username(x: Executor) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]", "_", x.code or x.executor_id.lower())[:64]


def _create(db: Session, username: str, full_name: str, role: str, executor_id: str | None) -> str | None:
    if db.scalar(select(User).where(User.username == username)) is not None:
        return None
    password = secrets.token_urlsafe(12)
    user = User(username=username, full_name=full_name, password_hash=hash_password(password),
                executor_id=executor_id)
    user.roles = [db.get(Role, role)]
    db.add(user)
    db.flush()
    audit(db, "cli", "user.created", "user", str(user.id), roles=[role], executor_id=executor_id)
    return password


def agency_accounts(role: str) -> list[tuple[str, str, str | None]]:
    """По аккаунту на каждое действующее ведомство и на ДРТ; уже заведённые логины не трогает.

    Возвращает (логин, организация, пароль); пароль None — аккаунт уже был.
    """
    run_migrations()
    rows = []
    with session_scope() as db:
        seed_all(db)
        if db.get(Role, role) is None:
            raise SystemExit(f"Нет роли {role}")
        for username, (full_name, drt_role) in DRT_ACCOUNTS.items():
            rows.append((username, "ДРТ", _create(db, username, full_name, drt_role, None)))
        for x in db.scalars(select(Executor).where(Executor.is_active.is_(True)).order_by(Executor.executor_id)):
            username = _username(x)
            rows.append((username, x.name, _create(db, username, x.name, role, x.executor_id)))
    return rows


def kp_import(path: Path, complete: bool, force: bool, area: str) -> Counter:
    """Выгрузка ФГИС УТКО (scripts/utko_harvest.py, details.jsonl) → реестр КП; потом привязка дел."""
    run_migrations()
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    with session_scope() as db:
        seed_all(db)
        stats = kp.import_utko(db, rows, complete=complete, force=force, area=area or None)
        stats["cases_linked"] = kp.link_cases(db)
        audit(db, "cli", "kp.imported", "kp", "utko", file=path.name, complete=complete, **stats)
    return stats


def kp_codes_gzhi(path: Path) -> Counter:
    """Выгрузка ГЖИ «код КП — utko_id» (CSV через «;») → коды КП по их нумерации и площадки всей области."""
    run_migrations()
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f, delimiter=";"))
    with session_scope() as db:
        seed_all(db)
        stats = kp.import_gzhi_codes(db, rows)
        stats["cases_linked"] = kp.link_cases(db)
        audit(db, "cli", "kp.codes_gzhi", "kp", "gzhi", file=path.name, **stats)
    return stats


def media_cache() -> tuple[int, int]:
    """Забрать в CRM снимки дел, у которых копии ещё нет (дела до 0.6.0 или DG был недоступен)."""
    run_migrations()
    with session_scope() as db:
        ids = [c.id for c in db.scalars(select(Case).order_by(Case.id))
               if any(m.get("type") == "image" and not m.get("crm_file") for m in c.media or [])]
    return len(ids), sum(media.cache_case_media(case_id) for case_id in ids)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    accounts = commands.add_parser("agency-accounts", help="завести аккаунты ведомств и ДРТ")
    accounts.add_argument("--role", default="executor", help="роль аккаунтов ведомств (по умолчанию executor)")
    load = commands.add_parser("kp-import-utko", help="загрузить площадки из выгрузки ФГИС УТКО (details.jsonl)")
    load.add_argument("path", type=Path)
    load.add_argument("--complete", action="store_true",
                      help="выгрузка полная, без сбойных ячеек: пропавшие площадки пометить missing_in_source")
    load.add_argument("--force", action="store_true", help="применить, даже если число площадок скакнуло больше 5 %%")
    load.add_argument("--area", default=kp.UTKO_AREA, help="areaName в выгрузке; пусто — все записи")
    codes = commands.add_parser("kp-codes-gzhi", help="коды КП по нумерации ГЖИ + площадки всей области (CSV)")
    codes.add_argument("path", type=Path)
    commands.add_parser("kp-link-cases", help="заново привязать дела о площадках к ближайшим КП")
    commands.add_parser("media-cache", help="забрать в CRM снимки дел, которых у неё ещё нет")
    args = parser.parse_args(argv)

    if args.command == "agency-accounts":
        rows = agency_accounts(args.role)
        width = max(len(r[0]) for r in rows)
        print("Пароли показываются один раз: сохраните и передайте ведомствам.\n")
        for username, organization, password in rows:
            print(f"{username:<{width}}  {password or '(уже есть)':<18}  {organization}")
    elif args.command == "kp-import-utko":
        try:
            stats = kp_import(args.path, args.complete, args.force, args.area)
        except kp.SyncRefused as exc:
            raise SystemExit(str(exc)) from None
        print(", ".join(f"{k}={v}" for k, v in sorted(stats.items())))
    elif args.command == "kp-codes-gzhi":
        try:
            stats = kp_codes_gzhi(args.path)
        except kp.SyncRefused as exc:
            raise SystemExit(str(exc)) from None
        print(", ".join(f"{k}={v}" for k, v in sorted(stats.items())))
    elif args.command == "kp-link-cases":
        run_migrations()
        with session_scope() as db:
            print(f"привязок изменено: {kp.link_cases(db)}")
    elif args.command == "media-cache":
        cases, saved = media_cache()
        print(f"дел без копии снимков: {cases}, снимков забрано: {saved}")


if __name__ == "__main__":
    main()
