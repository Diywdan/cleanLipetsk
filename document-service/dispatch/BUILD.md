# Интерфейс диспетчера: сборка и выкладка

Здесь лежит всё, что нужно, чтобы собрать и обновить интерфейс диспетчера
(«Чистый Липецк») без чьей-либо помощи.

## Что где лежит

| Что | Где |
|---|---|
| Наши патчи к их фронту | `project/dispatch/patches/0001…*.patch` |
| Зеркало фронта с патчами | Forgejo: `andrey/cleanLipetsk`, ветка `main` |
| Их исходники | GitHub: `Oxana48/cleanLipetsk` (мы туда не пишем) |
| Готовая сборка на сервере | `/home/deploy/document-service/dispatch/` |

Патчи — обычные git-патчи. Они применяются к их ветке `main` и не требуют
ручного слияния: правки мелкие и не пересекаются между собой.

## Сборка

Нужен Node.js 20+ и установленные зависимости (`pnpm install`).

```bash
cd cleanLipetsk

# Переменные сборки. Обе важны:
#   VITE_API_URL   — куда стучаться за данными (относительный путь, чтобы
#                    работало и по IP, и по домену);
#   VITE_MAP_TILES — подложка карты: свой слепок Липецка (см. ниже).
export VITE_API_URL=/api
export VITE_MAP_TILES='/tiles/styles/basic-preview/{z}/{x}/{y}.png'

node node_modules/vite/bin/vite.js build --base=/dispatch/
```

Если `VITE_MAP_TILES` не задать, карта возьмёт подложку CARTO по умолчанию —
она работает, но требует ключа и зависит от чужого сервиса.

## Выкладка

```bash
scp -r dist/* deploy@82.202.140.51:/home/deploy/document-service/dispatch/
ssh deploy@82.202.140.51 'chmod -R a+rX /home/deploy/document-service/dispatch'
```

Каталог `dispatch` подключён к nginx томом и раздаётся по адресу
`https://chili.moneta-rus.pro/dispatch/` — перезапуск не нужен, достаточно
обновить страницу с очисткой кэша (Ctrl+F5).

## Обновление с их стороны

Если их репозиторий ушёл вперёд:

```bash
git remote add upstream https://github.com/Oxana48/cleanLipetsk.git   # один раз
git fetch upstream
git checkout -b upstream-$(date +%Y%m%d) upstream/main
git am ../project/dispatch/patches/*.patch        # накатываем наши правки
```

Если какой-то патч не накладывается — значит, они правили тот же файл;
конфликт решается вручную, после чего патч пересобирается:

```bash
git format-patch -1 --stdout > ../project/dispatch/patches/00NN-имя.patch
```

## Карта: свой слепок

Подложка карты — локальный слепок Липецка, внешние сервисы не участвуют.

* файл: `/home/deploy/document-service/tiles/lipetsk.mbtiles` (≈4 МБ, масштабы 0–14);
* раздача: контейнер `map-tiles` (tileserver-gl) + прокси nginx по пути `/tiles/`;
* пересборка слепка: `/home/deploy/tiles-build.sh` — качает свежие данные
  OpenStreetMap и собирает тайлы заново (около 20 минут). Разумно раз в полгода;
* за границами города подложки нет (серые поля) — если понадобится шире,
  в скрипте меняется рамка `--bbox`.

## Что проверять после выкладки

```bash
curl -s -o /dev/null -w '%{http_code}\n' https://chili.moneta-rus.pro/dispatch/
curl -s -o /dev/null -w '%{http_code}\n' https://chili.moneta-rus.pro/tiles/styles/basic-preview/12/2515/1338.png
```

Оба адреса должны отвечать `200`. Второй — тайл карты: если он отдаётся,
значит слепок и сервер тайлов живы.
