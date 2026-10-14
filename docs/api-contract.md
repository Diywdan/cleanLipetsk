# Контракт API «Чистый Липецк» (черновик для бэкенда)

Фронт работает через два интерфейса:
- `IncidentApi` в `src/entities/incident/api/incidentApi.ts`;
- `KpApi` в `src/entities/kp/model/kpApi.ts`.

Есть две реализации:
- **макет** в браузере — для стенда;
- **HTTP** — включается переменной `VITE_API_URL`. Работает с CRM «Чистый Липецк» (`Diywdan/chisto-crm`):
  сборка `npm run build:crm` (адрес `/api/v1` из `.env.crm`), CRM отдаёт её с того же адреса, что и API.

Типы данных лежат в `src/entities/incident/types/index.ts` и `src/entities/kp/types.ts`. Правила переходов лежат в `src/entities/incident/lib/workflow.ts`, тесты к ним — в `workflow.test.ts`.

## Общее

- Формат — JSON, даты в ISO 8601 UTC, координаты `[долгота, широта]` (как в GeoJSON).
- Авторизация — кука сессии CRM (`credentials: 'include'`). Автора действия бэкенд определяет по сессии, фронт его не передаёт.
- Ошибка — HTTP-статус плюс тело `{ "message": "текст для человека" }`. Фронт показывает `message` в карточке дела.
  - `403` — роли нельзя;
  - `409` — статус дела не позволяет;
  - `422` — неверные данные.
- Права и переходы бэкенд **проверяет сам**. Фронт держит у себя копию тех же правил только для того, чтобы показывать нужные кнопки.

## Вход

| Метод | Путь | Тело | Ответ |
|---|---|---|---|
| POST | `/auth/login` | `{ "username", "password" }` | `204` и кука сессии; `401` — неверный логин или пароль |
| POST | `/auth/logout` | — | `204` |
| GET | `/auth/me` | — | пользователь: `id`, `name`, `role` (`INSPECTOR` \| `UK` \| `ADMIN`), `department`, `organizationName` |

Без сессии фронт показывает экран входа; `401` посреди работы возвращает на него. Роль выводится из прав:
ведёт дела — `INSPECTOR`, сдаёт фотоотчёт — `UK` (видит только дела своей организации), только смотрит — `ADMIN`.
Учётные записи ДРТ и ведомств заводит CRM (`python -m app.cli agency-accounts`).

## Обращения

| Метод | Путь | Тело | Ответ |
|---|---|---|---|
| GET | `/incidents` | — | `IIncident[]` |
| POST | `/incidents/{id}/confirm` | `{ "deadlineHours": 24 \| 48 \| 72, "executorId"?: string, "typeViolationId"?: string }` | `IIncident` |
| POST | `/incidents/{id}/dismiss` | `{ "reason"?: string }` | `IIncident` |
| POST | `/incidents/{id}/report` | `{ "report": IPhotoReport }` | `IIncident` |
| POST | `/incidents/{id}/approve` | `{}` | `IIncident` |
| POST | `/incidents/{id}/return` | `{ "comment"?: string }` | `IIncident` |
| POST | `/incidents/{id}/escalate` | `{}` | `IIncident` |
| POST | `/incidents/{id}/act` | `{}` | `IIncident` |

В ответе всегда дело целиком после действия, вместе с новой записью в `timeline.history`.

`executorId` и `typeViolationId` в confirm передаются, только если инспектор поменял исполнителя или тип
нарушения. CRM проверяет, что ведомство и тип активны и ведомство отвечает за этот тип (иначе `422`), и пишет
замену в хронику. Подтверждение без них оставляет пару как пришла, даже с расхождением со справочником;
CRM отмечает это в хронике и снимает `reviewReason`.

### Маршрут дела

| Действие | Кто | Из статуса | В статус | Что ещё меняется |
|---|---|---|---|---|
| confirm | инспектор | NEW | IN_PROGRESS | `validatedAt`, `deadlineAt` = сейчас + срок. Срок по матрице SLA: поручение руководства — 24 ч, портал губернатора — 72 ч, Дело-web — 720 ч, остальные — выбор инспектора |
| dismiss | инспектор | NEW | CLOSED | `closedAt`, `resolution = FALSE_POSITIVE` |
| report | мастер УК | IN_PROGRESS | VERIFICATION | `media.photoAfterUrl`, `media.report` |
| approve | инспектор | VERIFICATION | CLOSED | `closedAt`, `resolution = FIXED` |
| return | инспектор | VERIFICATION | IN_PROGRESS | срок **не** продлевается |
| escalate | система или инспектор | IN_PROGRESS | KNM_ESCALATION | только если `deadlineAt` уже прошёл |
| act | инспектор | KNM_ESCALATION | — | запись «Сформирован акт» в хронике |

Руководство (`ADMIN`) только смотрит.

Сейчас эскалацию по сроку запускает таймер в открытой карточке. На бэкенде это должна быть **фоновая задача**: дело уходит на КНМ, даже если его никто не открыл.

### Фотоотчёт

```ts
interface IPhotoReport {
  photoUrl: string;          // на бэкенде — ссылка на загруженный файл
  takenAt: string;           // время съёмки; надёжнее брать из EXIF на сервере
  coords?: [number, number]; // где был телефон при отправке
  distanceM?: number;        // расстояние до площадки, м; > 150 м — пометка инспектору
  comment?: string;
}
```

Сейчас фото уходит в теле запроса строкой data URL: JPEG до 1280 px, около 150–300 КБ. Для бэкенда предлагается отдельная загрузка:
1. `POST /files` (multipart) возвращает `{ "url": "…" }`;
2. в `report` передаётся уже `url`.

Расстояние до площадки стоит пересчитывать на сервере.

## Справочник КП

| Метод | Путь | Ответ |
|---|---|---|
| GET | `/kp` | `IKpCard[]` |

Справочник ведёт CRM (решение совещания 07.10); другие системы получают его через Data Gateway. Адрес задаётся в `createKpApi` в одном месте.

Статистику по площадке фронт сейчас считает сам из обращений (`src/entities/kp/lib/registry.ts`):
- нарушений за 30 дней;
- открыто сейчас;
- на КНМ;
- ложных срабатываний;
- среднее время устранения.

Когда обращений станет много, эти числа лучше отдавать с бэкенда: `GET /kp/{id}/stats`.

## Справочник ведомств и типов нарушений

| Метод | Путь | Ответ |
|---|---|---|
| GET | `/executors` | ведомства с их типами нарушений |

Это справочник CRM как есть, поля в snake_case: `executor_id`, `name`, `kind`, `is_active`,
`violation_types[]` (`type_violation_id`, `name`, `is_active`). Нужен инспектору при подтверждении дела,
фронт берёт только активные (`src/entities/executor/model/executorApi.ts`). Без бэкенда справочника нет,
и выбор исполнителя не показывается.

## Чего в контракте пока нет

- Пагинации и фильтров на сервере: сейчас `GET /incidents` отдаёт всё.
- Уведомлений исполнителю: бот работает только через Gateway, решение от 07.10.
