#!/usr/bin/env bash
#
# Выпуск сертификата Let's Encrypt для домена сервиса.
#
# Запускается один раз для нового имени (продлением занимается renew-cert.sh).
# Порядок работы скрипта:
#
#   1. проверяет, что домен уже указывает на наш сервер: без этого Let's
#      Encrypt не сможет убедиться, что домен наш, и выпуск провалится;
#   2. выпускает сертификат через certbot в контейнере — так же, как это
#      делает продление;
#   3. перечитывает конфигурацию nginx: без этого он продолжит работать со
#      старым набором сертификатов.
#
# Блок сервера для домена в nginx добавляется отдельно (в репозитории), потому
# что nginx не запустится, если файла сертификата ещё нет.
#
# Запуск:  ./issue-cert.sh chili.moneta-rus.pro
# Код возврата 0 — сертификат на месте.

set -euo pipefail

DOMAIN="${1:-${DOMAIN:-}}"
PROJECT_DIR="${PROJECT_DIR:-/home/deploy/document-service}"
SERVER_IP="${SERVER_IP:-82.202.140.51}"

if [ -z "$DOMAIN" ]; then
  echo "укажите домен: ./issue-cert.sh chili.moneta-rus.pro" >&2
  exit 2
fi

echo "[$(date '+%F %T')] домен: $DOMAIN"

# 1. Домен должен указывать на нас.
resolved="$(getent ahostsv4 "$DOMAIN" | awk '{print $1}' | sort -u | tr '\n' ' ' || true)"
if [ -z "$resolved" ]; then
  echo "  домен не разрешается: сначала поправьте DNS (делегирование и A-запись)" >&2
  exit 1
fi
echo "  домен указывает на: $resolved"
case "$resolved" in
  *"$SERVER_IP"*) ;;
  *)
    echo "  внимание: среди адресов нет $SERVER_IP — Let's Encrypt может не дойти" >&2
    ;;
esac

# 2. Сертификат.
docker run --rm \
  -v "$PROJECT_DIR/nginx/certs:/etc/letsencrypt" \
  -v "$PROJECT_DIR/nginx/www:/var/www/certbot" \
  certbot/certbot certonly \
  --webroot -w /var/www/certbot \
  -d "$DOMAIN" \
  --non-interactive --agree-tos --keep-until-expiring 2>&1 | sed 's/^/  /'

# Проверяем саму ссылку, а не файл за ней: каталог archive принадлежит root
# с ограниченными правами, и обычный пользователь не сможет заглянуть внутрь.
if [ ! -L "$PROJECT_DIR/nginx/certs/live/$DOMAIN/fullchain.pem" ] \
   && [ ! -f "$PROJECT_DIR/nginx/certs/live/$DOMAIN/fullchain.pem" ]; then
  echo "  сертификат не выпущен — смотрите вывод выше" >&2
  exit 1
fi
echo "  сертификат: $PROJECT_DIR/nginx/certs/live/$DOMAIN/fullchain.pem"

# 3. Nginx перечитывает конфигурацию.
cd "$PROJECT_DIR"
docker compose exec -T nginx nginx -t 2>&1 | tail -1 | sed 's/^/  /'
docker compose exec -T nginx nginx -s reload
echo "[$(date '+%F %T')] готово"
