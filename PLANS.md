# CRM-ядро Lift CRM - ExecPlan

Этот `PLANS.md` является источником истины для работ по CRM-ядру. Во время реализации обязательно поддерживать актуальными разделы `Progress`, `Surprises & Discoveries`, `Decision Log` и `Outcomes & Retrospective`.

Читатель плана не обязан знать предыдущий контекст. Достаточно текущего рабочего дерева и этого файла.

Весь план сразу не реализовывать. Код приложения не менять, пока пользователь отдельно не разрешит реализацию Sprint 1.

## Цель

Довести текущий Lift CRM до практичного CRM-ядра для одной лифтовой сервисной компании:

- быстрый учет заявок диспетчером;
- контроль заявок и базовая фильтрация;
- отдельные объекты/здания;
- лифты как оборудование внутри объекта;
- история по лифтам;
- история по объектам;
- отчетность по мастерам;
- отчетность по типам поломок;
- проблемные лифты;
- проблемные объекты;
- удобный интерфейс для диспетчера, мастера и администратора.

Это план только для CRM-ядра. ERP-модули в него не входят.

## Ограничения

Не делать и не добавлять в рамках этого плана:

- склад;
- складские остатки;
- запчасти;
- списание запчастей в заявках;
- зарплаты;
- счета;
- платежи;
- закупки;
- финансовую часть;
- multi-company;
- SaaS;
- сложный RBAC;
- роли/permissions на уровне отдельных действий;
- телефонию, SMS, push, BI, Docker, Postgres или deployment-работы без отдельного запроса.

Сохранить текущую простую модель ролей:

- `admin`;
- `dispatcher`;
- `technician`.

Сохранить текущую архитектуру Flask + SQLAlchemy + SQLite. Новые таблицы, колонки и индексы добавлять только через безопасные идемпотентные SQLite-миграции в стиле текущего проекта.

## Текущие факты по проекту

- Вход в приложение: [app.py](/Users/dmitriy/Projects/ERP_lift_company/app.py).
- Фабрика приложения и page routes: [liftcrm/__init__.py](/Users/dmitriy/Projects/ERP_lift_company/liftcrm/__init__.py).
- Модели и ручные SQLite-миграции: [liftcrm/db.py](/Users/dmitriy/Projects/ERP_lift_company/liftcrm/db.py).
- API заявок: [liftcrm/tickets/routes.py](/Users/dmitriy/Projects/ERP_lift_company/liftcrm/tickets/routes.py).
- Сериализация заявок и SLA: [liftcrm/tickets/repository.py](/Users/dmitriy/Projects/ERP_lift_company/liftcrm/tickets/repository.py).
- API лифтов, клиентов, договоров и ТО: [liftcrm/assets/routes.py](/Users/dmitriy/Projects/ERP_lift_company/liftcrm/assets/routes.py).
- Старый alias объектов: [liftcrm/objects/routes.py](/Users/dmitriy/Projects/ERP_lift_company/liftcrm/objects/routes.py).
- Desktop UI почти полностью находится в [templates/index.html](/Users/dmitriy/Projects/ERP_lift_company/templates/index.html).
- Мобильный интерфейс мастера: [templates/mobile.html](/Users/dmitriy/Projects/ERP_lift_company/templates/mobile.html) и [static/mobile.js](/Users/dmitriy/Projects/ERP_lift_company/static/mobile.js).
- Карточка и история лифта: [templates/lift_detail.html](/Users/dmitriy/Projects/ERP_lift_company/templates/lift_detail.html) и [static/lift_detail.js](/Users/dmitriy/Projects/ERP_lift_company/static/lift_detail.js).
- В тестах уже есть покрытие заявок, лифтов, истории лифта, истории мастера, sync, metrics, access, XSS guards и ТО.

Текущая цепочка данных:

`Asset` как лифт + адрес объекта -> `Ticket` -> `AuditLog` / `TicketComment` / `Attachment`.

Целевая цепочка CRM-ядра:

`Building/Object` -> `Asset` как лифт -> `Ticket` -> история, комментарии, вложения, отчеты.

## Progress

- [x] (2026-06-17 17:00 +0500) Прочитан `CRM_AUDIT_REPORT.md`.
- [x] (2026-06-17 17:00 +0500) Изучены структура проекта, модели, API заявок, API лифтов, metrics API, desktop UI, mobile UI и существующие тесты.
- [x] (2026-06-17 17:00 +0500) Старый исторический `PLANS.md` заменен актуальным ExecPlan для CRM-ядра.
- [ ] Sprint 1 разрешен пользователем.
- [ ] Sprint 1 реализован и проверен.
- [ ] Sprint 2 разрешен пользователем.
- [ ] Sprint 2 реализован и проверен.
- [ ] Sprint 3 разрешен пользователем.
- [ ] Sprint 3 реализован и проверен.
- [ ] Sprint 4 разрешен пользователем.
- [ ] Sprint 4 реализован и проверен.
- [ ] Sprint 5 разрешен пользователем.
- [ ] Sprint 5 реализован и проверен.

## Surprises & Discoveries

- Наблюдение: прежний `PLANS.md` содержал несколько старых завершенных ExecPlan-блоков по ТО, клиентам/договорам и другим работам. Он не был компактным источником истины для нового CRM-core плана.
  Evidence: файл начинался с "Technician Mobile App", затем шел набор завершенных планов.
- Наблюдение: `/api/metrics` возвращает по мастерам `name`, `total`, `avg_close_sec`, `median_close_sec`, а desktop UI читает `master_name`, `count`, `avg_sec`, `median_sec`.
  Evidence: endpoint `/api/metrics` в [liftcrm/tickets/routes.py](/Users/dmitriy/Projects/ERP_lift_company/liftcrm/tickets/routes.py) и `loadMetrics()` в [templates/index.html](/Users/dmitriy/Projects/ERP_lift_company/templates/index.html).
- Наблюдение: `TicketComment` уже есть, mobile sync умеет добавлять комментарии, но desktop-карточка заявки не имеет поля для комментария диспетчера.
  Evidence: `TICKET_ADD_COMMENT` в [static/mobile.js](/Users/dmitriy/Projects/ERP_lift_company/static/mobile.js) и `openTicketModal()` в [templates/index.html](/Users/dmitriy/Projects/ERP_lift_company/templates/index.html).
- Наблюдение: отдельной модели `Building` или `Object` нет. `Asset` сейчас одновременно хранит лифт и адресный контекст объекта.
  Evidence: модель `Asset` в [liftcrm/db.py](/Users/dmitriy/Projects/ERP_lift_company/liftcrm/db.py).
- Наблюдение: `/api/lifts/<asset_id>/history` есть для admin/dispatcher, но мобильный интерфейс мастера пока не показывает историю лифта в потоке работы по заявке.
  Evidence: route истории лифта в [liftcrm/assets/routes.py](/Users/dmitriy/Projects/ERP_lift_company/liftcrm/assets/routes.py) и mobile UI в [static/mobile.js](/Users/dmitriy/Projects/ERP_lift_company/static/mobile.js).

## Decision Log

- Решение: план ограничен CRM-ядром и явно исключает склад, финансы, запчасти, зарплаты, закупки, SaaS и сложный RBAC.
  Обоснование: пользователь прямо задал эти ограничения.
  Дата/Автор: 2026-06-17 / codex
- Решение: Sprint 1 должен быть быстрым и низкорисковым перед добавлением объектной модели.
  Обоснование: сначала нужно закрыть известный дефект отчетности, комментарии диспетчера и перегруженность создания заявки без большой миграции данных.
  Дата/Автор: 2026-06-17 / codex
- Решение: backend-модель объекта назвать `Building`.
  Обоснование: `Object` неоднозначен в коде, а в UI можно продолжать использовать бизнес-термин "Объект".
  Дата/Автор: 2026-06-17 / codex
- Решение: оставить backend-модель `Asset` для лифтов на время этой roadmap.
  Обоснование: переименование `Asset` в `Elevator` даст большой шум в коде; достаточно добавить `building_id` и последовательно называть `Asset` лифтом в UI.
  Дата/Автор: 2026-06-17 / codex
- Решение: признак проблемного лифта/объекта сначала делать как вычисляемый показатель.
  Обоснование: повторные заявки по лифту/объекту и `problem_type` достаточно покрывают управленческий контроль без нового ручного workflow.
  Дата/Автор: 2026-06-17 / codex

## Outcomes & Retrospective

- Outcome (2026-06-17): создан этот ExecPlan по CRM-ядру на основе аудита и текущего кода.
- Outcome (2026-06-17): код приложения не изменялся.
- Retrospective: заполнять после каждого спринта результатами, командами проверки и оставшимися рисками.

## Общие критерии приемки

Roadmap CRM-ядра считается завершенной только когда:

- диспетчер может быстро создать заявку через поиск лифта/объекта без технических полей на первом экране;
- dispatcher/admin могут контролировать активные заявки через базовые фильтры и компактный список;
- каждый лифт может быть связан с отдельным объектом;
- заявка может быть связана и с лифтом, и с объектом;
- старые данные по лифтам и заявкам мигрируются в объектную модель идемпотентно;
- карточка объекта показывает лифты, активные заявки, последние заявки, клиента/договор и заметки;
- карточка лифта показывает активные заявки, последние заявки, историю и признак проблемности;
- мастер в mobile UI видит полезную историю лифта по текущей заявке;
- отчеты показывают мастеров, типы поломок, проблемные лифты, проблемные объекты, SLA и зависшие заявки;
- видимые пользователю labels приведены к русскому языку;
- тесты покрывают миграции, API, права доступа, сериализацию, фильтры, отчеты и основные XSS-риски UI;
- не появились склад, финансы, запчасти, зарплаты, закупки, SaaS или сложный RBAC.

## Этапы

### Sprint 1 - быстрые улучшения

Цель: исправить известные операционные проблемы и ускорить работу диспетчера без изменения объектной модели.

#### Задачи

1. Исправить отчетность по мастерам.
   - В `templates/index.html` обновить `loadMetrics()` так, чтобы UI использовал текущие поля `/api/metrics`: `name`, `total`, `avg_close_sec`, `median_close_sec`.
   - Backend response не менять без необходимости.
   - Сделать пустые состояния понятными.

2. Добавить desktop-комментарии в заявку.
   - Добавить endpoint для admin/dispatcher, например `POST /api/tickets/<id>/comments`.
   - Использовать существующую модель `TicketComment`.
   - Показывать комментарии в карточке заявки или через `GET /api/tickets/<id>`.
   - Добавить поле комментария в desktop-карточку заявки в `templates/index.html`.
   - Логировать создание комментария через `log_audit()`.

3. Упростить создание заявки.
   - Сделать поиск лифта основным сценарием.
   - При выборе лифта автоматически заполнять объект/адрес/координаты.
   - Координаты, ручной адрес и вспомогательные поля оставить только в "Дополнительно".
   - Сохранить совместимость текущего `POST /api/tickets`.
   - Показывать понятную ошибку, если лифт не выбран и координат нет.

4. Скрыть advanced-поля.
   - Перенести кастомные SLA, raw coordinates, optional email и технические helper-кнопки в свернутый advanced-блок.
   - Перевести видимые English labels и helper-тексты на русский.
   - Не удалять поля из API и не ломать существующие тесты.

5. Добавить базовые фильтры заявок.
   - Расширить `/api/tickets` фильтрами `status`, `q`, `date_from`, `date_to`, `asset_id`.
   - Сохранить текущие фильтры `master_id`, `priority`, `overdue`, `unassigned`.
   - В desktop UI добавить статус, период, поиск, мастер, приоритет, SLA overdue и "без мастера".
   - Не нарушить scoped-доступ мастера: technician видит только свои заявки.

6. Добавить `problem_type` в заявку.
   - Добавить nullable `Ticket.problem_type` и идемпотентную миграцию.
   - Ввести MVP-значения: `DOORS`, `NOISE`, `STOPPED`, `POWER`, `BUTTONS`, `CABIN`, `OTHER`.
   - Принимать `problem_type` в create/update API и сериализовать его.
   - Добавить select в форму создания и карточку заявки.
   - Оставить свободный `description` для деталей.

#### Критерии приемки

- Таблица "Топ мастеров" показывает реальные имена мастеров, количество заявок, среднее и медианное время закрытия.
- Диспетчер может добавить комментарий из desktop-карточки заявки и увидеть его после повторного открытия.
- Заявка по выбранному лифту создается без ручного ввода координат.
- Advanced-поля скрыты по умолчанию, но доступны при раскрытии.
- Фильтры заявок работают совместно и не ломают доступ мастера.
- `problem_type` сохраняется, сериализуется и отображается в UI.
- Mobile sync комментариев продолжает работать.

#### Какие файлы примерно будут затронуты

- [liftcrm/db.py](/Users/dmitriy/Projects/ERP_lift_company/liftcrm/db.py)
- [liftcrm/tickets/routes.py](/Users/dmitriy/Projects/ERP_lift_company/liftcrm/tickets/routes.py)
- [liftcrm/tickets/repository.py](/Users/dmitriy/Projects/ERP_lift_company/liftcrm/tickets/repository.py)
- [liftcrm/tickets/service.py](/Users/dmitriy/Projects/ERP_lift_company/liftcrm/tickets/service.py)
- [templates/index.html](/Users/dmitriy/Projects/ERP_lift_company/templates/index.html)
- [static/mobile.js](/Users/dmitriy/Projects/ERP_lift_company/static/mobile.js), только если новая сериализация требует mobile/cache-адаптации
- [tests/test_metrics_api.py](/Users/dmitriy/Projects/ERP_lift_company/tests/test_metrics_api.py)
- [tests/test_ticket_filters.py](/Users/dmitriy/Projects/ERP_lift_company/tests/test_ticket_filters.py)
- [tests/test_audit_log.py](/Users/dmitriy/Projects/ERP_lift_company/tests/test_audit_log.py)

#### Какие тесты добавить или обновить

- Тест/guard на соответствие schema `/api/metrics` и UI-ожиданий по мастерам.
- API-тесты desktop-комментариев: admin, dispatcher, technician, anonymous, archived ticket, empty body, audit log.
- Тесты создания заявки по выбранному лифту с автозаполнением адреса/координат.
- Тесты фильтров заявок: status, q, date range, asset, priority, master, SLA overdue, unassigned, technician scope.
- Миграция и create/update/serialize тесты для `problem_type`.
- XSS rendering guard для новых мест вывода комментариев и problem labels.

### Sprint 2 - объектная модель

Цель: добавить реальный слой объекта/здания и связать его с лифтами и заявками без поломки текущей истории.

#### Задачи

1. Добавить `Building/Object`.
   - Добавить модель `Building` в `liftcrm/db.py`.
   - Базовые поля: `id`, `name`, `address`, `address_norm`, `lat`, `lon`, `customer_id`, `contract_id`, `contact_person`, `phone`, `email`, `notes`, `is_active`, `created_at`, `updated_at`.
   - Добавить индексы на `address_norm`, `customer_id`, `contract_id` и поисковые поля.
   - Сделать миграцию идемпотентной.

2. Связать объект с лифтами.
   - Добавить nullable `assets.building_id`.
   - Сериализовать `building_id`, `building_name`, object address/context в asset payload.
   - Обновить create/update/import лифтов, чтобы лифт можно было привязать к объекту.
   - Оставить текущие адресные поля `Asset` как denormalized/historical display fields.

3. Связать заявки с объектом.
   - Добавить nullable `tickets.building_id`.
   - При создании заявки с выбранным лифтом брать `building_id` из лифта.
   - При создании заявки без лифта разрешить выбор или создание объекта по адресу.
   - Оставить `Ticket.object_name` и `Ticket.address` как snapshot на момент заявки.

4. Сделать миграцию старых данных.
   - Создать объекты из существующих active assets, группируя по нормализованному адресу и customer/contract, если они есть.
   - Заполнить `assets.building_id`.
   - Заполнить `tickets.building_id` через `tickets.asset_id -> assets.building_id`.
   - Для заявок без лифта можно группировать по нормализованному адресу, не перезаписывая snapshot-поля.
   - Повторный запуск миграции не должен создавать дубликаты объектов.

5. Создать карточку объекта.
   - Добавить endpoints вроде `GET /api/buildings`, `POST /api/buildings`, `PATCH /api/buildings/<id>`, `GET /api/buildings/<id>/summary`.
   - Добавить страницу `/objects/<id>` или `/buildings/<id>`.
   - Карточка объекта должна показывать адрес, клиента/договор, контакты, список лифтов, активные заявки, последние заявки, заметки и карту.
   - Решить, оставить ли deprecated `/api/objects` как временный compatibility alias.

#### Критерии приемки

- Существующие лифты получают `building_id` после миграции.
- Существующие заявки с `asset_id` получают соответствующий `building_id`.
- Повторный запуск миграции не создает дубликаты объектов.
- Admin/dispatcher могут создать и обновить объект.
- Admin/dispatcher могут открыть карточку объекта и увидеть лифты, активные заявки, последние заявки, клиента/договор.
- `/api/assets`, `/api/tickets`, `/lifts/<id>` и mobile ticket flow продолжают работать.

#### Какие файлы примерно будут затронуты

- [liftcrm/db.py](/Users/dmitriy/Projects/ERP_lift_company/liftcrm/db.py)
- [liftcrm/assets/routes.py](/Users/dmitriy/Projects/ERP_lift_company/liftcrm/assets/routes.py)
- [liftcrm/objects/routes.py](/Users/dmitriy/Projects/ERP_lift_company/liftcrm/objects/routes.py)
- [liftcrm/__init__.py](/Users/dmitriy/Projects/ERP_lift_company/liftcrm/__init__.py)
- [liftcrm/tickets/routes.py](/Users/dmitriy/Projects/ERP_lift_company/liftcrm/tickets/routes.py)
- [liftcrm/tickets/repository.py](/Users/dmitriy/Projects/ERP_lift_company/liftcrm/tickets/repository.py)
- [templates/index.html](/Users/dmitriy/Projects/ERP_lift_company/templates/index.html)
- новый `templates/object_detail.html` или аналог
- новый `static/object_detail.js` или аналог
- [tests/test_assets_api.py](/Users/dmitriy/Projects/ERP_lift_company/tests/test_assets_api.py)
- [tests/test_ticket_filters.py](/Users/dmitriy/Projects/ERP_lift_company/tests/test_ticket_filters.py)
- новые тесты object/building API и миграции

#### Какие тесты добавить или обновить

- Тесты миграции таблицы `buildings` и идемпотентности.
- Тесты create/update/import лифта с `building_id`.
- Тесты обратной совместимости asset serialization.
- Тесты создания заявки с наследованием `building_id` из лифта.
- Тесты миграции старых assets/tickets.
- Тесты object summary API: active tickets, latest tickets, lift list.
- RBAC-тесты для admin/dispatcher/technician/anonymous.

### Sprint 3 - карточки и история

Цель: сделать карточки заявки, лифта и историю в mobile полезными для ежедневной работы.

#### Задачи

1. Улучшить карточку заявки.
   - Перевести desktop modal в более понятную карточку/drawer.
   - Показывать статус, приоритет, `problem_type`, объект, лифт, клиента, договор, контакт заявителя при наличии, описание, мастера, SLA, комментарии, вложения и audit timeline.
   - Показывать связанные активные заявки по тому же лифту/объекту для предупреждения дублей.
   - Оставить действия role-safe: назначить, изменить problem/priority/description, добавить комментарий, отменить, архивировать.

2. Улучшить карточку лифта.
   - Заполнить почти пустую info-вкладку `/lifts/<id>`.
   - Показывать объект, клиента, договор, адрес, подъезд, метку, серийный номер, статус, заметки и текущий контекст ТО, если он уже есть.
   - Добавить активные заявки и последние заявки перед полной историей.

3. Добавить активные заявки и последние заявки в карточку лифта.
   - Активные статусы: `NEW`, `ASSIGNED`, `ACCEPTED`, `IN_PROGRESS`, `WAITING`.
   - Последние заявки: завершенные/отмененные с `problem_type` и close reason.
   - Показывать SLA badges и мастера.

4. Добавить историю лифта в мобильный интерфейс мастера.
   - В detail текущей заявки показать последние события/заявки по этому лифту.
   - Добавить technician-safe endpoint: мастер видит историю лифта только если у него есть назначенная заявка по этому лифту.
   - Если возможно без расширения offline outbox, кешировать историю для чтения offline.

5. Добавить признак "проблемный лифт".
   - Определить MVP-правило: например, 3+ неотмененные заявки за 30 дней или 2+ high/emergency заявки за 30 дней.
   - Показывать признак в карточке лифта и карточке заявки.
   - Не добавлять запчасти, склад или финансы.

#### Критерии приемки

- Диспетчер в карточке заявки видит полный контекст и может добавить комментарий.
- Карточка лифта сразу показывает активные заявки и последние заявки, а не пустую info-вкладку.
- Мастер в mobile видит историю лифта по текущей заявке.
- Признак проблемного лифта вычисляется детерминированно и покрыт тестами.
- Существующие тесты истории лифта продолжают проходить.

#### Какие файлы примерно будут затронуты

- [liftcrm/assets/routes.py](/Users/dmitriy/Projects/ERP_lift_company/liftcrm/assets/routes.py)
- [liftcrm/tickets/routes.py](/Users/dmitriy/Projects/ERP_lift_company/liftcrm/tickets/routes.py)
- [liftcrm/tickets/repository.py](/Users/dmitriy/Projects/ERP_lift_company/liftcrm/tickets/repository.py)
- [templates/index.html](/Users/dmitriy/Projects/ERP_lift_company/templates/index.html)
- [templates/lift_detail.html](/Users/dmitriy/Projects/ERP_lift_company/templates/lift_detail.html)
- [templates/mobile.html](/Users/dmitriy/Projects/ERP_lift_company/templates/mobile.html)
- [static/lift_detail.js](/Users/dmitriy/Projects/ERP_lift_company/static/lift_detail.js)
- [static/mobile.js](/Users/dmitriy/Projects/ERP_lift_company/static/mobile.js)
- [tests/test_lift_history.py](/Users/dmitriy/Projects/ERP_lift_company/tests/test_lift_history.py)
- [tests/test_technician_history.py](/Users/dmitriy/Projects/ERP_lift_company/tests/test_technician_history.py)
- [tests/test_xss_rendering_guards.py](/Users/dmitriy/Projects/ERP_lift_company/tests/test_xss_rendering_guards.py)

#### Какие тесты добавить или обновить

- Тесты ticket card payload: comments, related tickets, object/lift context, problem type.
- Тесты lift summary: active tickets, latest tickets, problem signal, RBAC.
- Тесты technician lift history scope: свой лифт разрешен, чужой запрещен.
- Mobile rendering/XSS guard для истории и комментариев.

### Sprint 4 - отчеты

Цель: добавить практичные CRM-отчеты для операционного контроля, не затрагивая финансы.

#### Задачи

1. Отчет по мастерам.
   - Добавить или усилить endpoint вроде `/api/reports/masters`.
   - Поля: всего назначено, активный backlog, выполнено, отменено, среднее время реакции, среднее время завершения, SLA breaches, mix `problem_type`.
   - Поддержать фильтр периода.

2. Отчет по типам поломок.
   - Использовать `Ticket.problem_type`.
   - Показать counts by type, priority, status, SLA breach, average completion time.
   - Не парсить свободный текст `description` как источник аналитики.

3. Отчет по проблемным лифтам.
   - Ранжировать лифты по повторным неотмененным заявкам за окно, по умолчанию 30 дней.
   - Показывать активные заявки, дату последней заявки, top problem types, SLA breaches, объект и клиента.

4. Отчет по проблемным объектам.
   - Агрегировать проблемы по `building_id`.
   - Показывать количество лифтов, количество заявок, активные заявки, повторные problem types, SLA breaches и последнюю активность.

5. Отчет по SLA и зависшим заявкам.
   - Показать заявки с просроченным response/completion SLA.
   - Показать stale tickets: NEW без мастера, ASSIGNED долго не принята, WAITING слишком долго, IN_PROGRESS слишком долго.
   - Включить мастера, объект, лифт, приоритет, `problem_type`, created/updated timestamps.

6. UI отчетов.
   - Держать отчеты в понятном разделе `Отчеты`.
   - Добавить фильтр периода и, где полезно, фильтры объект/лифт/мастер.
   - Не делать PDF/Excel report builder в этом спринте.

#### Критерии приемки

- Admin/dispatcher открывают отчеты и фильтруют их по периоду.
- Отчет по мастерам совпадает с тестовыми fixture-данными.
- Отчет по типам поломок использует `problem_type`.
- Проблемные лифты и объекты ранжируются по детерминированному правилу.
- SLA/stuck отчет показывает просроченные и зависшие заявки с прямым переходом к заявке/лифту/объекту.
- Technician не имеет доступа к отчетам admin/dispatcher.

#### Какие файлы примерно будут затронуты

- новый `liftcrm/reports/routes.py` или additions в [liftcrm/tickets/routes.py](/Users/dmitriy/Projects/ERP_lift_company/liftcrm/tickets/routes.py)
- [liftcrm/__init__.py](/Users/dmitriy/Projects/ERP_lift_company/liftcrm/__init__.py)
- [liftcrm/tickets/repository.py](/Users/dmitriy/Projects/ERP_lift_company/liftcrm/tickets/repository.py)
- [liftcrm/assets/routes.py](/Users/dmitriy/Projects/ERP_lift_company/liftcrm/assets/routes.py)
- [templates/index.html](/Users/dmitriy/Projects/ERP_lift_company/templates/index.html)
- новый report helper module, если query-логика станет большой
- [tests/test_metrics_api.py](/Users/dmitriy/Projects/ERP_lift_company/tests/test_metrics_api.py)
- новые тесты отчетов

#### Какие тесты добавить или обновить

- RBAC-тесты отчетов.
- Fixture-тесты отчета по мастерам с известными counts/durations.
- Тесты агрегации `problem_type`.
- Тесты ranking проблемных лифтов и объектов.
- Тесты SLA/stale отчета.
- Тесты date range и фильтров.

### Sprint 5 - UX-полировка

Цель: сделать CRM удобной для ежедневной работы после стабилизации данных и отчетов.

#### Задачи

1. Упростить меню.
   - Целевые разделы: `Заявки`, `Объекты`, `Лифты`, `Мастера`, `Клиенты`, `ТО`, `Отчеты`, `Пользователи`.
   - Переименовать или объединить неочевидные `Панель`, `Контроль этапов`, `Админ`.
   - Не добавлять пункты `Склад`, `Финансы`, `Запчасти`.

2. Перевести смешанные English labels на русский.
   - Заменить видимые пользователю `active`, `paused`, `monthly`, `overdue only`, `Response`, `Completion`, `SLA breach`, `Asset`.
   - Backend enum values не менять без отдельной причины.

3. Сделать compact view для заявок.
   - По умолчанию показать плотный список для диспетчера.
   - Колонки/поля: id, статус, приоритет, тип поломки, объект/лифт, мастер, SLA state, последнее событие.
   - Детали оставить в карточке/drawer.

4. Добавить глобальный поиск.
   - Искать по заявкам, объектам, лифтам, адресам, серийным номерам, клиентам, договорам и мастерам.
   - Добавить endpoint вроде `/api/search?q=...`.
   - Возвращать typed results с прямыми ссылками.
   - Учитывать role scope.

5. Убрать лишние элементы из главного экрана.
   - Низкочастотные действия вынести из первого экрана.
   - Оставить быстрый create flow, активные заявки и ключевые фильтры.
   - Не скрывать важные operational alerts.

#### Критерии приемки

- Первый экран диспетчера фокусируется на создании заявки и контроле активных заявок.
- Меню и labels понятны и на русском.
- Compact view уменьшает горизонтальную перегрузку списка заявок.
- Глобальный поиск находит заявки, объекты, лифты и клиентов из одного поля.
- Mobile UI мастера не перегружен admin-only элементами.
- В UI не появились склад, финансы, запчасти, зарплаты, закупки, SaaS или сложный RBAC.

#### Какие файлы примерно будут затронуты

- [templates/index.html](/Users/dmitriy/Projects/ERP_lift_company/templates/index.html)
- [templates/mobile.html](/Users/dmitriy/Projects/ERP_lift_company/templates/mobile.html), только для небольшой текстовой/history-полировки
- [static/mobile.js](/Users/dmitriy/Projects/ERP_lift_company/static/mobile.js), только для небольшой текстовой/history-полировки
- [liftcrm/tickets/routes.py](/Users/dmitriy/Projects/ERP_lift_company/liftcrm/tickets/routes.py)
- [liftcrm/assets/routes.py](/Users/dmitriy/Projects/ERP_lift_company/liftcrm/assets/routes.py)
- новый search route/module при необходимости
- [tests/test_desktop_nav_rbac.py](/Users/dmitriy/Projects/ERP_lift_company/tests/test_desktop_nav_rbac.py)
- [tests/test_xss_rendering_guards.py](/Users/dmitriy/Projects/ERP_lift_company/tests/test_xss_rendering_guards.py)

#### Какие тесты добавить или обновить

- Desktop navigation/RBAC тесты для видимых разделов.
- Search API тесты для каждого типа результата и role scope.
- Compact-view rendering/XSS guard.
- Regression test, что forbidden menu items вроде склада/финансов не добавлены.

## Риски

- SQLite-миграции ручные. Каждая новая таблица, колонка и индекс должны быть идемпотентными.
- Миграция объектов может создать дубликаты зданий при слабой нормализации адресов.
- `Asset` сейчас хранит и лифт, и объектный контекст; изменения сериализации могут сломать desktop, mobile, карту, import/export и историю.
- Desktop UI сконцентрирован в одном большом `templates/index.html`; крупные правки могут случайно задеть соседние вкладки.
- Mobile PWA имеет offline cache/outbox. Новые поля в ticket serialization не должны ломать кеш и sync events.
- Отчеты могут стать медленными без индексов на `tickets.asset_id`, `tickets.building_id`, `tickets.assigned_master_id`, `tickets.status`, `tickets.created_at`, `tickets.problem_type`, comments, attachments и связанные таблицы.
- Признак проблемности может восприниматься как оценка работы людей. В UI формулировать его как фактический сигнал по повторным заявкам, а не как обвинение.
- Старые `objects/objects.xlsx/json` и deprecated `/api/objects` могут путать новую объектную модель. В Sprint 2 нужно явно решить судьбу compatibility alias.

## Порядок реализации

1. Не писать код, пока пользователь отдельно не разрешит Sprint 1.
2. Перед каждым спринтом обновлять этот план:
   - отметить разрешение в `Progress`;
   - добавить новые факты в `Surprises & Discoveries`;
   - записать решения в `Decision Log`.
3. Работать milestone-by-milestone внутри текущего спринта.
4. После каждого milestone запускать focused tests и записывать проверку в `Outcomes & Retrospective`.
5. Коммиты делать небольшими и рабочими:
   - schema/migration;
   - backend/API;
   - UI;
   - tests/docs.
6. Не начинать следующий спринт без выполненных критериев приемки текущего спринта и отдельного разрешения пользователя.

## Общий список файлов, которые могут быть затронуты

Ожидаемые CRM-core файлы:

- [PLANS.md](/Users/dmitriy/Projects/ERP_lift_company/PLANS.md)
- [liftcrm/db.py](/Users/dmitriy/Projects/ERP_lift_company/liftcrm/db.py)
- [liftcrm/__init__.py](/Users/dmitriy/Projects/ERP_lift_company/liftcrm/__init__.py)
- [liftcrm/tickets/routes.py](/Users/dmitriy/Projects/ERP_lift_company/liftcrm/tickets/routes.py)
- [liftcrm/tickets/repository.py](/Users/dmitriy/Projects/ERP_lift_company/liftcrm/tickets/repository.py)
- [liftcrm/tickets/service.py](/Users/dmitriy/Projects/ERP_lift_company/liftcrm/tickets/service.py)
- [liftcrm/assets/routes.py](/Users/dmitriy/Projects/ERP_lift_company/liftcrm/assets/routes.py)
- [liftcrm/assets/service.py](/Users/dmitriy/Projects/ERP_lift_company/liftcrm/assets/service.py)
- [liftcrm/objects/routes.py](/Users/dmitriy/Projects/ERP_lift_company/liftcrm/objects/routes.py)
- возможный новый `liftcrm/reports/routes.py`
- возможный новый object/building service module
- [templates/index.html](/Users/dmitriy/Projects/ERP_lift_company/templates/index.html)
- [templates/lift_detail.html](/Users/dmitriy/Projects/ERP_lift_company/templates/lift_detail.html)
- [templates/mobile.html](/Users/dmitriy/Projects/ERP_lift_company/templates/mobile.html)
- возможный новый `templates/object_detail.html`
- [static/lift_detail.js](/Users/dmitriy/Projects/ERP_lift_company/static/lift_detail.js)
- [static/mobile.js](/Users/dmitriy/Projects/ERP_lift_company/static/mobile.js)
- возможный новый `static/object_detail.js`
- [docs/RUNBOOK.md](/Users/dmitriy/Projects/ERP_lift_company/docs/RUNBOOK.md), только после operator-facing изменений
- [docs/ARCHITECTURE.md](/Users/dmitriy/Projects/ERP_lift_company/docs/ARCHITECTURE.md), только после реализации object model/reporting

Файлы/области, которые не трогать без отдельного запроса:

- `vendor/`;
- складские модули, если они появятся;
- модули запчастей, если они появятся;
- finance/invoice/payment/purchase/payroll модули, если они появятся;
- SaaS/multi-company инфраструктура.

## Тестовый план

Минимальная focused validation по спринтам:

- Sprint 1:
  - `venv/bin/python -m pytest tests/test_metrics_api.py tests/test_ticket_filters.py tests/test_audit_log.py -q`
  - добавить focused tests для комментариев, `problem_type` и create-flow.
- Sprint 2:
  - tests миграции object/building;
  - `venv/bin/python -m pytest tests/test_assets_api.py tests/test_ticket_filters.py -q`;
  - добавить object API/card summary tests.
- Sprint 3:
  - `venv/bin/python -m pytest tests/test_lift_history.py tests/test_technician_history.py tests/test_xss_rendering_guards.py -q`;
  - добавить lift summary и mobile lift-history scope tests.
- Sprint 4:
  - `venv/bin/python -m pytest tests/test_metrics_api.py -q`;
  - добавить report endpoint tests для мастеров, problem types, problematic lifts, problematic objects и SLA/stuck tickets.
- Sprint 5:
  - `venv/bin/python -m pytest tests/test_desktop_nav_rbac.py tests/test_xss_rendering_guards.py -q`;
  - добавить global search API tests и compact-view guard tests.

Финальная проверка после каждого спринта:

- relevant focused tests;
- `venv/bin/python -m pytest -q`, если спринт затрагивает модели, сериализацию, auth, mobile sync или общий UI;
- `git diff --check`;
- ручной smoke test в браузере для измененных dispatcher/admin/mobile flows.

## Manual Smoke Checklist

Использовать после implementation-спринтов, не в рамках этой planning-only задачи:

- Login as dispatcher.
- Создать заявку по выбранному лифту.
- Создать заявку без выбранного лифта только через advanced/manual path.
- Добавить desktop-комментарий в заявку.
- Отфильтровать активные заявки по статусу, мастеру, приоритету, SLA overdue и поиску.
- Открыть карточку лифта и проверить active/latest/history секции.
- Login as technician и проверить, что видны только назначенные заявки.
- В mobile ticket detail проверить историю лифта только для разрешенных заявок.
- Login as admin и проверить отчеты по мастерам, типам поломок, проблемным лифтам/объектам и SLA/stuck.
- Убедиться, что не появились склад, финансы, запчасти, зарплаты, закупки, SaaS или сложный RBAC.

## End-of-plan Change Log

- Change: старый многораздельный `PLANS.md` заменен focused CRM-core roadmap.
  Reason: пользователь попросил подготовить практичный план по CRM-аудиту и отдельно запретил реализацию Sprint 1 на этом шаге.
  Date/Author: 2026-06-17 / codex
