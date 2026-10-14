npm run dev

## Карта

Подложка — свой файл тайлов OpenStreetMap по Липецкой области (`lipetsk.pmtiles`, ~130 МБ, вектор Protomaps,
зум до 15): ни ключа, ни запросов к чужим серверам. Рисует Leaflet, тон подложки следует теме.
В git файла нет:

- для `npm run dev` и стенда без бэкенда положите его в `public/maps/lipetsk.pmtiles`;
- сборка для CRM (`npm run build:crm`) его не включает: CRM отдаёт файл по `/maps/` из своей папки `maps/`.

Где взять: со стенда CRM (`http://10.248.55.165:18081/maps/lipetsk.pmtiles`, из сети ЦОД) или вырезать
свежий из сборки Protomaps:

```bash
pmtiles extract https://build.protomaps.com/<ГГГГММДД>.pmtiles lipetsk.pmtiles --bbox=37.6,51.85,40.8,53.75 --maxzoom=15
```

Сервер обязан отдавать файл кусками (HTTP Range): Vite, nginx и CRM умеют, `python -m http.server` — нет,
карта на нём будет пустой. Нет файла — на карте подпись с адресом, по которому его искали.
Другой адрес файла — переменная `VITE_MAP_TILES_URL`.
