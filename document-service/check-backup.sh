#!/usr/bin/env bash
#
# Проверка резервной копии восстановлением.
#
# Копия разворачивается в отдельную базу, после чего её содержимое сверяется
# с описью, снятой в момент копирования (tables.txt, files.txt). Сравнивать
# с рабочей базой нельзя: с момента копии данные могли измениться.
#
# Проверяются: контрольные суммы копии, восстановление базы, число записей
# в каждой таблице, состав и содержимое файлов документов. Пробная база
# удаляется в любом случае, в том числе при ошибке.
#
# Запуск:  ./check-backup.sh              (последняя копия)
#          ./check-backup.sh <каталог>    (конкретная копия)
#
# Код возврата 0 — копия годная, 1 — есть расхождения.

set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-/home/deploy/document-service}"
BACKUP_ROOT="${BACKUP_ROOT:-/home/deploy/backups}"
SCRATCH_DB="${SCRATCH_DB:-restore_check}"
CONTAINER="${CONTAINER:-document-service-postgres}"

cd "$PROJECT_DIR"

copy="${1:-}"
if [ -z "$copy" ]; then
  copy="$(ls -1dt "$BACKUP_ROOT"/*/ 2>/dev/null | head -1)"
fi
if [ -z "$copy" ] || [ ! -d "$copy" ]; then
  echo "копия не найдена: ${copy:-нет ни одной в $BACKUP_ROOT}"
  exit 1
fi
copy="${copy%/}"

DB_USER="$(docker compose exec -T postgres sh -c 'printf %s "$POSTGRES_USER"')"
work="$(mktemp -d)"
failures=0

note() { printf '%s\n' "$*"; }
fail() { failures=$((failures + 1)); note "  ОШИБКА: $*"; }

cleanup() {
  docker exec "$CONTAINER" psql -U "$DB_USER" -d postgres \
    -c "DROP DATABASE IF EXISTS $SCRATCH_DB" >/dev/null 2>&1 || true
  docker exec "$CONTAINER" rm -f /tmp/restore-check.dump >/dev/null 2>&1 || true
  rm -rf "$work"
}
trap cleanup EXIT

note "=== проверка копии $copy ==="

# 1. Целостность самой копии.
if ( cd "$copy" && sha256sum -c SHA256SUMS >/dev/null 2>&1 ); then
  note "контрольные суммы копии: верны"
else
  fail "контрольные суммы копии не совпали"
fi

# 2. Восстановление базы в отдельную базу.
docker exec "$CONTAINER" psql -U "$DB_USER" -d postgres \
  -c "DROP DATABASE IF EXISTS $SCRATCH_DB" >/dev/null 2>&1 || true
docker exec "$CONTAINER" psql -U "$DB_USER" -d postgres \
  -c "CREATE DATABASE $SCRATCH_DB" >/dev/null
docker cp "$copy/db.dump" "$CONTAINER":/tmp/restore-check.dump >/dev/null
if docker exec "$CONTAINER" pg_restore -U "$DB_USER" -d "$SCRATCH_DB" \
     /tmp/restore-check.dump >/dev/null 2>&1; then
  note "дамп развёрнут без ошибок"
else
  fail "pg_restore завершился с ошибкой"
fi

# 3. Сверка записей по таблицам с описью.
checked=0
while read -r table expected; do
  [ -n "$table" ] || continue
  actual="$(docker exec "$CONTAINER" psql -U "$DB_USER" -d "$SCRATCH_DB" -tA \
    -c "select count(*) from \"$table\"" 2>/dev/null || echo "нет таблицы")"
  checked=$((checked + 1))
  if [ "$actual" != "$expected" ]; then
    fail "таблица $table: в копии $expected, восстановлено $actual"
  fi
done < "$copy/tables.txt"
note "таблиц сверено: $checked"

# 4. Состав и содержимое файлов документов.
tar -xzf "$copy/files.tar.gz" -C "$work"
if [ -s "$copy/files.txt" ]; then
  if ( cd "$work" && sha256sum -c "$copy/files.txt" >/dev/null 2>&1 ); then
    note "файлы документов: $(wc -l < "$copy/files.txt") шт., содержимое совпало"
  else
    fail "содержимое файлов документов не совпало с описью"
  fi
  missing="$(cd "$work" && sha256sum -c "$copy/files.txt" 2>/dev/null \
    | grep -c 'FAILED open or read' || true)"
  [ "$missing" -gt 0 ] && fail "не восстановлено файлов: $missing"
else
  note "файлов документов в копии не было"
fi

note "=== итог ==="
if [ "$failures" -gt 0 ]; then
  note "  расхождений: $failures — копия негодная"
  exit 1
fi
note "  копия годная: база разворачивается, данные и файлы совпали с описью"
