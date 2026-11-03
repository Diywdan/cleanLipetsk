#!/usr/bin/env bash
#
# Продление сертификатов Let's Encrypt.
#
# Certbot продлевает сертификат только когда до окончания остаётся меньше
# 30 дней, поэтому запускать можно хоть каждый день: лишних обращений к
# Let's Encrypt не будет.
#
# Сертификатов у нас несколько: домены интерфейса и отдельный на IP-адрес
# для git-сервера. Следим за ВСЕМИ сразу: раньше проверялся только один
# домен, и когда обновился сертификат на IP, nginx не перечитал
# конфигурацию — git-сервер два дня отдавал просроченный сертификат.
#
# Если хоть один сертификат обновился, nginx перечитывает конфигурацию:
# без этого он продолжит отдавать старый сертификат из памяти. Признак
# обновления — изменение файла цепочки, а не вывод certbot: так надёжнее.
#
# Запуск:  ./renew-cert.sh
# Код возврата 0 — всё в порядке (в том числе когда продлевать нечего).

set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-/home/deploy/document-service}"
CERTS_DIR="$PROJECT_DIR/nginx/certs"

cd "$PROJECT_DIR"

# Отпечатки всех цепочек: имя домена -> sha256 файла.
fingerprints() {
  if [ ! -d "$CERTS_DIR/live" ]; then
    return 0
  fi
  for chain in "$CERTS_DIR"/live/*/fullchain.pem; do
    [ -f "$chain" ] || continue
    printf '%s %s\n' "$(basename "$(dirname "$chain")")" \
      "$(sha256sum "$chain" | cut -d' ' -f1)"
  done | sort
}

before="$(fingerprints)"
count_before=$(printf '%s\n' "$before" | grep -c . || true)

echo "[$(date '+%F %T')] проверка продления сертификатов (найдено: $count_before)"
docker run --rm \
  -v "$CERTS_DIR:/etc/letsencrypt" \
  -v "$PROJECT_DIR/nginx/www:/var/www/certbot" \
  certbot/certbot renew \
  --webroot -w /var/www/certbot \
  --non-interactive 2>&1 | sed 's/^/  /' || true

after="$(fingerprints)"

if [ -z "$before" ]; then
  echo "[$(date '+%F %T')] сертификатов ещё нет — продлевать нечего"
  exit 0
fi

if [ "$before" != "$after" ]; then
  changed=$(comm -13 <(printf '%s\n' "$before") <(printf '%s\n' "$after") \
    | awk '{print $1}' | tr '\n' ' ')
  echo "[$(date '+%F %T')] обновлены сертификаты: ${changed:-не определено}"
  echo "[$(date '+%F %T')] перечитываю конфигурацию nginx"
  docker compose exec -T nginx nginx -s reload
  echo "[$(date '+%F %T')] готово, действуют новые сертификаты"
else
  echo "[$(date '+%F %T')] сертификаты не менялись"
fi

# Проверка со стороны: какие сертификаты теперь лежат и до какой даты.
# Читаем их во временном контейнере: файлы сертификатов принадлежат root,
# и с хоста под deploy их прочитать нельзя.
echo "[$(date '+%F %T')] проверка сертификатов:"
docker run --rm --entrypoint sh -v "$CERTS_DIR:/etc/letsencrypt:ro" \
  certbot/certbot -c '
  for chain in /etc/letsencrypt/live/*/fullchain.pem; do
    [ -e "$chain" ] || continue
    domain=$(basename "$(dirname "$chain")")
    end=$(openssl x509 -in "$chain" -noout -enddate 2>/dev/null | cut -d= -f2)
    echo "  $domain: действует до ${end:-не определено}"
  done' 2>/dev/null || echo "  проверить не удалось"
