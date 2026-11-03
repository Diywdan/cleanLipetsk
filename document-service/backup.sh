#!/usr/bin/env bash
#
# Резервная копия базы и файлов документов.
#
# Копия складывается в /home/deploy/backups/<дата-время>/:
#   db.dump      — дамп базы в собственном формате PostgreSQL
#   files.tar.gz — каталог data с файлами документов
#   tables.txt   — сколько записей было в каждой таблице на момент копии
#   files.txt    — контрольные суммы всех файлов документов
#   SHA256SUMS   — суммы самих файлов копии
#
# Опись (tables.txt, files.txt) нужна для проверки: восстановленную копию
# сравнивают с ней, а не с рабочей базой — рабочая с момента копии могла
# измениться, и такое сравнение давало бы ложные расхождения.
#
# Запуск:  ./backup.sh          (обычный запуск, с ротацией)
#          KEEP=30 ./backup.sh  (хранить 30 копий)
#
# Каталог копий доступен только владельцу: в дампе персональные данные.

set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-/home/deploy/document-service}"
BACKUP_ROOT="${BACKUP_ROOT:-/home/deploy/backups}"
KEEP="${KEEP:-7}"

cd "$PROJECT_DIR"

stamp="$(date +%Y%m%d-%H%M%S)"
target="$BACKUP_ROOT/$stamp"
mkdir -p "$target"
chmod 700 "$BACKUP_ROOT" "$target"

# Имена базы и пользователя берём из окружения контейнера — там же, откуда
# их берёт само приложение.
DB_USER="$(docker compose exec -T postgres sh -c 'printf %s "$POSTGRES_USER"')"
DB_NAME="$(docker compose exec -T postgres sh -c 'printf %s "$POSTGRES_DB"')"

echo "[$(date '+%F %T')] копия $stamp: дамп базы"
docker compose exec -T postgres sh -c \
  'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -F c -f /tmp/document-service.dump'
docker compose cp postgres:/tmp/document-service.dump "$target/db.dump" >/dev/null
docker compose exec -T postgres rm -f /tmp/document-service.dump

echo "[$(date '+%F %T')] копия $stamp: опись таблиц"
docker compose exec -T postgres psql -U "$DB_USER" -d "$DB_NAME" -tA -F' ' -c "
  select tablename,
         (xpath('/row/c/text()',
                query_to_xml(format('select count(*) as c from %I.%I', schemaname, tablename),
                             false, true, '')))[1]::text::bigint
    from pg_tables
   where schemaname = 'public'
   order by tablename" > "$target/tables.txt"

echo "[$(date '+%F %T')] копия $stamp: файлы документов"
tar -czf "$target/files.tar.gz" -C "$PROJECT_DIR" data
find data/files -type f -exec sha256sum {} + 2>/dev/null | sort -k2 > "$target/files.txt" \
  || : > "$target/files.txt"

echo "[$(date '+%F %T')] копия $stamp: контрольные суммы"
(
  cd "$target"
  sha256sum db.dump files.tar.gz tables.txt files.txt > SHA256SUMS
  du -sh db.dump files.tar.gz
  echo "записей в таблицах: $(awk '{s += $2} END {print s}' tables.txt)"
  echo "файлов документов:  $(wc -l < files.txt)"
)

# Ротация: список каталогов от новых к старым, всё после KEEP-го удаляем.
if [ "$KEEP" -gt 0 ]; then
  removed=0
  while IFS= read -r old; do
    rm -rf "$old"
    removed=$((removed + 1))
  done < <(ls -1dt "$BACKUP_ROOT"/*/ 2>/dev/null | tail -n +"$((KEEP + 1))")
  [ "$removed" -gt 0 ] && echo "[$(date '+%F %T')] удалено старых копий: $removed"
fi

echo "[$(date '+%F %T')] копия $stamp готова: $target"
