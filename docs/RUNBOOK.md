# Runbook — Lift CRM

## Быстрый старт (локально)
1) Зависимости: `python -m pip install -r requirements.txt` (Python 3.11+).【F:requirements.txt†L1-L8】  
2) Запуск: `python app.py` (поднимает Flask dev-server на `http://127.0.0.1:5000`).【F:app.py†L773-L804】  
3) Аккаунты для входа:
   - admin / `admin123`
   - dispatcher / `disp123`
   - Доступ мастеров назначается вручную через страницу «Пользователи и допуск» (админ создаёт профиль мастера и назначает роль TECHNICIAN).【F:templates/index.html†L203-L334】

## Что создаётся автоматически
- База `lift_crm.db` (SQLite) и таблицы при первом запросе (hook `before_request`).【F:app.py†L124-L180】
- Каталог `uploads/` для файлов вложений и таблица `assets` в SQLite (создаётся миграцией при первом запросе).【F:liftcrm/db.py†L95-L142】
- Файл `archive.xlsx` (пустой с заголовками, включая колонку priority) для скачивания архива заявок.【F:liftcrm/__init__.py†L68-L104】

## Пользователи и допуск
- Админская вкладка «Пользователи и допуск» разделяет доступы (Users) и профили сотрудников (Masters).【F:templates/index.html†L203-L334】
- Пользователи: смена роли, отключение доступа, сброс пароля.  
- Мастера: назначение роли TECHNICIAN, сброс пароля связанного пользователя, замена сотрудника с переносом открытых заявок.  

## Приоритеты заявок
- Enum: HIGH («Очень важно»), MEDIUM («Нужно сделать», значение по умолчанию), LOW («Не срочно»).【F:liftcrm/tickets/routes.py†L20-L27】【F:liftcrm/db.py†L46-L77】
- Установка при создании: поле «Приоритет» в форме тикета; бэкенд ожидает строку enum, иначе 400. Дефолт — MEDIUM, SLA не изменяется.【F:liftcrm/tickets/routes.py†L174-L202】【F:templates/index.html†L33-L69】
- Изменение после создания: админ/диспетчер → таблица заявок → выпадающий список, отправляется `PATCH /api/tickets/{id}` с новым приоритетом.【F:liftcrm/tickets/routes.py†L204-L236】【F:templates/index.html†L285-L334】
- Отображение: таблица, канбан, карточки мастера и метрики показывают цветовые бейджи (красный для HIGH, нейтральный для MEDIUM, приглушённый для LOW).【F:templates/index.html†L270-L334】【F:templates/index.html†L335-L380】【F:templates/index.html†L360-L421】【F:templates/index.html†L616-L647】

## SLA: контроль ответа и завершения
- SLA ответа = `created_at` → `arrived_at`; SLA завершения = `created_at` → `completed_at`.
- Дедлайны считаются динамически из `SLA_RESPONSE_MINUTES` и `SLA_COMPLETION_MINUTES`; по умолчанию 30/120 минут, можно переопределять через переменные окружения.
- **Перекрытие по тикету:** admin/dispatcher могут задать `custom_sla_response_minutes` и/или `custom_sla_completion_minutes` (целые >0) при создании/редактировании заявки. Эти поля перекрывают значения конфига только для выбранного тикета. Поля скрыты для мастера и доступны через форму создания/таблицу (кнопка «Сохранить» рядом с заявкой). В API `PATCH /api/tickets/{id}` можно передавать только SLA поля (priority становится опциональным).【F:liftcrm/tickets/routes.py†L174-L240】【F:templates/index.html†L33-L78】【F:templates/index.html†L268-L334】
- Нарушение фиксируется, если время факта позже дедлайна или если факт отсутствует, а текущее время уже вышло за срок. Флаги отображаются в таблице заявок, карточках канбана/дашборда и выгружаются в `archive.xlsx` (добавлены колонки custom_sla_*).【F:liftcrm/tickets/repository.py†L10-L68】【F:liftcrm/tickets/routes.py†L390-L421】
- API `/api/metrics` отдаёт счётчики и проценты нарушений, UI показывает их в блоке «Дашборд выполнения».
- При завершении тикета мастер обязан выбрать `close_reason` из списка (EQUIPMENT_FAILURE/PASSENGER_TRAPPED/FALSE_CALL/POWER_ISSUE/EXTERNAL_REASON/OTHER); поле отражается в API, метриках и выгрузке архива.【F:liftcrm/tickets/routes.py†L184-L241】【F:templates/index.html†L373-L421】

## Архивация заявок (soft-delete)
- `DELETE /api/tickets/{id}` больше не удаляет строку из БД, а проставляет `archived_at`; вложения остаются, запись скрывается из активного списка.【F:liftcrm/tickets/routes.py†L360-L372】
- `GET /api/tickets` по умолчанию отдаёт только активные заявки; добавьте `?include_archived=1`, чтобы увидеть архивированные (для админа/диспетчера).【F:liftcrm/tickets/routes.py†L153-L162】
- Экспорт `GET /api/archive` выгружает все заявки (активные + архив) и отдельные столбцы `archived_at` и `close_reason` в XLSX.【F:liftcrm/tickets/routes.py†L390-L433】
- При запуске выполняется миграция SQLite: колонка `archived_at` добавляется автоматически, если её ещё нет.【F:liftcrm/db.py†L107-L125】

## Реестр лифтов (Assets)
- CRUD доступен для admin/dispatcher: `GET/POST/PATCH /api/assets`.【F:liftcrm/assets/routes.py†L1-L129】
- Экспорт реестра: `GET /api/assets/export.xlsx` и `GET /api/assets/export.csv`.【F:liftcrm/assets/routes.py†L132-L176】
- Разовый сид из Excel: `python scripts/seed_assets_from_objects_xlsx.py` (читает `objects/objects.xlsx`, идемпотентно создаёт/обновляет assets и по возможности связывает существующие тикеты).【F:scripts/seed_assets_from_objects_xlsx.py†L1-L104】

## Типовой флоу проверки
1. Запустить сервер.  
2. Войти как admin.  
3. Создать заявку (форма на главной).  
4. Проверить автоназначение мастера и отображение в таблице/канбане.  
5. Скачать архив через кнопку «Скачать архив».
6. Переключиться на masterN, открыть `/mobile`, нажать «Принять», затем «В работу» (для перехода `ACCEPTED → IN_PROGRESS` нужна геолокация и попадание в радиус 500 м от объекта), после работ нажать «Завершить» с обязательной причиной закрытия.
7. Открыть вкладку «Объекты» и убедиться, что точки отображаются из SQL-реестра лифтов, а переключатель «Показывать заявки» показывает открытые тикеты.

## Частые ошибки и решения
- **`Missing dependency: openpyxl` при скачивании архива.**  
  Установите зависимости (`python -m pip install -r requirements.txt`) или используйте встроенный `vendor/openpyxl` (подхватывается автоматически).【F:app.py†L12-L21】【F:app.py†L667-L693】
- **`uploads` нет / ошибка сохранения файла.**  
  Каталог создаётся в `before_request`. Убедитесь, что процесс имеет права на запись в корень проекта или создайте `uploads/` вручную.【F:app.py†L124-L144】【F:app.py†L568-L616】
- **Блокировки SQLite / ошибки записи.**  
  Закройте другие процессы, удалите `lift_crm.db` для сброса (потеря данных), перезапустите сервер. SQLite не рассчитан на высокую конкуренцию.
- **Геолокация отклонена в браузере.**  
  В `/mobile` координаты требуются при переводе принятой заявки «В работу» из `ACCEPTED`; legacy-кнопки «Приехал/Завершить» тоже требуют координаты. Разрешите доступ или используйте ручную подстановку координат в DevTools.
- **Архив растёт (archive_N.xlsx).**  
  Удалите лишние `archive_*.xlsx` вручную; ротации нет.【F:app.py†L183-L259】

## Конфигурация и секреты
- Файл примера: `.env.example` содержит все поддерживаемые переменные окружения.
- Обязательные в проде (dev имеет дефолты):
  - `SECRET_KEY` — ключ сессий Flask (dev по умолчанию `dev-secret`, обязательно переопределить в проде).【F:liftcrm/config.py†L7-L18】【F:liftcrm/__init__.py†L12-L33】
  - `ADMIN_USERNAME` / `ADMIN_PASSWORD` — креды админа (dev: `admin` / `admin123`).【F:liftcrm/config.py†L7-L18】【F:liftcrm/db.py†L58-L73】
  - `DISPATCHER_USERNAME` / `DISPATCHER_PASSWORD` — креды диспетчера (dev: `dispatcher` / `disp123`).【F:liftcrm/config.py†L7-L18】【F:liftcrm/db.py†L58-L73】
  - `SLA_RESPONSE_MINUTES`, `SLA_COMPLETION_MINUTES` — опциональные, задают лимиты SLA в минутах (30/120 по умолчанию).【F:liftcrm/config.py†L7-L23】
- Опционально:
  - `SMTP_SERVER`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD` — для email-отправки отчёта при завершении; если пусто, отправка пропускается.【F:liftcrm/config.py†L20-L23】【F:liftcrm/tickets/service.py†L43-L77】
- Файлы и данные:
  - БД: `lift_crm.db` в корне.
  - Архив: `archive.xlsx` и копии `archive_N.xlsx` в корне.
- Реестр лифтов: таблица `assets` в `lift_crm.db` (экспорт в CSV/XLSX).
  - Вложения: `uploads/` в корне.

## Мониторинг/здоровье
- `/api/health` — простой health-check (без auth).【F:liftcrm/utils/health.py†L1-L6】

## Логирование и ошибки
- Логирование: консоль, формат `%(asctime)s %(levelname)s [%(name)s] %(message)s`, уровень по умолчанию INFO; можно переопределить `LOG_LEVEL`.【F:liftcrm/utils/logging.py†L1-L13】
- Ошибки API возвращаются как JSON: `{"error": {"code": <int>, "message": "<string>"}}` для всех 4xx/5xx; для не-API маршрутов остаётся стандартное HTML-поведение. Ошибки логируются с путём и методом.【F:liftcrm/__init__.py†L35-L63】

## Лимитирование логина
- `/api/login` ограничен: 10 попыток за 10 минут на пару `(IP + username)`. Счётчик учитывает все попытки (успешные и неуспешные). При превышении возвращается `429` с JSON-ошибкой `{"error": {"code": "RATE_LIMITED", "message": "Too many login attempts. Try again later."}}` и заголовком `Retry-After`.【F:liftcrm/auth/routes.py†L21-L59】
- Реализация in-memory: состояние хранится в памяти процесса и сбрасывается при перезапуске, а также не разделяется между воркерами/инстансами.【F:liftcrm/utils/rate_limit.py†L1-L34】
- По умолчанию заголовки прокси не доверяются. Если приложение развёрнуто **только** за доверенным reverse-proxy (Nginx/Cloudflare) и недоступно напрямую, включите `TRUST_PROXY_HEADERS=true` (и при необходимости `PROXY_FIX_X_FOR=1`), чтобы `ProxyFix` корректно использовал `X-Forwarded-For`. Иначе оставляйте выключенным, чтобы предотвратить подмену IP.【F:liftcrm/config.py†L7-L20】【F:liftcrm/__init__.py†L23-L38】

## После рефакторинга: что куда переехало
- Вход: `app.py` вызывает `liftcrm.create_app()`.【F:app.py†L1-L5】
- Конфиги путей: `liftcrm/config.py` (архив, uploads, objects).【F:liftcrm/config.py†L1-L4】
- БД и модели: `liftcrm/db.py` (Master/User/Ticket/Attachment/Asset).【F:liftcrm/db.py†L1-L122】
- Роуты: `liftcrm/auth/routes.py`, `liftcrm/tickets/routes.py`, `liftcrm/assets/routes.py`, `liftcrm/objects/routes.py`.【F:liftcrm/auth/routes.py†L1-L35】【F:liftcrm/tickets/routes.py†L1-L424】【F:liftcrm/assets/routes.py†L1-L176】【F:liftcrm/objects/routes.py†L1-L21】
- Логика тикетов: `liftcrm/tickets/service.py` (назначение, геозона, архив, email).【F:liftcrm/tickets/service.py†L1-L103】
- Утилиты: `liftcrm/utils/security.py`, `liftcrm/utils/time.py`, `liftcrm/utils/health.py`.【F:liftcrm/utils/security.py†L1-L14】【F:liftcrm/utils/time.py†L1-L5】【F:liftcrm/utils/health.py†L1-L6】

## Чек-лист валидации поведения (без изменений)
1. `python -m pip install -r requirements.txt` — зависимости ставятся без ошибок.
2. `python app.py` — сервер стартует, открывается `/` с формой логина.
3. Логин admin/admin123 успешен, `GET /api/me` возвращает role=admin.
4. Создание заявки через форму с выбранным приоритетом → запись появляется в таблице/канбане (`GET /api/tickets`).
5. Переключение приоритета через выпадающий список в таблице обновляет бейдж в таблице/канбане/мастерском UI.
6. Назначение мастера вручную (`POST /api/tickets/{id}/assign/{mid}`) — мастер обновлён.
7. Метрики (`GET /api/metrics`) отвечают корректно под admin/dispatcher; блок «Итоги» показывает распределение по приоритетам.
8. Скачивание архива (`GET /api/archive`) отдаёт `archive.xlsx` с колонкой priority.
9. Вкладка «Объекты» грузит точки из SQL-реестра (`GET /api/assets`), `/api/objects` остаётся алиасом.
10. SLA отображается: создание тикета, ожидание > SLA (или ручная правка времени) → флаги «overdue» в таблице/канбане/дашборде и рост счётчиков в `/api/metrics`.

### Важно: не менять правила автоназначения/перераспределения без решения продукта
Текущее поведение фиксировано: активные мастера, минимальная нагрузка (`NEW/ASSIGNED/IN_PROGRESS`), перераспределение при деактивации/удалении. Любые изменения требуют отдельного продуктового решения.
