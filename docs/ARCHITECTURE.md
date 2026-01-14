# Архитектура Lift CRM

## Обзор стека
- **Backend:** Flask + SQLAlchemy (SQLite, file `lift_crm.db`).【F:app.py†L23-L91】
- **Frontend:** Single-page HTML (Jinja template), Tailwind CDN, Vanilla JS, Leaflet, сервис-воркер для PWA-манифеста.【F:templates/index.html†L1-L27】【F:templates/index.html†L200-L351】
- **Auth:** Flask-Login с cookie-сессиями; роли: admin, dispatcher, master.【F:app.py†L1-L91】【F:templates/index.html†L219-L262】
- **Файлы и данные:** Excel через openpyxl (есть в `vendor/openpyxl`), загрузки в `uploads/`, архив `archive.xlsx`, реестр лифтов в SQL-таблице `assets` (экспорт в CSV/XLSX).【F:liftcrm/db.py†L46-L104】【F:liftcrm/assets/routes.py†L1-L176】

## Карта директорий и ответственности
- `/app.py` — тонкий вход: создаёт приложение через `liftcrm.create_app()` и запускает сервер.【F:app.py†L1-L5】
- `/liftcrm/__init__.py` — фабрика приложения, конфиг, регистрация blueprints, инициализация БД/файлов на первом запросе.【F:liftcrm/__init__.py†L1-L129】
- `/liftcrm/config.py` — корневые пути (архив, объекты, uploads).【F:liftcrm/config.py†L1-L4】
- `/liftcrm/db.py` — engine/SessionLocal/Base + модели Master/User/Ticket/Attachment/Asset и миграции init/ensure.【F:liftcrm/db.py†L1-L122】
- `/liftcrm/extensions.py` — login manager экземпляр.【F:liftcrm/extensions.py†L1-L2】
- `/liftcrm/auth/routes.py` — login/logout/me и user_loader для Flask-Login.【F:liftcrm/auth/routes.py†L1-L35】
- `/liftcrm/tickets/routes.py` — мастера, CRUD заявок, статусы, файлы, архив, метрики, uploads; без изменения путей.【F:liftcrm/tickets/routes.py†L1-L424】
- `/liftcrm/tickets/service.py` — назначение мастеров, геозона, отправка отчёта, архивирование.【F:liftcrm/tickets/service.py†L1-L103】
- `/liftcrm/tickets/repository.py` — сериализация заявок (ответ API).【F:liftcrm/tickets/repository.py†L1-L25】
- `/liftcrm/assets/routes.py` — CRUD + экспорт SQL-реестра лифтов (admin/dispatcher).【F:liftcrm/assets/routes.py†L1-L176】
- `/liftcrm/objects/routes.py` — deprecated alias `/api/objects` → список лифтов из SQL (без Excel runtime).【F:liftcrm/objects/routes.py†L1-L21】
- `/liftcrm/utils/` — security (role_required), time (UTC helper), health endpoint, excel helpers.【F:liftcrm/utils/security.py†L1-L14】【F:liftcrm/utils/time.py†L1-L5】【F:liftcrm/utils/health.py†L1-L6】
- `/templates/index.html` — единственный HTML; UI логика, запросы к API, отрисовка таблиц/канбан/карт, формы, загрузки файлов, реестр лифтов и карта с заявками.【F:templates/index.html†L1-L620】
- `/static/` — PWA манифест и иконки; сервис-воркер `sw.js`.【F:static/manifest.webmanifest†L1-L19】
- `/scripts/seed_assets_from_objects_xlsx.py` — одноразовый сид из `objects.xlsx` в SQL-реестр лифтов (идемпотент).【F:scripts/seed_assets_from_objects_xlsx.py†L1-L104】
- `/archive.xlsx` — итоговый экспорт и накопительный архив удалённых заявок; содержит колонку `priority` для фиксации важности тикетов.【F:liftcrm/tickets/service.py†L39-L97】【F:liftcrm/tickets/routes.py†L390-L421】
- `/vendor/openpyxl` — встроенная копия openpyxl для оффлайн-окружений (подхватывается через sys.path).【F:liftcrm/__init__.py†L7-L20】
- `/uploads/` — создаётся при первом запросе; хранение загруженных фото вложений для заявок.【F:liftcrm/__init__.py†L33-L44】【F:liftcrm/tickets/routes.py†L259-L282】
- `/requirements.txt` — зависимости Python (Flask, SQLAlchemy, Flask-Login/CORS, Pillow, pandas, openpyxl).【F:requirements.txt†L1-L8】

## Основные модели и роли
- `User`: username, password_hash, role (`admin|dispatcher|master`), связь `master_id`.【F:liftcrm/db.py†L27-L43】
- `Master`: справочник мастеров, флаг `is_active`.【F:liftcrm/db.py†L11-L24】
- `Ticket`: заявка со статусами `NEW/ASSIGNED/IN_PROGRESS/COMPLETED/CANCELLED`, координатами, временами прибытия/завершения, e-mail клиента, гео факты прибытия/завершения, вложения, полем **priority** (`HIGH|MEDIUM|LOW`, дефолт MEDIUM), **custom_sla_response_minutes/custom_sla_completion_minutes** (опциональные, только для admin/dispatcher, перекрывают конфиг SLA), **close_reason** и привязкой к `assets` через `asset_id` + summary поля в сериализации.【F:liftcrm/db.py†L46-L112】【F:liftcrm/tickets/repository.py†L17-L43】
- `Asset`: реестр лифтов (адрес, подъезд, метка, серийник, координаты, статус).【F:liftcrm/db.py†L82-L112】
- `Attachment`: файл, связанный с заявкой, лежит в `uploads/`.【F:liftcrm/db.py†L76-L84】

### Связка Users ↔ Masters
- `masters` хранит сущность мастера (ФИО, активность) — без логина/пароля.
- `users` хранит учётные записи. Для ролей `admin/dispatcher` поле `master_id` пустое. Для роли `master` поле `users.master_id` обязательно и указывает на конкретную запись в `masters`.
- Каждому мастеру соответствует ровно один пользователь с `role=master` (создаётся при первичной инициализации и при добавлении мастера). Пароль для мастерского пользователя уникален и выдаётся как временный при создании или через сброс. 【F:liftcrm/db.py†L11-L73】【F:liftcrm/tickets/routes.py†L33-L120】

### Назначение заявок на мастеров
- В заявке поле `tickets.assigned_master_id` ссылается на `masters.id` и определяет исполнителя.
- Автоназанчение выбирает активного мастера с минимальной нагрузкой по открытым статусам (`NEW|ASSIGNED|IN_PROGRESS`).【F:liftcrm/tickets/service.py†L15-L38】
- Ручное назначение/переназначение через `POST /api/tickets/{id}/assign/{master_id}` проставляет `assigned_master_id` (только активным мастерам) и, при необходимости, переводит статус в `ASSIGNED`.【F:liftcrm/tickets/routes.py†L299-L324】
- При удалении или деактивации мастера открытые заявки перераспределяются на других активных мастеров; связанные `users` с ролью master удаляются или остаются в зависимости от операции удаления мастера.【F:liftcrm/tickets/routes.py†L33-L122】

### Карта статусов (бизнес → enum → эндпойнт → таймстемпы)

| Бизнес-термин               | `Ticket.status`  | Основной эндпойнт                    | Таймстемпы               |
|-----------------------------|------------------|--------------------------------------|--------------------------|
| Новая                       | `NEW`            | `POST /api/tickets` (создание)       | `created_at`             |
| Назначена                   | `ASSIGNED`       | автоназначение или `.../assign/{id}` | `created_at`             |
| В пути / На месте (факт прибытия) | `IN_PROGRESS`   | `POST /api/tickets/{id}/arrive`      | `arrived_at`, `arrival_lat/lon` |
| Выполнено                   | `COMPLETED`      | `POST /api/tickets/{id}/complete`    | `completed_at`, `completion_lat/lon`, `close_reason` |
| Отменено                    | `CANCELLED`      | `POST /api/tickets/{id}/cancel`      | —                        |
| (Удалено → архивируется)    | — (запись удаляется) | `DELETE /api/tickets/{id}`          | В архив пишется все поля |

### SLA (ответ и завершение)
- Конфиги SLA в минутах: `SLA_RESPONSE_MINUTES` (по умолчанию 30) и `SLA_COMPLETION_MINUTES` (по умолчанию 120) в `liftcrm/config.py`. Админ/диспетчер могут задать кастомные минуты в полях заявки `custom_sla_response_minutes/custom_sla_completion_minutes` (валидация >0), чтобы перекрыть конфиг только для конкретного тикета.【F:liftcrm/tickets/routes.py†L174-L240】【F:templates/index.html†L38-L78】【F:templates/index.html†L268-L334】
- Дедлайны рассчитываются на лету: `created_at + SLA_{...}_MINUTES`, где приоритет — кастомные поля заявки, иначе значения конфига; в сериализации тикета добавлены поля с дедлайнами, флагами нарушения и оставшимися минутами (могут быть отрицательными).【F:liftcrm/tickets/repository.py†L10-L68】
- Нарушение фиксируется как по факту (arrived/completed позже дедлайна), так и для открытых заявок, если текущее время вышло за пределы SLA. Экспорт `archive.xlsx` включает флаги нарушений и кастомные SLA; метрики `/api/metrics` дополнены счётчиками/процентами нарушений, UI их визуализирует в таблице, канбане и дашборде.【F:liftcrm/tickets/routes.py†L142-L212】【F:liftcrm/tickets/routes.py†L390-L421】【F:templates/index.html†L268-L341】【F:templates/index.html†L520-L567】
- Метрики `/api/metrics` дополнительно выдают `tickets_by_close_reason`, `sla_breaches_by_reason` и `tickets_by_priority` для аналитики причин/важности в UI/архивах.【F:liftcrm/tickets/routes.py†L212-L242】【F:templates/index.html†L531-L548】

## Existing behaviors (frozen)
- Автоназанчение: используется только активные мастера; метрика нагрузки — количество открытых заявок в статусах `NEW/ASSIGNED/IN_PROGRESS`, выбирается минимальная нагрузка (и минимальный id как тайбрейк).【F:liftcrm/tickets/service.py†L15-L38】
- Переназначение при удалении/деактивации мастера: все открытые заявки (`NEW/ASSIGNED/IN_PROGRESS`) переводятся на других активных мастеров по той же логике минимальной нагрузки; если активных мастеров нет — операция запрещена.【F:liftcrm/tickets/routes.py†L33-L122】
- Ограничение: назначение/переназначение возможно только на активных мастеров; закрытые (`COMPLETED/CANCELLED`) заявки не учитываются при распределении.

## Потоки запросов (текстовые диаграммы)

### 1) Логин
`/templates/index.html` → `POST /api/login` → проверка пользователя, `login_user`, ответ `role/username/master_id` → фронт вызывает `/api/me` для актуализации UI.【F:app.py†L149-L167】【F:templates/index.html†L219-L262】

### 2) Список заявок
UI: `loadTickets()` → `GET /api/tickets` (auth required) → SQLAlchemy выборка всех Ticket → сериализация (мастер, статусы, вложения, тайминги) → JSON → отрисовка таблицы и канбана.【F:app.py†L223-L262】【F:templates/index.html†L255-L334】

### 3) Создание заявки
UI форма с выбором лифта + приоритета (`HIGH|MEDIUM|LOW`, дефолт MEDIUM) → `POST /api/tickets` (admin/dispatcher) c `object_name`, `lat`, `lon`, опционально `asset_id/address/description/email/priority` → сервер создаёт Ticket, автоназначает активного мастера (балансировка) и привязывает/создаёт asset → статус `ASSIGNED|NEW` → ответ id/assigned/status → UI обновляет список/канбан.【F:liftcrm/tickets/routes.py†L174-L223】【F:templates/index.html†L33-L87】

### 4) Изменение приоритета
Админ/диспетчер могут изменить приоритет заявки через `PATCH /api/tickets/{id}` c JSON `{ "priority": "HIGH|MEDIUM|LOW" }`; поле доступно из таблицы заявок (select рядом с бейджем).【F:liftcrm/tickets/routes.py†L204-L236】【F:templates/index.html†L285-L334】

### 5) Назначение мастера (ручное)
UI `showReassign()` выбирает master → `POST /api/tickets/{id}/assign/{master_id}` (admin/dispatcher) → проверка активности мастера → обновление `assigned_master_id`, статус `ASSIGNED` если нужно → JSON подтверждение → UI перерисовывает списки.【F:app.py†L618-L639】【F:templates/index.html†L308-L334】

### 6) Обновление статуса мастером
- **Прибыл:** мастерский UI → геолокация → `POST /api/tickets/{id}/arrive` (role master) → проверка владельца, геозона 500 м (haversine) → статус `IN_PROGRESS`, `arrived_at`, координаты прибытия → JSON.【F:app.py†L370-L405】【F:templates/index.html†L349-L419】
- **Завершил:** мастерский UI → выбор причины закрытия (dropdown, без неё кнопка блокируется) → геолокация → `POST /api/tickets/{id}/complete` (role master) → проверки аналогичны → статус `COMPLETED`, `completed_at`, координаты завершения, `close_reason` из разрешённого списка → попытка `send_report()` по email → JSON.【F:liftcrm/tickets/routes.py†L184-L214】【F:templates/index.html†L373-L421】

### 7) Отмена / удаление и архив
- **Отмена:** `POST /api/tickets/{id}/cancel` (admin/dispatcher) → статус `CANCELLED` → ответ.【F:app.py†L326-L338】【F:templates/index.html†L287-L299】
- **Удаление:** `DELETE /api/tickets/{id}` (admin/dispatcher) → `archive_ticket()` пишет строку в `archive.xlsx` (и копию `archive_N.xlsx`), удаляет вложения с диска → удаляет Ticket → ответ. Экспортируемый архив содержит колонку `close_reason` для аналитики причин закрытия.【F:liftcrm/tickets/service.py†L39-L83】【F:liftcrm/tickets/routes.py†L390-L433】

### 8) Скачивание архива
UI кнопка → `GET /api/archive` (admin/dispatcher) → в рантайме создаётся новый `archive.xlsx` со всеми текущими заявками через openpyxl → send_from_directory с attachment.【F:app.py†L667-L693】【F:templates/index.html†L464-L472】

### 9) Загрузка объектов для карты
`GET /api/assets` (auth) → SQL-реестр лифтов → фронт строит Leaflet circleMarker, поиск по адресам/серийникам/меткам, доп. слой открытых заявок через `GET /api/tickets?include_archived=0`.【F:liftcrm/assets/routes.py†L1-L176】【F:templates/index.html†L430-L566】

## Технический долг и риски
- **Монолитный файл** `app.py` объединяет модели, API, миграции, утилиты; трудно расширять и тестировать по слоям.【F:app.py†L23-L804】
- **SQLite в файле** (`lift_crm.db`) без блокировок и бэкапов; конкурентные записи/удаления могут блокировать файл, нет миграций через Alembic.【F:app.py†L34-L118】
- **Нет валидации входных данных** (Pydantic отсутствует); потенциальные ValueError/TypeError и слабая защита от неверных типов.【F:app.py†L264-L444】
- **Глобальные побочные эффекты** в `before_request` (инициализация БД/директорий/файлов) — дорого при первом запросе, сложно тестировать, риск гонок при многопроцессном запуске.【F:app.py†L124-L180】
- **openpyxl копия** (`vendor/openpyxl`) + системная установка — разные версии могут расходиться, нет проверки совместимости.【F:app.py†L12-L21】
- **Отсутствие CSRF/HTTPS настроек**; CORS разрешён с cred-сессиями без ограничений origin.【F:app.py†L22-L33】
- **Файлы загрузок без вирус-скана/квот**; путь хранения в локальной ФС, нет S3/backup, нет очистки старых вложений вне удалений заявок.【F:app.py†L568-L616】
- **Архивирование на удаление** создаёт копии `archive_N.xlsx` без лимита → рост диска, отсутствие ротации.【F:app.py†L216-L259】
- **Логика геозоны/статусов в UI и backend дублируется**, нет централизованного enum/констант, возможны рассинхроны.【F:app.py†L347-L444】【F:templates/index.html†L255-L419】
