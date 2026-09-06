# Lift CRM: рабочее CRM-ядро и обновление интерфейса

## Purpose / Scope

Поручение 2026-09-05: изучить существующую CRM, закончить незавершённое, улучшить dashboard, вход и мобильное приложение. Этот ExecPlan уточняет выполнение Sprint 2–5 из `PLANS.md`; прежние требования отдельного разрешения спринтов заменены текущим прямым поручением. Сохранить Flask/SQLite, роли admin/dispatcher/technician, существующие API, историю и файлы. Финансы, склад, внешние интеграции и публикация не входят.

## Progress

- [x] (2026-09-05 15:15 +0500) Прочитаны AGENTS.md и весь PLANS.md, изучены маршруты, модели, UI, PWA и тесты. Рабочее дерево чистое. Baseline: 161 passed, 6 subtests passed.
- [x] (2026-09-05 15:18 +0500) M1: объектная модель, безопасная миграция, API объектов и связи заявок/лифтов.
- [x] (2026-09-05 15:23 +0500) M2: сводки лифтов, история для мастера, отчёты и общий поиск с проверкой доступа.
- [x] (2026-09-05 16:05 +0500) M3: единый локальный стиль, вход, dashboard, компактные заявки, объекты и карточки.
- [x] (2026-09-05 21:03 +0500) M4: мобильный интерфейс, изоляция кеша пользователей, перезапуск offline, очередь и восстановление связи.
- [x] (2026-09-06 00:45 +0500) M5: полные тесты, браузерные сценарии desktop/mobile/offline, проверка существующей БД, документация и локальный запуск.

## Surprises & Discoveries

- База тестов зелёная, но UI заявок содержит 16 колонок с координатами и редактированием SLA в каждой строке. Это затрудняет обычную работу.
- Нет Building; Info в карточке лифта является заглушкой. Sprint 2–5 из PLANS.md ещё не реализованы.
- Tailwind загружается из CDN. Service worker зарегистрирован под /static/ и не управляет /mobile; HTML мобильной оболочки не доступен при offline reload.
- IndexedDB использует общий DB_NAME для всех пользователей, поэтому надо изолировать данные, не переносить чужую очередь в новый аккаунт.
- В браузерной проверке остановка тестового сервера оставила форму лифта на «Сохраняю…»; добавлена обработка сетевой ошибки с сохранением полей и блокировка повторного клика. Удаление ошибочного offline-действия должно восстанавливать серверное состояние, иначе локальный статус остаётся ложным.

## Decision Log

- 2026-09-05: завершать CRM-ядро на текущей архитектуре; изменения бизнес-моделей добавочные. Перед проверкой на существующей БД создать SQLite backup; браузерные записи сначала выполнять в отдельной демонстрационной БД.
- 2026-09-05: Building группируется по нормализованному адресу и customer/contract. Snapshot адресов заявок сохраняется. /api/objects остаётся совместимым alias для карты.
- 2026-09-05: единый визуальный язык: светлая рабочая область, тёмная боковая навигация, зелёный акцент, крупные operational counters; никаких выдуманных KPI. Все показатели из API.
- 2026-09-05: offline reload обслуживается публичной оболочкой без пользовательских данных; авторизованный HTML/API не кешируется service worker. Локальные данные изолированы по user id, повторная проверка личности перед синхронизацией обязательна.
- 2026-09-05: удаление ошибочного события доступно online после чтения сервера; с подтверждением удаляется его цепочка зависимых версий, фото остаются. `app.py` запускать по умолчанию на loopback без debugger; HOST/PORT/DEBUG задаются явно для нужного окружения.

## Milestones / Implementation

M1: В `liftcrm/db.py` добавить Building, nullable building_id в Asset/Ticket и идемпотентный backfill. Создать `liftcrm/buildings/service.py` и `routes.py`: list/create/update/summary с role_required admin/dispatcher, валидацией координат и связей. Связать create/update/import assets, create ticket и generate-ticket для ТО. `serialize_ticket` и `serialize_asset` добавить объектный контекст. Проверить повторную миграцию, наследование связей, summary, отказ чужим ролям и старые тесты assets/tickets.

M2: `liftcrm/reports/routes.py` и сервис сводок: dashboard, отчёт по мастерам, типам, повторным заявкам по лифтам/объектам и SLA/stale с диапазоном дат. Проблемность = не менее 3 неотменённых заявок за 30 дней или 2 HIGH/EMERGENCY. `GET /api/lifts/<id>/summary` и ограниченная `GET /api/me/lifts/<id>/history`. `GET /api/search` возвращает тип, подпись и безопасную внутреннюю ссылку; technician только свои заявки и связанные лифты, без клиентов/договоров. Проверить фиксированными fixture counts, сроки, RBAC и ошибки ввода.

M3: Сохранить существующие DOM hooks и рабочие разделы `templates/index.html`. Добавить dashboard, отдельный список объектов и отчёты; компактный список заявок, карточки и прямые ссылки. `static/crm.css`, локально собранный Tailwind CSS и локальный Leaflet исключают CDN как условие работоспособности. `templates/login.html`: адаптивная двухколоночная форма, понятные ошибки, показать пароль, автозаполнение. Страницы building и lift показывают реальный контекст. Проверить в браузере создание объекта → лифта → заявки → комментария, поиск и отчёты, отсутствие горизонтального overflow.

M4: `templates/mobile.html`, `static/mobile.js`, `static/sw.js`, route `/sw.js` и публичная `/mobile-shell`: список с поиском и фильтрами, ясная следующая операция, детали и история лифта, настройки отдельно, русские подписи. Кеш по user id, запрет отправки чужой очереди, single-flight sync. Backend events → UI → offline shell/storage → browser validation. Принять заявку offline, перезагрузить, восстановить сеть, проверить применение ровно один раз; сохранить геозону 500 м и version conflicts.

M5: `venv/bin/python -m pytest -q`, syntax checks JS, `git diff --check`. В браузере dispatcher/admin/technician, desktop 1440px и mobile 390px; screenshots в `output/playwright/`. Обновить README, docs/RUNBOOK.md и docs/ARCHITECTURE.md, записать точные результаты. Запустить приложение для пользователя на localhost без демонстрационных записей в основной базе.

## Validation / Reproduction

1. Установить requirements, запустить `python app.py`, войти администратором или диспетчером.
2. Открыть Объекты, создать объект с адресом/координатами, добавить лифт к объекту, создать заявку выбором лифта. Проверить связи в карточках и общий поиск.
3. Добавить комментарий, назначить мастера, открыть Отчёты и изменить период. Проверить реальные значения и ссылки на заявки.
4. Войти мастером, открыть /mobile, выбрать заявку. После первого онлайн открытия переключить браузер offline, принять заявку, перезагрузить страницу. Включить сеть, синхронизировать, проверить состояние на сервере и пустую очередь.
5. Проверить другую учётную запись: прежние данные не отображаются и очередь не отправляется от другого пользователя.

## Outcomes & Retrospective

Baseline: 161 passed, 6 subtests passed за 23.77 s. Дальнейшие результаты записывать после каждого milestone. Публикация/HTTPS на сервере заказчика и реальные проверки GPS на телефоне требуют соответствующего окружения; локальная проверка не подменяет их.

M1 outcome: 36 passed, 6 subtests passed (new object CRUD/snapshot/coordinate/migration tests plus existing assets, DB init, filters, maintenance). Legacy DB without attachments exposed missing-table index assumption; index creation now checks table existence. Closed-ticket SLA now freezes at cancellation instead of growing forever.

M2 outcome: 16 passed (CRM reports, search scopes, mobile lift history, legacy metrics/history). Counts include archived history, exclude cancelled tickets from repeated-fault ranking, and define reporting dates in Asia/Almaty. Mobile history requires an active assigned ticket.

M3/M4 progress (2026-09-05): новый desktop/login осмотрен при 1440x960, screenshot сохранён. 23 focused UI/auth tests passed. Full suite выявил привязку Building к перезагруженному ORM mapper в тестах миграции; link_asset теперь использует mapper фактического Asset. Недостающие Leaflet images добавлены локально. Mobile backend получил root-scope public shell и X-Mobile-User guard, UI и outbox isolation реализованы; offline browser scenario ещё выполняется.

Additional M4 decision (2026-09-05): upload_file used second-resolution filenames, so photos with the same name could overwrite each other. Add random filenames plus optional Attachment.upload_key with a unique index, send the mobile photo UUID, return the existing attachment on retries. Validate collision avoidance and retry idempotence. This is an additive migration; legacy uploads keep their existing URLs.

M3 outcome: dispatcher browser login, dashboard, lift autocomplete -> ticket #25 creation, ticket comment persisted, building #5 created via form; screenshots login-desktop.png, dashboard-desktop.png, ticket-card.png. Desktop focused UI/RBAC/login checks: 23 passed. Additional core search/upload/migration checks: 25 passed.


M4 outcome: Chrome 390x844, `/sw.js` scope `/`, кеш v7. Offline принятие, reload, комментарий и фото сохранены; сервер: 1 комментарий, 1 фото, 6 уникальных событий после полного цикла. Повторный online reload не изменил version/counts. Для проверки потерянного online-события добавлен повтор подключения каждые 30 секунд в открытом приложении; offline WAITING -> reload -> online отправился автоматически, version 6, обе очереди пусты. Геолокация 43.24/76.92 смоделирована в браузере. Второй мастер получил только [2,12,7], чужая заявка ответила 403, чужой X-Mobile-User — 409. Проверка выявила сброс формы при sync; черновики полей теперь сохраняются при обновлении той же карточки, отправленный комментарий очищается. 14 focused tests passed; до последней UI-правки full suite: 170 passed, 6 subtests passed.

M5 progress: реальная БД скопирована в `backups/20260905-155528` через backup script и SQLite backup API. Двойная миграция: 7 пользователей, 5 мастеров, 2 заявки, остальные рабочие реестры пусты. Все прежние поля всех исходных записей сравнены и совпадают, integrity_check=ok. Старые заявки не имеют адреса для группировки, поэтому объекты не выдумывались. Результат проверки — `output/main-db-validation.json`. README/RUNBOOK/ARCHITECTURE переписаны по фактическому поведению.


M4 follow-up: завершение #2 проверено с задержкой ответа sync: EQUIPMENT_FAILURE и введённый итог сохранены, очередь пуста. При визуальном осмотре обнаружено, что обновление краткого списка перезаписывает подробный кеш комментариев; краткий ответ теперь объединяется с прежними деталями, а открытая карточка после sync читает актуальные детали сервера. Переключение раздела снимает выбранную заявку, чтобы фоновое обновление не открывало её поверх истории.


M5 outcome: последний полный запуск — 170 passed, 6 subtests passed (31.13s); локальная сборка CSS, node --check всех изменённых JS и git diff --check прошли. Browser: dispatcher создал объект #5, лифт #5, заявку #25 и комментарий; admin нашёл лифт CRM-CHECK-005 общим поиском, отчёт за 2026-09-05 вернул 5 заявок. Финальный mobile v7 при 390x844: комментарий #7 сохранён после offline reload, горизонтального overflow нет. На основной базе проверен вход admin, `/api/health` ok, `/api/dashboard` active=1; desktop 1440x960 без overflow и ошибок console. Приложение запущено на http://127.0.0.1:5000 без debugger. Скриншоты: login-desktop.png, dashboard-desktop.png (демо), reports-desktop.png, mobile-list.png, mobile-offline-reload.png, mobile-detail-final.png, dashboard-live.png в output/playwright/.

Ограничение приемки: реальные камера/GPS, установка на физический телефон и эксплуатация по внешнему HTTPS требуют целевого устройства/сервера. В этой работе проверены браузерная геолокация, responsive UI, offline/reload/sync и локальная база. Отдельная нативная сборка и внешнее развёртывание не выполнялись. CRM-ядро Sprint 2–5 завершено в согласованном объёме; исходные данные сохранены.


## PR #100 follow-up: search deep links and maintenance KPI

Progress: [x] (2026-09-06T23:59+05:00) исправлены оба P2, добавлены регрессии, проверки прошли; изменения подготовлены к отправке в PR #100.
Discovery: mobile init открывает только id из активного списка, хотя поиск возвращает также завершённые/архивные свои заявки. Dashboard исключает поддерживаемый статус ТО overdue.
Decision: валидный положительный целочисленный deep link передавать в openTicket; доступ проверяет GET /api/tickets/<id>, offline читает только персональный кеш. KPI считает active с наступившей датой и все явно overdue, исключает paused/completed.
Validation: regression API для состава ТО и scope поиска/доступа; выполнение mobile init с deep link вне активного списка; полный pytest и JS syntax. После проверки commit и push в PR #100.
Outcome: 172 passed, 6 subtests passed (27.97s); node --test tests/mobile_deep_link.test.cjs — 3 passed. Проверены закрытая/архивная заявка вне активного списка, offline personal cache, 403/404 без показа старого кеша, невалидные id; API проверяет владение. KPI regression: active вчера/сегодня, overdue вчера/будущее учитываются, active будущее и paused/completed исключаются. Node regression включён в GitHub Actions, mobile cache повышен до v8. Ошибка первой тестовой фикстуры (не заданы обязательные координаты) исправлена до полного успешного запуска.
