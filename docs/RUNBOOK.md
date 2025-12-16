# Runbook — Lift CRM

## Быстрый старт (локально)
1) Зависимости: `python -m pip install -r requirements.txt` (Python 3.11+).【F:requirements.txt†L1-L8】  
2) Запуск: `python app.py` (поднимает Flask dev-server на `http://127.0.0.1:5000`).【F:app.py†L773-L804】  
3) Аккаунты для входа:
   - admin / `admin123`
   - dispatcher / `disp123`
   - master1 … master10 / `m123456` (создаются при первом запуске).【F:app.py†L92-L118】

## Что создаётся автоматически
- База `lift_crm.db` (SQLite) и таблицы при первом запросе (hook `before_request`).【F:app.py†L124-L180】
- Каталог `uploads/` для файлов вложений и `objects/objects.{xlsx,json}` с примером объекта.【F:app.py†L124-L175】
- Файл `archive.xlsx` (пустой с заголовками) для скачивания архива заявок.【F:app.py†L170-L175】

## Типовой флоу проверки
1. Запустить сервер.  
2. Войти как admin.  
3. Создать заявку (форма на главной).  
4. Проверить автоназначение мастера и отображение в таблице/канбане.  
5. Скачать архив через кнопку «Скачать архив».  
6. Переключиться на masterN и отметить «Приехал» / «Завершить» (нужна геолокация в браузере).  
7. Открыть вкладку «Объекты» и убедиться, что точки отображаются с `objects.xlsx`.

## Частые ошибки и решения
- **`Missing dependency: openpyxl` при скачивании архива.**  
  Установите зависимости (`python -m pip install -r requirements.txt`) или используйте встроенный `vendor/openpyxl` (подхватывается автоматически).【F:app.py†L12-L21】【F:app.py†L667-L693】
- **`uploads` нет / ошибка сохранения файла.**  
  Каталог создаётся в `before_request`. Убедитесь, что процесс имеет права на запись в корень проекта или создайте `uploads/` вручную.【F:app.py†L124-L144】【F:app.py†L568-L616】
- **Блокировки SQLite / ошибки записи.**  
  Закройте другие процессы, удалите `lift_crm.db` для сброса (потеря данных), перезапустите сервер. SQLite не рассчитан на высокую конкуренцию.
- **Геолокация отклонена в браузере.**  
  Кнопки «Приехал/Завершить» требуют координаты; разрешите доступ или используйте ручную подстановку координат в DevTools.
- **Архив растёт (archive_N.xlsx).**  
  Удалите лишние `archive_*.xlsx` вручную; ротации нет.【F:app.py†L183-L259】

## Конфигурация и секреты
- Файл примера: `.env.example` содержит все поддерживаемые переменные окружения.
- Обязательные в проде (dev имеет дефолты):
  - `SECRET_KEY` — ключ сессий Flask (dev по умолчанию `dev-secret`, обязательно переопределить в проде).【F:liftcrm/config.py†L7-L18】【F:liftcrm/__init__.py†L12-L33】
  - `ADMIN_USERNAME` / `ADMIN_PASSWORD` — креды админа (dev: `admin` / `admin123`).【F:liftcrm/config.py†L7-L18】【F:liftcrm/db.py†L58-L73】
  - `DISPATCHER_USERNAME` / `DISPATCHER_PASSWORD` — креды диспетчера (dev: `dispatcher` / `disp123`).【F:liftcrm/config.py†L7-L18】【F:liftcrm/db.py†L58-L73】
  - `MASTER_PASSWORD` — пароль для всех мастеров при сидировании (dev: `m123456`).【F:liftcrm/config.py†L7-L18】【F:liftcrm/db.py†L58-L73】
- Опционально:
  - `SMTP_SERVER`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD` — для email-отправки отчёта при завершении; если пусто, отправка пропускается.【F:liftcrm/config.py†L20-L23】【F:liftcrm/tickets/service.py†L43-L77】
- Файлы и данные:
  - БД: `lift_crm.db` в корне.
  - Архив: `archive.xlsx` и копии `archive_N.xlsx` в корне.
  - Объекты: `objects/objects.xlsx|json`.
  - Вложения: `uploads/` в корне.

## Мониторинг/здоровье
- `/api/health` — простой health-check (без auth).【F:liftcrm/utils/health.py†L1-L6】

## Логирование и ошибки
- Логирование: консоль, формат `%(asctime)s %(levelname)s [%(name)s] %(message)s`, уровень по умолчанию INFO; можно переопределить `LOG_LEVEL`.【F:liftcrm/utils/logging.py†L1-L13】
- Ошибки API возвращаются как JSON: `{"error": {"code": <int>, "message": "<string>"}}` для всех 4xx/5xx; для не-API маршрутов остаётся стандартное HTML-поведение. Ошибки логируются с путём и методом.【F:liftcrm/__init__.py†L35-L63】

## После рефакторинга: что куда переехало
- Вход: `app.py` вызывает `liftcrm.create_app()`.【F:app.py†L1-L5】
- Конфиги путей: `liftcrm/config.py` (архив, uploads, objects).【F:liftcrm/config.py†L1-L4】
- БД и модели: `liftcrm/db.py` (Master/User/Ticket/Attachment).【F:liftcrm/db.py†L1-L96】
- Роуты: `liftcrm/auth/routes.py`, `liftcrm/tickets/routes.py`, `liftcrm/objects/routes.py`.【F:liftcrm/auth/routes.py†L1-L35】【F:liftcrm/tickets/routes.py†L1-L424】【F:liftcrm/objects/routes.py†L1-L48】
- Логика тикетов: `liftcrm/tickets/service.py` (назначение, геозона, архив, email).【F:liftcrm/tickets/service.py†L1-L103】
- Утилиты: `liftcrm/utils/security.py`, `liftcrm/utils/time.py`, `liftcrm/utils/health.py`.【F:liftcrm/utils/security.py†L1-L14】【F:liftcrm/utils/time.py†L1-L5】【F:liftcrm/utils/health.py†L1-L6】

## Чек-лист валидации поведения (без изменений)
1. `python -m pip install -r requirements.txt` — зависимости ставятся без ошибок.
2. `python app.py` — сервер стартует, открывается `/` с формой логина.
3. Логин admin/admin123 успешен, `GET /api/me` возвращает role=admin.
4. Создание заявки через форму → запись появляется в таблице/канбане (`GET /api/tickets`).
5. Назначение мастера вручную (`POST /api/tickets/{id}/assign/{mid}`) — мастер обновлён.
6. Метрики (`GET /api/metrics`) отвечают корректно под admin/dispatcher.
7. Скачивание архива (`GET /api/archive`) отдаёт `archive.xlsx`.
8. Вкладка «Объекты» грузит точки с `objects.xlsx` (`GET /api/objects`).

### Важно: не менять правила автоназначения/перераспределения без решения продукта
Текущее поведение фиксировано: активные мастера, минимальная нагрузка (`NEW/ASSIGNED/IN_PROGRESS`), перераспределение при деактивации/удалении. Любые изменения требуют отдельного продуктового решения.
