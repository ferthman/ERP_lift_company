# Technician Mobile App (PWA + Offline Outbox + Sync) — ExecPlan

This PLANS.md file is a living execution plan. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

Treat the reader as a complete beginner to this repository. The only context they have is the working tree and this file. Do not assume any prior conversation.

---

# Asset/Lift Import Workflow PR — ExecPlan

## Purpose / Big Picture

Make the SQL-backed lift registry practical for a real elevator company by letting admin and dispatcher users import assets from CSV or Excel `.xlsx` files. Keep this PR focused on the existing assets area: no PWA/offline logic, no CSRF/CORS/session changes, no upload authorization changes, no backup/restore changes, no Postgres/Docker/deployment work, and no unrelated frontend/backend refactors.

The import targets the existing `Asset` model fields only: `address`, `address_norm`, `entrance`, `lift_label`, `serial_no`, `lat`, `lon`, and `status`. `customer_id` exists in the database model but is not exposed in the current assets UI/export and will not be imported in this PR.

## Progress

- [x] (2026-05-23 18:13Z) Read `README.md`, `AGENTS.md`, `PLANS.md`, and `docs/RUNBOOK.md`.
- [x] (2026-05-23 18:13Z) Inspect current asset implementation: `liftcrm/assets/routes.py`, `liftcrm/db.py`, `templates/index.html`, `templates/lift_detail.html`, `static/lift_detail.js`, `scripts/seed_assets_from_objects_xlsx.py`, and `tests/test_assets_api.py`.
- [x] (2026-05-23 18:13Z) Verify existing behavior before adding import: assets already have CRUD, search, SQL-backed map usage, CSV/XLSX export, and a one-off `objects.xlsx` seed script; no admin/dispatcher upload import endpoint or UI exists.
- [x] (2026-05-23 18:13Z) Create this focused import ExecPlan before coding.
- [x] (2026-05-23 18:19Z) Implement backend parsing, validation, duplicate handling, and import endpoint.
- [x] (2026-05-23 18:19Z) Add minimal assets-page upload/result UI.
- [x] (2026-05-23 18:19Z) Update runbook import/export documentation.
- [x] (2026-05-23 18:19Z) Add focused import tests.
- [x] (2026-05-23 18:21Z) Run focused tests, full pytest suite, `git diff --check`, and `git status --short`.

## Surprises & Discoveries

- Observation: The working tree started on `codex/local-backup-restore`; `main` was behind `origin/main` by five commits. I fetched and fast-forwarded local `main` to `9558855` before creating `codex/asset-import-pr94`.
  Evidence: `git fetch origin main`, `git pull --ff-only origin main`, and `git switch -c codex/asset-import-pr94`.
- Observation: Existing asset export headers are `id`, `address`, `entrance`, `lift_label`, `serial_no`, `lat`, `lon`, `status`, `created_at`, and `updated_at`.
  Evidence: `export_assets_xlsx()` and `export_assets_csv()` in `liftcrm/assets/routes.py`.
- Observation: Existing role policy allows admin/dispatcher asset CRUD/export and blocks technicians through `@role_required("admin", "dispatcher")`.
  Evidence: `create_asset()`, `update_asset()`, `delete_asset()`, and export routes in `liftcrm/assets/routes.py`.

## Decision Log

- Decision: Implement skip-existing duplicate handling, not update-existing.
  Rationale: The current asset CRUD has minimal validation and the request prioritizes avoiding silent duplicates. Skipping existing rows is safer for a bulk import PR because it will not overwrite a live registry by accident.
  Date/Author: 2026-05-23 / codex
- Decision: Use `serial_no` as the strongest identity key, then fall back to normalized `(address, entrance, lift_label)` when all composite parts are available.
  Rationale: `serial_no` already has a DB unique constraint, and the composite matches the practical fields visible in the UI without adding new schema constraints.
  Date/Author: 2026-05-23 / codex
- Decision: Add the import endpoint as `POST /api/assets/import` using multipart upload and in-memory parsing only.
  Rationale: This keeps file handling small and avoids path traversal/permanent uploaded import files.
  Date/Author: 2026-05-23 / codex

## Outcomes & Retrospective

- Outcome (2026-05-23): Added `POST /api/assets/import` for admin/dispatcher multipart CSV/XLSX imports. The endpoint parses files in memory, requires an address/object column, skips empty rows, validates coordinates/status, and returns `created`, `updated`, `skipped`, `skipped_duplicates`, `invalid`, and row-level `errors`.
- Outcome (2026-05-23): Duplicate handling is skip-existing: `serial_no` is the strongest key; otherwise `(address, entrance, lift_label)` is used when all three values are present. Existing assets are not updated by import.
- Outcome (2026-05-23): Added a small import control to the existing assets registry page and documented file format, aliases, examples, duplicate behavior, verification, and backup recommendation in `docs/RUNBOOK.md`.
- Validation (2026-05-23): `venv/bin/python -m pytest tests/test_assets_api.py -q` passed (`15 passed in 1.47s`).
- Validation (2026-05-23): `venv/bin/python -m pytest -q` passed (`119 passed in 16.75s`).
- Validation (2026-05-23): `git diff --check` passed with no output.
- Validation (2026-05-23): `git status --short` showed only intended files: `PLANS.md`, `docs/RUNBOOK.md`, `liftcrm/assets/routes.py`, `templates/index.html`, and `tests/test_assets_api.py`.

## Plan of Work

### Milestone 1 — Backend import workflow

Goal: Admin/dispatcher users can submit `.csv` or `.xlsx` files and receive a structured import result without bad files crashing the app.

Work:

- Add import parsing helpers in `liftcrm/assets/routes.py` or a small assets-local helper module if the route file becomes too dense.
- Accept multipart field `file`, enforce extension allow-list `.csv` and `.xlsx`, and rely on the app-level `MAX_CONTENT_LENGTH` for the existing 16 MB upload cap.
- Parse CSV with `csv.DictReader` from memory and XLSX with `openpyxl.load_workbook(..., read_only=True, data_only=True)` from memory.
- Support aliases for `address`, `entrance`, `lift_label`, `serial_no`, `lat`, `lon`, and `status`.
- Skip fully empty rows.
- Validate required `address`; validate `lat`/`lon` as numbers when present; accept only `ACTIVE` or `INACTIVE` status, defaulting to `ACTIVE`.
- Use skip-existing duplicate behavior by `serial_no` first, then normalized `(address, entrance, lift_label)` when all three exist.
- Return JSON with `created`, `updated`, `skipped`, `invalid`, and row-level `errors`.

Validation:

- Focused tests for valid CSV, valid XLSX, roles, bad file type, invalid coordinates, duplicate skipping, row-level errors, and result counts.

### Milestone 2 — Minimal UI and docs

Goal: The existing assets page exposes the import workflow without redesigning the registry.

Work:

- Add a compact file input and import button in the existing assets section of `templates/index.html`.
- POST selected files to `/api/assets/import` using `FormData`.
- Render created/skipped/invalid counts and row-level errors in the assets area.
- Refresh the asset table and map after a successful import.
- Update `docs/RUNBOOK.md` with supported format, aliases, examples, duplicate behavior, verification steps, and a recommendation to run a local backup before large imports.

Validation:

- Static/browser-level behavior is covered through route tests plus source inspection; run full pytest and `git diff --check`.

## End-of-plan change log

- Change: Added Asset/Lift Import Workflow PR ExecPlan.
  Reason: The task spans backend, frontend, docs, and tests, so `AGENTS.md` requires an ExecPlan before coding.
  Date/Author: 2026-05-23 / codex

---

# Local Backup/Restore Tooling PR — ExecPlan

## Purpose / Big Picture

Make the local MVP safer for a controlled pilot by adding small operator scripts that back up and restore the local SQLite database, uploads, and generated archive/export files. This is only local MVP tooling. It is not a production backup architecture and does not migrate the app to Postgres, add Docker/deployment, change PWA/offline behavior, change CSRF/CORS/session security, or touch uploads authorization, XSS rendering, or metrics logic.

## Progress

- [x] (2026-05-23 17:57Z) Read `README.md`, `AGENTS.md`, `PLANS.md`, and `docs/RUNBOOK.md`.
- [x] (2026-05-23 17:57Z) Inspect current local runtime files: `lift_crm.db`, `uploads/`, and `archive.xlsx`.
- [x] (2026-05-23 17:57Z) Create this focused local backup/restore ExecPlan before coding.
- [x] (2026-05-23 18:03Z) Implement local backup script, restore script, `.gitignore` entry, docs, and focused tests.
- [x] (2026-05-23 18:05Z) Run focused backup/restore tests, full pytest suite, and `git status --short`.

## Surprises & Discoveries

- Observation: The working tree started on `codex/pwa-offline-reliability`, but fetched `origin/main` is `2dad997` and does not contain `codex/pwa-offline-reliability`.
  Evidence: `git merge-base --is-ancestor codex/pwa-offline-reliability origin/main; printf '%s\n' $?` returned `1`.
- Observation: Runtime local data exists and is currently untracked: `lift_crm.db`, `uploads/`, and `archive.xlsx`.
  Evidence: `find . -maxdepth 2 \( -name 'lift_crm.db' -o -name 'uploads' -o -name 'archive*.xlsx' -o -name '*export*.xlsx' -o -name '*export*.csv' \) -print`.
- Observation: `.gitignore` already ignores `lift_crm.db`, `uploads/`, and `archive*.xlsx`, but does not yet ignore `backups/`.
  Evidence: `sed -n '1,220p' .gitignore`.

## Decision Log

- Decision: Base this branch on fetched `origin/main` instead of the PWA branch.
  Rationale: The requested latest-main PWA merge was not visible in the fetched remote, and basing on the PWA branch would mix unrelated PWA/offline changes into this focused backup/restore PR.
  Date/Author: 2026-05-23 / codex
- Decision: Treat archive/export files as root-level `archive*.xlsx` plus root-level `*export*.xlsx` and `*export*.csv`.
  Rationale: The runbook documents `archive.xlsx` and `archive_N.xlsx`; asset export endpoints generate CSV/XLSX downloads, and this keeps the backup scope file-based and local without touching app routes.
  Date/Author: 2026-05-23 / codex

## Outcomes & Retrospective

- Outcome (2026-05-23): Added standard-library local backup and restore scripts for `lift_crm.db`, `uploads/`, and root-level archive/export files. Backup creates `backups/<timestamp>/manifest.json`; restore refuses to overwrite existing local data unless `--force` is provided.
- Outcome (2026-05-23): Added `backups/` to `.gitignore`, documented pilot-day backup/restore steps in `docs/RUNBOOK.md`, and added focused pytest coverage in `tests/test_local_backup_restore.py`.
- Validation (2026-05-23): `venv/bin/python -m pytest tests/test_local_backup_restore.py -q` passed (`5 passed in 0.03s`).
- Validation (2026-05-23): `venv/bin/python -m pytest -q` passed (`105 passed in 16.43s`).
- Validation (2026-05-23): `git status --short` showed only intended files: modified `.gitignore`, `PLANS.md`, `docs/RUNBOOK.md`; untracked `scripts/backup_local.py`, `scripts/restore_local.py`, `tests/test_local_backup_restore.py`.

## Plan of Work

### Milestone 1 — Backup and restore scripts

Goal: Operators can create a timestamped local copy of the SQLite DB, uploads, and archive/export files, and can restore a selected backup only after explicitly accepting overwrite risk.

Work:

- Add `scripts/backup_local.py`.
- Add `scripts/restore_local.py`.
- Backup behavior: create `backups/YYYYmmdd-HHMMSS/`, copy `lift_crm.db` if present, copy `uploads/` if present, copy archive/export files if present, and write `manifest.json` with timestamp, source root, copied file entries, byte sizes, and warnings for optional missing inputs.
- Restore behavior: accept a backup folder argument, refuse to overwrite existing `lift_crm.db`, `uploads/`, or archive/export files unless `--force` is provided, then restore present backup contents.
- Keep scripts standalone and standard-library only.

Validation:

- Add pytest coverage for backup with all inputs, backup with optional files missing, manifest creation, restore refusal without `--force`, and restore with `--force` into a temp root.

### Milestone 2 — Docs, ignore rules, and final validation

Goal: The local pilot runbook explains the operator workflow and generated backups are never committed.

Work:

- Add `backups/` to `.gitignore`.
- Update `docs/RUNBOOK.md` with backup creation, restore, restore verification, daily pilot backup checklist, and an explicit local-MVP-only warning.
- Run focused backup/restore tests.
- Run the full pytest suite.
- Run `git status --short`.

Validation:

- Record exact commands and results in this plan and final response.

## End-of-plan change log

- Change: Added Local Backup/Restore Tooling PR ExecPlan.
  Reason: The task spans scripts, docs, ignore rules, and tests, so `AGENTS.md` requires an ExecPlan before coding.
  Date/Author: 2026-05-23 / codex

---

# PWA Offline Reliability PR — ExecPlan

## Purpose / Big Picture

Create a focused reliability PR for the technician PWA only. Make the service worker avoid stale authenticated/API responses, keep static shell/assets cacheable, make deploy updates predictable, improve visibility and retry/discard handling for failed offline outbox events, and add small photo queue safety limits. Do not add product features, do not touch CSRF/CORS/session security, upload authorization, Docker/Postgres/deployment, or broad frontend architecture.

## Progress

- [x] (2026-05-06 17:54Z) Read `README.md`, `AGENTS.md`, `PLANS.md`, and `docs/RUNBOOK.md`.
- [x] (2026-05-06 17:54Z) Inspect `templates/mobile.html`, `static/mobile.js`, `static/sw.js`, service worker registration, `/api/me/tickets`, `/api/sync/events`, and upload/photo flow.
- [x] (2026-05-06 17:54Z) Create the focused PWA/offline reliability ExecPlan before coding.
- [x] (2026-05-06 17:56Z) Patch service worker caching so API/authenticated requests are network-only and static shell/assets remain cache-first.
- [x] (2026-05-06 17:57Z) Patch mobile outbox/photo handling with visible failed-event rows, retry/discard controls, transient retry behavior, and practical photo queue limits.
- [x] (2026-05-06 17:57Z) Add focused regression tests for service worker caching, mobile outbox visibility/retryability, sync compatibility, mobile ticket flow, and upload access.
- [x] (2026-05-06 17:57Z) Update manual offline validation notes.
- [x] (2026-05-06 18:01Z) Run focused tests, full pytest suite, local app startup, smoke checks, and `git status --short`.

## Surprises & Discoveries

- Observation: `static/sw.js` currently uses cache-first behavior for every fetch request via `caches.match(e.request).then(resp => resp || fetch(e.request))`.
  Evidence: `sed -n '1,260p' static/sw.js`.
- Observation: `/mobile` and the desktop shell both register `/static/sw.js`, so any service worker API caching bug affects both technician and admin API calls under the same origin.
  Evidence: `rg -n "serviceWorker|manifest|sw\\.js|mobile" templates static liftcrm app.py`.
- Observation: `static/mobile.js` already stores failed sync events as `status: "error"` and shows only aggregate `Ошибка (N)` status; there is no visible per-event retry/discard control.
  Evidence: `syncEvents()` and `updateSyncIndicators()` in `static/mobile.js`.
- Observation: Offline photos are stored as raw IndexedDB blobs with `status: "pending"` and retried only for pending records; there is no file size validation, failed upload status, or queue cap.
  Evidence: `renderDetail()` photo input handler and `syncPhotos()` in `static/mobile.js`.
- Observation: Backend `/api/sync/events` already returns per-event error codes for conflicts, geofence failures, validation failures, forbidden tickets, immutable tickets, and duplicates.
  Evidence: `sync_events()` in `liftcrm/tickets/routes.py`.

## Decision Log

- Decision: Treat service worker API/authenticated fetches as network-only instead of network-first with a cached fallback.
  Rationale: The app already owns offline ticket data in IndexedDB. Falling back from Cache Storage for `/api/*`, uploads, login, or HTML pages can serve stale or cross-user authenticated data.
  Date/Author: 2026-05-06 / codex
- Decision: Keep the outbox UX small by adding an inline failed-event panel with retry and discard actions rather than building a separate queue management screen.
  Rationale: The current mobile page already has sync controls and aggregate status; a compact panel makes failures visible without product expansion or frontend refactoring.
  Date/Author: 2026-05-06 / codex
- Decision: Add practical client-side photo limits only: maximum file size and maximum queued photo count.
  Rationale: This prevents silent unbounded IndexedDB growth while avoiding a larger compression/storage-management feature.
  Date/Author: 2026-05-06 / codex

## Outcomes & Retrospective

- Outcome (2026-05-06): `static/sw.js` now precaches only static shell/assets, deletes old caches on activation, claims clients after activation, and sends API, uploads, login/logout/admin/mobile HTML, non-GET, and other non-static requests directly to network.
- Outcome (2026-05-06): `templates/mobile.html` and `static/mobile.js` now show a compact failed outbox panel. Failed sync events and failed photo uploads remain visible with retry and discard actions; transient network failures stay pending for later retry.
- Outcome (2026-05-06): Photo queue safety now rejects files larger than 8 MB before IndexedDB storage and caps the local queued photo count at 20.
- Outcome (2026-05-06): `docs/RUNBOOK.md` now has a manual offline/PWA checklist covering online load, offline actions, reconnect, duplicate prevention, visible failures, photo limits, metrics, and protected uploads.
- Validation (2026-05-06): `venv/bin/python -m pytest tests/test_pwa_offline_reliability.py tests/test_sync_events.py tests/test_mobile_login_flow.py tests/test_mobile_ticket_coords.py tests/test_upload_access.py tests/test_metrics_api.py -q` passed (39 tests).
- Validation (2026-05-06): `venv/bin/python -m pytest -q` passed (104 tests).
- Validation (2026-05-06): First local startup attempt `PORT=5056 venv/bin/python app.py` failed under sandbox with `Operation not permitted`; rerun with approved local-server escalation started Flask successfully.
- Validation (2026-05-06): Local smoke against `http://127.0.0.1:5056` passed admin login, master creation, technician role assignment, ticket creation and assignment, `/mobile` render with outbox panel, `/api/me/tickets`, sync accept, duplicate event idempotency, sync start, photo upload, anonymous upload redirect to login, assigned technician upload readback, and `/api/metrics`.
- Validation (2026-05-06): Smoke summary: `{"accept_sync": "OK", "admin_login": 200, "anonymous_upload_status": 302, "assigned_ticket_seen": true, "duplicate_sync": "duplicate", "master_id": 182, "metrics_total_tickets_present": true, "mobile_status": 200, "start_sync": "OK", "technician_upload_status": 200, "ticket_id": 155, "upload_status": 200}`.

## Plan of Work

### Milestone 1 — Service worker cache strategy

Goal: Avoid stale API/authenticated responses while preserving offline shell asset caching.

Work:

- Update `static/sw.js` to version caches explicitly, pre-cache only safe static shell/assets, and remove old caches during activation.
- Return `fetch(request)` for `/api/*`, `/uploads/*`, login/logout/admin/mobile HTML navigations, non-GET requests, and other non-static requests.
- Keep cache-first behavior only for static assets and manifests.

Validation:

- Add a static regression test that proves the service worker contains API/upload network-only handling and does not use blanket `caches.match(e.request)` for all fetches.

### Milestone 2 — Outbox and photo queue reliability

Goal: Failed offline work remains visible and retryable, while transient failures stay queued.

Work:

- Add a minimal failed outbox panel in `templates/mobile.html`.
- In `static/mobile.js`, render failed events with ticket/type/error labels, add retry and discard buttons, and keep transient fetch failures as pending.
- Add photo file size validation, queued-photo count limits, visible photo queue status, and failed-photo retry behavior.

Validation:

- Add static tests over `templates/mobile.html` and `static/mobile.js` for failed outbox panel controls, retry/discard behavior, transient pending preservation, and photo limits.

### Milestone 3 — Backend compatibility, docs, and smoke

Goal: Prove existing technician sync, mobile ticket, upload access, and metrics flows still work.

Work:

- Run focused tests for sync events, mobile login/ticket endpoints, upload access, metrics, and PWA static guards.
- Run the full pytest suite.
- Update `docs/RUNBOOK.md` with a short manual offline checklist covering install/open, online load, offline actions, reconnect, duplicate prevention, and visible failures.
- Start the app locally and run a smoke script covering admin ticket creation, technician `/mobile`, accept/start sync, queued-event compatibility, protected uploads, and metrics.
- Run `git status --short` and record exact results.

Validation:

- Record exact commands/results in this plan and final response.

## End-of-plan change log

- Change: Added PWA Offline Reliability PR ExecPlan.
  Reason: The task changes service worker cache strategy, IndexedDB outbox behavior, photo queue safety, docs, and tests, so `AGENTS.md` requires an ExecPlan.
  Date/Author: 2026-05-06 / codex
- Change: Completed the focused PWA/offline reliability implementation and validation.
  Reason: Record the final behavior, tests, smoke evidence, and review scope.
  Date/Author: 2026-05-06 / codex

---

# CSRF/CORS/Session Security Hardening PR — ExecPlan

## Purpose / Big Picture

Harden only the cookie-auth security envelope: CORS, session cookie settings, production `SECRET_KEY` validation, and same-origin protection for unsafe state-changing requests. Preserve the existing same-domain Flask UI, JSON API, technician mobile sync, uploads access rules, archive/admin workflows, and metrics endpoint. This PR must not implement product features or touch PWA/offline, upload authorization, XSS rendering, Docker/Postgres/deployment, or unrelated refactors.

## Progress

- [x] (2026-05-06 17:34Z) Read `README.md`, `AGENTS.md`, `PLANS.md`, `liftcrm/config.py`, `liftcrm/utils/security.py`, app factory/auth routes, route decorators, and frontend fetch/form patterns.
- [x] (2026-05-06 17:42Z) Add config-driven CORS/session/SECRET_KEY hardening in the app factory and security utilities.
- [x] (2026-05-06 17:42Z) Add same-origin protection for unsafe cookie-auth state-changing requests.
- [x] (2026-05-06 17:42Z) Add focused pytest coverage for CORS, cookies, production secret validation, same-origin rejection/acceptance, login, ticket create/update, and mobile sync.
- [x] (2026-05-06 17:43Z) Run focused security tests, then the full pytest suite.
- [x] (2026-05-06 17:51Z) Start the app locally and run requested smoke checks.
- [x] (2026-05-06 17:54Z) Record exact validation results, changed files, and retrospective.

## Surprises & Discoveries

- Observation: `liftcrm/__init__.py` currently enables `CORS(app, supports_credentials=True)` with no origin restrictions.
  Evidence: `rg "CORS|supports_credentials" liftcrm`.
- Observation: Current session cookie settings are hardcoded in `create_app()` as `SESSION_COOKIE_SAMESITE = "Lax"` and `SESSION_COOKIE_SECURE = False`; `SECRET_KEY` defaults to `dev-secret` in `liftcrm/config.py`.
  Evidence: `liftcrm/__init__.py` and `liftcrm/config.py`.
- Observation: State-changing endpoints are all same-app cookie flows, including `/api/login`, `/login`, `/api/logout`, `/logout`, ticket create/update/assignment/archive/mobile sync/upload actions, asset CRUD, and access-management actions.
  Evidence: `rg -n "@.*\\.(post|patch|put|delete)|methods=.*(POST|PATCH|PUT|DELETE)" liftcrm`.
- Observation: Frontend unsafe requests are vanilla `fetch()` calls from `templates/index.html` and `static/mobile.js`, plus same-site form posts in `templates/login.html` and `templates/index.html`; no separate frontend origin was found.
  Evidence: `rg -n "fetch\\(|method:\\s*['\\\"](POST|PATCH|PUT|DELETE)|<form" templates static liftcrm tests`.
- Observation: The metrics endpoint is healthy but currently returns top-level metrics keys such as `total_tickets`, not a nested `totals` object.
  Evidence: The first smoke script reached `GET /api/metrics` with status 200 and stopped only because the script asserted the wrong response shape.

## Decision Log

- Decision: Use strict same-origin validation for unsafe methods instead of adding CSRF tokens in this PR.
  Rationale: The app is same-origin Flask-rendered UI plus mobile PWA; a token rollout would require broader template and fetch plumbing, while Origin/Referer validation protects browser cookie-auth unsafe requests without rewriting frontend flows.
  Date/Author: 2026-05-06 / codex
- Decision: Disable CORS by default and only enable credentialed CORS when `CORS_ALLOWED_ORIGINS` contains explicit non-wildcard origins.
  Rationale: The inspected frontend does not require cross-origin API calls, and wildcard credentialed CORS is unsafe.
  Date/Author: 2026-05-06 / codex
- Decision: Treat `APP_ENV` or `FLASK_ENV` equal to `production` as production mode for secret/cookie defaults.
  Rationale: The repo currently has no explicit environment abstraction; using these conventional environment variables keeps development working and lets deployment fail fast on weak secrets.
  Date/Author: 2026-05-06 / codex

## Outcomes & Retrospective

- Outcome (2026-05-06): Removed default broad credentialed CORS, added opt-in explicit `CORS_ALLOWED_ORIGINS`, added environment-driven session cookie settings, added production-only strong `SECRET_KEY` validation, and added unsafe-method same-origin protection using `Origin`/`Referer` while preserving no-header local/test clients.
- Outcome (2026-05-06): Added focused security regression tests in `tests/test_security_hardening.py` and documented new runtime settings in `.env.example` and `docs/RUNBOOK.md`.
- Validation (2026-05-06): `venv/bin/python -m pytest tests/test_security_hardening.py -q` passed (8 tests).
- Validation (2026-05-06): `venv/bin/python -m pytest -q` passed (97 tests).
- Validation (2026-05-06): `PORT=5055 venv/bin/python app.py` started the Flask app locally after sandbox approval. Corrected smoke script passed admin login, master creation, technician role assignment, ticket create, ticket update, technician assignment, assigned ticket read, metrics endpoint, admin logout, technician login, mobile sync accept, mobile sync start, upload file, and upload readback.
- Validation (2026-05-06): Smoke-test artifacts in `lift_crm.db` and `uploads/` were cleaned up; `git status --short` showed only intended code/docs/test files modified.

## Plan of Work

### Milestone 1 — Configuration hardening

Goal: Production startup and response cookies are safer while local development still works.

Work:

- Update `liftcrm/config.py` with environment helpers for app env, session cookie flags, allowed CORS origins, and secret validation.
- Update `liftcrm/__init__.py` to call secret validation during `create_app()`, apply configurable session cookie settings, and remove broad credentialed CORS.
- If CORS origins are configured, enable `flask_cors.CORS` with `supports_credentials=True` and the explicit origin list only.

Validation:

- Unit tests cover dev fallback, production weak/missing secret rejection, production secure cookie defaults, local development cookie behavior, and no wildcard credentialed CORS.

### Milestone 2 — Same-origin unsafe request guard

Goal: Cookie-auth state-changing browser requests from other origins are rejected before route handlers mutate state.

Work:

- Add helpers in `liftcrm/utils/security.py` to compare `Origin` or `Referer` against the request host URL for `POST`, `PATCH`, `PUT`, and `DELETE`.
- Register a `before_request` guard in `liftcrm/__init__.py` for unsafe methods.
- Return JSON 403 for `/api/*` requests and plain 403 for non-API form posts.
- Preserve requests with no browser provenance header so existing tests, CLI/manual local calls, and non-browser clients continue to work.

Validation:

- Tests prove a cross-origin unsafe request is rejected and a same-origin unsafe request is accepted.
- Existing login, ticket create/update, mobile sync, upload, archive, admin workflows remain same-origin compatible.

### Milestone 3 — Focused regression tests and smoke

Goal: Prove the security contract and avoid behavior drift outside this PR scope.

Work:

- Add focused pytest module for security config and same-origin behavior.
- Run the focused test module.
- Run the full pytest suite.
- Start the app locally and smoke-test admin login, ticket create/update, assignment, technician mobile sync accept/start, upload access, and metrics endpoint.
- Run `git status --short`.

Validation:

- Record exact commands and results in this plan and final response.

## End-of-plan change log

- Change: Added CSRF/CORS/session security hardening ExecPlan.
  Reason: The task changes authentication/session/security behavior across app factory, utilities, and tests, so `AGENTS.md` requires an ExecPlan.
  Date/Author: 2026-05-06 / codex
- Change: Completed CSRF/CORS/session security hardening implementation and validation.
  Reason: Track the exact hardening scope, tests, smoke results, and cleanup outcome for review.
  Date/Author: 2026-05-06 / codex

---

# XSS Rendering Hardening PR — ExecPlan

## Purpose / Big Picture

Fix only the highest-risk frontend XSS rendering paths where user-controlled ticket, object/address, comment, asset, and mobile history fields are interpolated into `innerHTML` template strings. Preserve existing UI appearance and behavior, avoid frontend modularization, and add targeted regression coverage that makes these paths hard to reintroduce.

## Progress

- [x] (2026-04-30 14:40Z) Inspect template/static JS rendering paths for `innerHTML` and user-controlled fields.
- [x] (2026-04-30 15:00Z) Patch the identified high-risk desktop, lift history, and mobile render sites with text-safe rendering helpers.
- [x] (2026-04-30 15:03Z) Add targeted pytest regression checks over the affected frontend files.
- [x] (2026-04-30 15:05Z) Run backend/frontend-related tests and manually verify malicious-looking text renders as text.
- [x] (2026-04-30 15:08Z) Record outcomes and exact validation results.

## Surprises & Discoveries

- Observation: The repository has no frontend test runner; available tests are pytest backend tests, so practical regression coverage should use pytest assertions over checked-in JS/templates.
  Evidence: `requirements.txt` and `tests/` exist, but no `package.json` was found.
- Observation: The highest-risk paths are template-string renderers in `templates/index.html`, `static/mobile.js`, `static/history.js`, `static/lift_history.js`, and `static/lift_detail.js`.
  Evidence: `rg "innerHTML|\\$\\{.*description|\\$\\{.*address|\\$\\{.*comment"` across `templates static`.
- Observation: A scoped post-patch scan found no remaining raw interpolations for the requested risky field names in the touched renderers.
  Evidence: `rg "\\$\\{[^}]*\\b(object_name|description|address|close_comment|assigned_master_name|serial_no|lift_label|entrance|body|text|actor|title)\\b" templates/index.html static/mobile.js static/history.js static/lift_history.js static/lift_detail.js` returned no matches.

## Decision Log

- Decision: Use small local `escapeHtml()` helpers in each affected non-module script and the admin inline script instead of introducing a shared frontend module.
  Rationale: The user explicitly asked not to modularize `index.html`, and the existing scripts are standalone files loaded directly by templates.
  Date/Author: 2026-04-30 / codex
- Decision: Keep trusted static markup and enum-derived labels in template strings, but escape user-controlled API fields before interpolation.
  Rationale: This preserves layout/classes while neutralizing ticket descriptions, object/address values, comments, asset fields, actors, titles, and history text.
  Date/Author: 2026-04-30 / codex

## Outcomes & Retrospective

- Outcome (2026-04-30): Added local `escapeHtml()` helpers to the affected standalone scripts and the admin inline script. Escaped high-risk ticket description, object/address, comment, asset/lift, event text, actor, attachment-label, and mobile history render paths while preserving the existing `innerHTML` layout structure where it carries trusted static classes/markup. Added `tests/test_xss_rendering_guards.py`.
- Validation (2026-04-30): `venv/bin/python -m pytest tests/test_xss_rendering_guards.py -q` passed (3 tests); `venv/bin/python -m pytest -q` passed (89 tests). Manual browser fixture served from localhost rendered `<img src=x onerror="window.executed=true"><script>window.executed=true</script>` as visible text; Playwright eval returned `executed: false`, `imageCount: 0`, and `scriptCount: 0`.

## Plan of Work

### Milestone 1 — Patch high-risk renderers

Goal: User-controlled text from tickets, assets/lifts, comments, addresses, and mobile history appears as text, not executable markup.

Work:

- In `static/mobile.js`, escape mobile ticket list, ticket detail, comments, and history timeline/list text before assigning `innerHTML`.
- In `static/history.js`, escape ticket history fields including object name, address, close reason, close comment, and assigned master.
- In `static/lift_history.js` and `static/lift_detail.js`, escape lift header fields, event text/actors, ticket titles, and assigned user labels.
- In `templates/index.html`, add a small escaping helper and apply it to the highest-risk admin tickets/assets/dashboard/map popup renderers that interpolate API data into `innerHTML` or popup HTML.

Validation:

- Search for remaining scoped risky interpolations and confirm remaining raw uses are either static markup, enum labels, dates/numbers, URLs built from IDs, or outside this PR scope.

### Milestone 2 — Regression tests and verification

Goal: Capture the security contract with lightweight tests and run the available suite.

Work:

- Add pytest coverage that inspects the affected JS/template files for the escaping helper and representative escaped render paths.
- Run targeted tests.
- Run the full pytest suite.
- Manually exercise the escaping behavior with malicious-looking strings using a browser/DOM-capable check or direct helper simulation, depending on available tooling.

Validation:

- Record exact commands and results here and in the final response.

## End-of-plan change log

- Change: Added XSS Rendering Hardening PR ExecPlan.
  Reason: The task spans multiple frontend renderers and security-sensitive behavior, so AGENTS.md requires an ExecPlan.
  Date/Author: 2026-04-30 / codex
- Change: Completed XSS rendering hardening milestones and recorded validation.
  Reason: Track exact files, test results, and manual browser evidence for the security patch.
  Date/Author: 2026-04-30 / codex

---

# Upload Access Protection PR — ExecPlan

## Purpose / Big Picture

Protect ticket attachment files served from `/uploads/<filename>` so uploads are no longer public static assets. The route must require login, reject unsafe filename/path access, and authorize by the ticket connected to the attachment: admins can access all uploads, dispatchers can access operational uploads, and technicians can only access uploads for tickets assigned to their master profile. This PR intentionally avoids upload UI changes and broader MIME validation.

## Progress

- [x] (2026-04-30 12:30Z) Inspect current upload creation, attachment serialization, `/uploads/<path:filename>` serving, auth helpers, ticket ownership checks, and existing test setup.
- [x] (2026-04-30 12:31Z) Add protected upload-serving authorization helper and path-safety checks in `liftcrm/tickets/routes.py`.
- [x] (2026-04-30 12:31Z) Add focused upload access tests covering anonymous, unrelated technician, assigned technician, admin, dispatcher, and unsafe filenames.
- [x] (2026-04-30 12:32Z) Run targeted upload/security tests and the full backend test suite.
- [x] (2026-04-30 12:32Z) Record validation results and retrospective.

## Surprises & Discoveries

- Observation: `serve_upload(filename)` was unauthenticated and accepted a path converter before passing the value directly to `send_from_directory`.
  Evidence: `liftcrm/tickets/routes.py` defined `@bp.get("/uploads/<path:filename>")` with no `@login_required`.
- Observation: Attachments already have the ticket relationship needed for authorization, and upload creation already restricts technicians to their assigned tickets.
  Evidence: `liftcrm/db.py` `Attachment.ticket` relationship and `liftcrm/tickets/routes.py` `upload_file()`.

## Decision Log

- Decision: Authorize served uploads by first resolving an exact `Attachment.filename` row, then checking the related ticket.
  Rationale: Files not recorded in the database should not be reachable through the protected ticket upload surface, and ticket-level authorization can reuse existing role/master fields without changing URLs or UI.
  Date/Author: 2026-04-30 / codex
- Decision: Reject any filename containing path separators, `.` or `..`, or a basename mismatch before querying the database.
  Rationale: The route uses a path converter, so traversal and nested-path attempts should fail before filesystem access.
  Date/Author: 2026-04-30 / codex

## Outcomes & Retrospective

- Outcome (2026-04-30): `/uploads/<filename>` now requires authentication, rejects unsafe path-like filenames before filesystem access, resolves uploads through `Attachment.filename`, and enforces ticket-level authorization. Admin can access all attachment-backed uploads, dispatcher can access non-archived operational uploads, and technicians can only access uploads for tickets assigned to their master profile. Validation: `venv/bin/python -m pytest tests/test_upload_access.py -q` passed (6 tests); `venv/bin/python -m pytest -q` passed (86 tests).

## Plan of Work

### Milestone 1 — Protected serving route

Goal: `/uploads/<filename>` requires authentication and only serves ticket-connected files to authorized users.

Work:

- Add `@login_required` to `serve_upload()`.
- Add an internal filename safety check in `liftcrm/tickets/routes.py` that rejects path separators, current/parent directory names, empty names, and basename rewrites.
- Query `Attachment` by exact stored `filename` and require a related ticket.
- Allow roles:
  - `admin`: all uploads.
  - `dispatcher`: non-archived operational uploads.
  - `technician`: only uploads where `Attachment.ticket.assigned_master_id == current_user.master_id`.

Validation:

- Anonymous request to an existing upload returns an auth failure.
- Unsafe path requests do not reach filesystem serving.

### Milestone 2 — Access regression tests

Goal: Capture the ticket-level access contract.

Work:

- Add `tests/test_upload_access.py`.
- Create a temporary app/database/upload folder per test.
- Seed two technician users, assigned tickets, attachment rows, and real files.
- Cover anonymous denied, unrelated technician denied, assigned technician allowed, admin allowed, dispatcher allowed, and unsafe filename denied.

Validation:

- Run the focused upload access test module.

### Milestone 3 — Backend validation

Goal: Ensure no existing backend behavior regresses.

Work:

- Run the focused upload/security tests.
- Run the full backend test suite.

Validation:

- Record exact commands and results here and in the final report.

## End-of-plan change log

- Change: Added and completed Upload Access Protection PR ExecPlan.
  Reason: Upload authorization spans routes, database-backed permissions, filesystem serving, and tests, so AGENTS.md requires an ExecPlan and validation record.
  Date/Author: 2026-04-30 / codex

---

# Technician History (Mobile) — ExecPlan

## Purpose / Big Picture

Add a technician-facing history view under `/mobile` so technicians can review completed/cancelled tickets and inspect a timeline of status changes, comments, and photos for dispute prevention. The backend must enforce technician-only access and ensure technicians only see their own tickets.

## Progress

- [x] (2025-03-08 12:30Z) Implement `/api/me/history` and `/api/me/tickets/<id>/timeline` with technician scoping and status/comment/photo timelines.
- [x] (2025-03-08 12:45Z) Add `/mobile` “История” UI, date filters, timeline panel, and IndexedDB caching for offline use.
- [x] (2025-03-08 13:10Z) Add pytest coverage for technician history access, filtering, and timeline permissions.
- [x] (2025-03-08 13:20Z) Run pytest and capture output; document validation steps.
- [x] (2025-03-08 13:30Z) Update Outcomes & Retrospective with what shipped and any follow-ups.

## Surprises & Discoveries

- None yet.

## Decision Log

- Decision: Filter technician history by `assigned_master_id == current_user.master_id` (MVP), rather than by audit-log authorship.
  Rationale: Matches existing schema and is the simplest correct ownership check for assigned tickets.
  Date/Author: 2025-03-08 / codex
- Decision: Build timeline entries from audit logs (status changes), ticket comments, and attachment uploads, using audit logs for attachment actors when available.
  Rationale: Reuses existing audit trail and avoids schema changes while providing a complete timeline.
  Date/Author: 2025-03-08 / codex

## Outcomes & Retrospective

- Outcome (2025-03-08): Added technician history API endpoints, mobile history UI with offline cache, and pytest coverage for access control and filters. Pytest: 79 passed.

## Plan of Work

### Milestone 1 — Backend endpoints

Goal: Provide technician-scoped history list and ticket timeline endpoints.

Work:

- Add `GET /api/me/history` in `liftcrm/tickets/routes.py`:
  - Role guard: technician only.
  - Filter tickets by `assigned_master_id`.
  - Support `date_from`, `date_to`, `status`, `limit`, `offset`.
  - Sort by closed timestamp (completed_at/cancelled_at fallback to updated_at).
  - Return `ticket_id`, `object_name`, `address`, `status`, `closed_at`, `updated_at`.
- Add `GET /api/me/tickets/<ticket_id>/timeline`:
  - Role guard: technician only.
  - Verify ticket belongs to current technician.
  - Return ordered timeline entries for status changes, comments, and photos.

Validation:

- Hit `/api/me/history` for a technician and verify only their closed tickets appear.
- Hit `/api/me/tickets/<id>/timeline` and confirm status/comment/photo events are ordered ascending.

### Milestone 2 — Mobile UI + offline caching

Goal: Add a “История” UI in `/mobile` with date filters, timeline view, and IndexedDB caching.

Work:

- Update `templates/mobile.html` with a History tab, date inputs, and a timeline panel.
- Update `static/mobile.js` to:
  - Fetch `/api/me/history` with date filters.
  - Fetch `/api/me/tickets/<id>/timeline` for selected items.
  - Cache the history list and timelines in IndexedDB.
  - Display “оффлайн данные” when showing cached results.

Validation:

- Online: open `/mobile`, switch to История, and view closed tickets and timelines.
- Offline: refresh `/mobile` in offline mode and confirm cached history list and timeline render with an offline label.

### Milestone 3 — Tests

Goal: Ensure technician history access control and filtering.

Work:

- Add pytest tests in `tests/`:
  - Technician can access `/api/me/history` and only sees their tickets.
  - Other technicians cannot see those tickets.
  - Technician timeline endpoint returns 403 for чужой ticket.
  - Date range filtering works.
  - Optional: timeline includes comments.

Validation:

- Run `pytest` and capture output.

## End-of-plan change log

- Change: Added ExecPlan for technician history API + mobile UI + offline cache.
  Reason: Multi-file backend + frontend + offline behavior needs an execution plan.
  Date/Author: 2025-03-08 / codex

# Ticket Cancellation Timestamp Fix — ExecPlan

## Purpose / Big Picture

Ensure cancelled tickets store a stable `cancelled_at` timestamp that does not move when `updated_at` changes, and use it for history filtering and “last 4 cancelled” selection.

## Progress

- [x] (2025-03-06 10:00Z) Review Ticket model, history helper, kanban list logic, and tests that depend on cancelled timestamps.
- [x] (2025-03-06 10:15Z) Add `cancelled_at` column, migration/backfill in `ensure_migrations()`, and set it on cancellation without overwriting.
- [x] (2025-03-06 10:30Z) Update history helpers and kanban closed ordering to use `cancelled_at` when available.
- [x] (2025-03-06 10:45Z) Update tests to validate stable cancellation timestamps and history filtering behavior.
- [x] (2025-03-06 11:00Z) Run pytest and capture output.
- [x] (2025-03-06 11:05Z) Document manual validation notes and retrospective.

## Surprises & Discoveries

- None yet.

## Decision Log

- Decision: Use `cancelled_at` with `updated_at` fallback for cancelled tickets to preserve historical ordering while supporting legacy data.
  Rationale: Maintains stable history filtering without breaking existing rows that lack `cancelled_at`.
  Date/Author: 2025-03-06 / codex

## Outcomes & Retrospective

- Outcome (2025-03-06): Cancelled tickets now persist a stable `cancelled_at`, history filtering and “last 4 cancelled” rely on it, and tests cover post-cancel edits. Pytest: 75 passed.

## Plan of Work

### Milestone 1 — Model + migration

Goal: add `Ticket.cancelled_at` with backfill.

Work:

- Update `liftcrm/db.py` Ticket model with `cancelled_at` (nullable DateTime).
- Update `ensure_migrations()` to add missing column and backfill cancelled rows from `updated_at`.

Validation:

- Run migrations on existing DB and confirm cancelled rows have `cancelled_at` populated.

### Milestone 2 — History + kanban behavior

Goal: use the new cancelled timestamp.

Work:

- Update `_ticket_closed_at` and kanban closed ordering to use `cancelled_at`.
- Ensure cancellation sets `cancelled_at` only once.

Validation:

- Confirm cancelled tickets do not move between date ranges after edits.

### Milestone 3 — Tests + validation

Goal: assert stability and filtering.

Work:

- Add tests for stable `cancelled_at` after post-cancel edits.
- Update history/kanban tests to use `cancelled_at`.

Validation:

- Run `pytest` and record output below.

## End-of-plan change log

- Change: Added ExecPlan for cancellation timestamp fix (model/migration/history/tests).
  Reason: Data model + migration + multi-file history changes require an ExecPlan.
  Date/Author: 2025-03-06 / codex

# Ops Kanban History + Layout Fix — ExecPlan

## Purpose / Big Picture

Fix the “Контроль этапов” Kanban layout so cards stay inside columns, limit completed/cancelled columns to the latest four tickets with a “Вся история” link, and add a history page with date range filtering plus API support for admin/dispatcher roles.

## Progress

- [x] (2026-03-05 10:00Z) Review current Kanban template/CSS and backend ticket API feeding the board; document target files and fields.
- [x] (2026-03-05 10:15Z) Update Kanban layout styles to constrain columns and cards; verify visually.
- [x] (2026-03-05 10:45Z) Backend: limit COMPLETED/CANCELLED to last 4 tickets in Kanban API; add “Вся история” links.
- [x] (2026-03-05 11:20Z) Add history page route + template and history API with date range filters and RBAC.
- [x] (2026-03-05 12:05Z) Add pytest coverage for ops limits, history filtering, and RBAC.
- [x] (2026-03-05 12:15Z) Run pytest and capture output.
- [x] (2025-03-08 09:20Z) Rebuild Kanban markup with flex scroll columns, add history links, and align history status labels with STATUS_RU.
- [x] (2025-03-08 09:45Z) Run pytest for ops history changes.
- [x] (2025-03-08 10:00Z) Document manual validation steps and retrospective.
- [x] (2025-03-08 11:10Z) Enforce kanban closed limits via kanban feed and add empty-column collapsing with counts.
- [x] (2025-03-08 11:30Z) Update ops history tests for strict closed column limits.
- [x] (2025-03-08 11:40Z) Run pytest for kanban closed limit + empty column work.

## Surprises & Discoveries

- None during this iteration.

## Decision Log

- Decision: Use `/history` and `/api/tickets/history` for the ops history UI/API to keep URLs short and consistent with existing admin templates.
  Rationale: Keeps navigation simple and avoids nesting under `/ops` while still gated by RBAC.
  Date/Author: 2026-03-05 / codex
- Decision: Reuse STATUS_RU in the history page JS for status labels to keep display consistent with admin UI.
  Rationale: Avoids drift between hardcoded labels and the canonical mapping injected server-side.
  Date/Author: 2025-03-08 / codex
- Decision: Switch the kanban fetch to the kanban-filtered API and drive empty-column UI via counts on the client.
  Rationale: Ensures server-side closed limits are respected while keeping the existing DOM IDs intact.
  Date/Author: 2025-03-08 / codex

## Outcomes & Retrospective

- Outcome (2026-03-05): Kanban layout constrained, completed/cancelled columns limited with history links, and history page/API shipped with tests; manual validation remains.
- Outcome (2025-03-08): Kanban columns now scroll within fixed-width flex columns, history status labels come from STATUS_RU, and ops history tests still pass. Manual validation: open “Контроль этапов” to confirm horizontal scrolling and per-column vertical scroll; open /history with status/date filters.
- Outcome (2025-03-08): Kanban now requests the kanban-limited feed, shows header counts, and collapses empty columns to reduce whitespace; tests cover strict 4-item limits for closed statuses.

## Plan of Work

### Milestone 1 — Kanban layout constraints

Goal: Ensure cards stay within columns and prevent overflow.

Work:

- Update `templates/index.html` and/or `static` CSS for the Kanban layout.
- Apply `display:flex` with `gap` and `overflow-x:auto` for the board, fixed column width, and `min-width: 0` where needed.
- Enforce card width `100%` with `box-sizing: border-box`.

Validation:

- Load the “Контроль этапов” board and confirm cards do not spill into adjacent columns.

### Milestone 2 — Limit completed/cancelled + history links

Goal: Show only the latest four completed/cancelled tickets and add history navigation.

Work:

- Update the backend API feeding the Kanban to limit COMPLETED/CANCELLED to the last four by closure timestamp (fallback updated_at).
- Add a “Вся история” link under completed/cancelled columns pointing to `/history?status=COMPLETED` or `/history?status=CANCELLED`.

Validation:

- Confirm completed/cancelled columns show max 4 cards and render the history link.

### Milestone 3 — History page + API

Goal: Add /history page with date range filtering and supporting API.

Work:

- Add `GET /history` template + route gated to admin/dispatcher.
- Add `GET /api/tickets/history` with status/date range filters, limit/offset, inclusive date_to handling, and closure timestamp fallback.
- Render results list/table with required fields and filters.

Validation:

- Use the history page with date filters and confirm results match the date range and statuses.

### Milestone 4 — Tests + validation

Goal: Add pytest coverage for limits, filtering, and RBAC.

Work:

- Tests for Kanban API limits and history filters.
- Tests for RBAC (technician blocked from /history and /api/tickets/history).

Validation:

- Run `pytest` and record output in this plan.

## End-of-plan change log

- Change: Added ExecPlan for Kanban history + layout fix.
  Reason: Multi-file UI + API + tests work requires an execution plan.
  Date/Author: 2026-03-05 / codex

# Lift History UX Hierarchy — ExecPlan

## Purpose / Big Picture

Rework lift history UX so users navigate from the lifts list → lift detail → history tab → ticket cards → expandable per-ticket logs. The API must return grouped ticket history with computed metrics for consistent rendering.

## Progress

- [x] (2025-03-01 09:10Z) Review current lift history endpoint, templates, and JS flow; inventory required changes for lift detail page + grouped history payload.
- [x] (2025-03-01 10:05Z) Backend: update `/api/lifts/<id>/history` to return grouped ticket histories with metrics and filtering.
- [x] (2025-03-01 10:30Z) Frontend: add lift detail page with history tab + ticket cards + expandable logs; update lift list links.
- [x] (2025-03-01 11:15Z) Tests: update lift history tests for grouped response + permissions + page markup.
- [x] (2025-03-01 11:20Z) Validation: run pytest and capture output.
- [x] (2025-03-01 12:10Z) Fix: count waiting downtime when tickets cancel out of WAITING (metrics + tests).

## Surprises & Discoveries

- None yet.

## Decision Log

- Decision: Keep `/lifts/<id>` as the lift detail entrypoint and replace the standalone history page with a tabbed detail template.
  Rationale: Matches requested navigation while minimizing route churn.
  Date/Author: 2025-03-01 / codex
- Decision: Auto-expand the newest ticket card by default in the history tab.
  Rationale: Highlights the most recent activity without extra clicks while still allowing collapse.
  Date/Author: 2025-03-01 / codex
- Decision: Close WAITING downtime on any non-WAITING status (including CANCELLED) and cap open WAITING at the last event timestamp.
  Rationale: Ensures downtime metrics are stable for cancelled tickets without guessing future timestamps.
  Date/Author: 2025-03-01 / codex

## Outcomes & Retrospective

- Outcome (2025-03-01): Lift detail page now hosts the history tab with ticket cards + expandable logs, and the lift history API groups tickets with metrics; tests updated and passing.
- Outcome (2025-03-01): Downtime metrics now include WAITING segments that end in cancellation, with test coverage for cancelled flow.

## Plan of Work

### Milestone 1 — Backend grouped history + metrics

Goal: serve grouped ticket history with computed metrics and ordering.

Work:

- Update `liftcrm/assets/routes.py` `/api/lifts/<id>/history` to return `{lift, tickets:[{ticket, events, summary}]}`.
- Compute metrics (`response_seconds`, `repair_seconds`, `downtime_seconds`) using ticket timestamps + audit events.
- Keep filtering by date range (`ticket.created_at`) and search (`ticket title/description`, optional event text).
- Keep RBAC unchanged (admin/dispatcher only).

Validation:

- Request `/api/lifts/<id>/history` and confirm grouped payload with metrics keys present (nullable).
- Verify newest activity ticket first.

### Milestone 2 — Lift detail page + history tab

Goal: replace standalone lift history page with lift detail page containing tabs.

Work:

- Create/update `templates/lift_detail.html` with lift header card and tabs (Инфо, История).
- Load a new JS module (e.g., `static/lift_detail.js`) that renders ticket cards and expandable logs.
- Update lift list actions to link to `/lifts/<id>#history` (shortcut) or `/lifts/<id>`.

Validation:

- Load `/lifts/<id>` and ensure lift card and history tab render.
- Expand/collapse details for a ticket and verify only one open at a time.

### Milestone 3 — Tests

Goal: update pytest coverage for new API and page markup.

Work:

- Update `tests/test_lift_history.py` to assert grouped response shape and metrics keys.
- Ensure permissions and ordering tests align with grouped payload.
- Ensure lift detail page includes data-lift-id and history tab markup.

Validation:

- Run `pytest` and confirm passing.

## End-of-plan change log

- Change: Added Lift History UX ExecPlan with milestones and validation steps.
  Reason: Required for multi-file backend + frontend changes.
  Date/Author: 2025-03-01 / codex
- Change: Updated progress, decisions, and outcomes for lift history UX implementation.
  Reason: Track milestone completion and validation status.
  Date/Author: 2025-03-01 / codex
- Change: Added downtime-cancellation fix entries to progress and decisions.
  Reason: Track metrics correction and follow-up validation work.
  Date/Author: 2025-03-01 / codex

## Purpose / Big Picture

We will add a mobile-first “Technician App” that runs on the same domain as the existing LiftCRM web app and can be installed on a phone as a PWA. It must work offline and sync changes when internet returns.

After this work is complete, a technician can:

- Open `/mobile` and see “My tickets” even without internet (after they have opened it once online).
- Open a ticket, change status (Accept → In progress → Waiting → Done), add comments, and add photos while offline.
- See a clear sync indicator: `Synced`, `Pending (N)`, or `Error`.
- Automatically sync pending actions when online again, without losing work.
- Get a safe conflict message if the ticket changed on the server while they were offline (no silent overwrites).

Admin/dispatcher UI must continue to work as before.

## Progress

- [x] (2026-01-19 09:10Z) Read repository structure and confirm where routes, models, and templates live; update “Context and Orientation” with exact paths found.
- [x] (2026-01-19 09:15Z) Confirm current ticket status values and technician-related endpoints; list existing routes and decide what to add.
- [x] (2026-01-19 11:05Z) Add backend support for technician workflow fields (Accept/Waiting) and ticket versioning.
- [x] (2026-01-19 11:10Z) Add technician-scoped endpoints: `/api/me/tickets` and mobile-safe `/api/tickets/<id>` details response.
- [x] (2026-01-19 11:30Z) Add idempotent batch sync endpoint: `POST /api/sync/events` with conflict handling.
- [x] (2026-01-19 12:05Z) Add `/mobile` UI (template + JS) with offline cache, outbox, and sync engine.
- [x] (2026-01-19 12:10Z) Add offline photo queue and upload-on-reconnect flow.
- [x] (2026-01-19 12:45Z) Add automated tests for permissions, idempotency, conflicts, and status transitions.
- [ ] Manual verification: prove offline works using browser offline mode and a real phone install.
- [x] (2026-01-19 12:55Z) Update README with clear technician PWA usage and troubleshooting.
- [x] (2025-02-14 12:20Z) Add `/mobile` login gate + non-technician page, safe post-login redirect, technician auto-redirect from `/`, and tests for the flow.
- [x] (2025-02-14 13:05Z) Harden safe redirect normalization with a strict allowlist and add open-redirect regression tests.
- [x] (2025-02-14 13:30Z) Add admin escape hatch and UI preference cookie to avoid technician redirect traps.
- [x] (2025-02-14 14:05Z) Add technician desktop banner on /admin with a link back to /mobile.
- [x] (2025-02-14 14:20Z) Expand technician banner with guidance text and logout action.
- [x] (2025-02-14 14:35Z) Add human logout redirect to /mobile for technician banner UX.
- [x] (2025-02-15 10:45Z) Unify login UX into a shared `/login` page with role-based redirects and updated tests.
- [x] (2025-02-15 11:30Z) Route all human-facing logout flows to `/login` and ensure protected pages redirect after logout.
- [x] (2025-02-16 10:05Z) Harden desktop navigation rendering by role and add coverage for admin/dispatcher/technician menu visibility.
- [x] (2025-02-16 11:05Z) Guard admin JS initialization and conditionally omit it for technician /admin to avoid map/kanban errors.
- [x] (2025-02-17 09:45Z) Add 2GIS web link button in `/mobile` ticket details and expose lat/lng in ticket payload with tests.
- [x] (2025-02-17 10:05Z) Fix 2GIS coord parsing to avoid null/empty values mapping to 0,0.
- [x] (2025-02-17 10:40Z) Update 2GIS links to route search (lon,lat) and add URL builder test.
- [x] (2025-02-17 11:05Z) Switch 2GIS routing to dgis deeplink with 2gis.kz web fallback and update tests.
- [x] (2025-02-17 11:30Z) Ensure /api/me/tickets and details include lat/lng and add mobile coordinate tests.
- [x] (2025-02-17 12:05Z) Switch 2GIS routing to geo lon/lat URLs and gate debug logging behind a flag.
- [x] (2025-02-20 10:15Z, superseded 2025-03-05) Initially enforce geofence on sync TICKET_ACCEPT and request geolocation only on mobile accept.
- [x] (2025-02-20 11:05Z) Harden sync geofence validation for non-finite technician coordinates.
- [x] (2025-03-05 09:10Z) Move sync geofence enforcement to TICKET_IN_PROGRESS (ACCEPTED → IN_PROGRESS only) and keep accept available without coords.
- [x] (2025-03-05 09:20Z) Update mobile geolocation prompts to request coords only on "В работу" from ACCEPTED and handle out-of-range messaging.
- [x] (2025-03-05 09:50Z) Validation: run pytest and capture output for geofence transition changes.
- [x] (2025-03-05 09:40Z) Localize ticket status labels across admin/dispatcher and mobile technician UI with shared mappings.

## Surprises & Discoveries

Document unexpected behaviors, constraints, or bugs discovered during implementation, with short evidence.

- Observation: No blocking surprises during implementation; backend migrations required a one-time run before ad-hoc DB scripting.
  Evidence: Local scripting failed until `ensure_migrations()` executed.
- Observation: Existing login flow only supported JSON `/api/login`, so a dedicated HTML `/login` handler was added for the `/mobile` form.
  Evidence: `liftcrm/auth/routes.py` only exposed `/api/login` before the change.
- Observation: Unified login required expanding safe redirect allowlist to include `/admin` while preserving strict path validation.
  Evidence: Updated `safe_next_target` to validate parsed path and restrict to `/`, `/admin`, and `/mobile`.
- Observation: Sync event results now return top-level codes for mobile error handling.
  Evidence: `/api/sync/events` returns `{id, ok, code}` per event and includes geofence error metadata.
- Observation: `nan`/`inf` technician coords could trigger a server error during distance formatting.
  Evidence: `int(distance_m)` raised on non-finite values in sync geofence checks.

## Decision Log

Record every decision made while working on this plan.

- Decision: Implement technician UI at `/mobile` as a separate template + JS, rather than modifying the existing admin/dispatcher UI.
  Rationale: Reduces risk of breaking admin UI and keeps mobile code small and purpose-built.
  Date/Author: 2026-01-19 / (fill)

- Decision: Use tickets as the “job” entity for MVP (no new jobs table yet).
  Rationale: Keeps scope small; existing schema already assigns a master to a ticket.
  Date/Author: 2026-01-19 / (fill)

- Decision: Sync endpoint returns `FORBIDDEN` when a technician attempts to update a ticket that is no longer assigned to their master.
  Rationale: Makes reassignment explicit and avoids silent conflicts.
  Date/Author: 2026-01-19 / codex

- Decision: Allow `TICKET_ADD_COMMENT` events on closed tickets, but block status changes once a ticket is `COMPLETED` or `CANCELLED`.
  Rationale: Technicians can still append notes without altering final state.
  Date/Author: 2026-01-19 / codex

- Decision: Superseded by the 2025-03-05 sync geofence change. `/api/sync/events` now enforces the 500 m geofence on `TICKET_IN_PROGRESS` only when moving `ACCEPTED → IN_PROGRESS`; `TICKET_ACCEPT` remains available without coordinates.
  Rationale: Close the mobile bypass at the moment work starts while keeping acceptance and non-arrival outbox actions usable offline.
  Date/Author: 2025-03-05 / codex

- Decision: When a technician uses the legacy `/arrive` endpoint from `ASSIGNED`, the backend auto-records `accepted_at` and transitions through `ACCEPTED` for backward compatibility.
  Rationale: Avoid breaking existing technician workflows while introducing the ACCEPTED state.
  Date/Author: 2026-01-19 / codex
- Decision: Implemented a small HTML `/login` handler with a strict `next` allowlist (paths starting with `/`) for mobile login redirects.
  Rationale: Meets `/mobile` UX without opening open-redirect vulnerabilities.
  Date/Author: 2025-02-14 / codex
- Decision: Normalize and allowlist post-login redirect targets to only `/` and `/mobile`.
  Rationale: Prevent encoded/backslash open-redirect bypasses while keeping mobile UX intact.
  Date/Author: 2025-02-14 / codex
- Decision: Add `/admin` route with an optional `ui` preference cookie to let technicians reach the desktop UI without disabling the default `/` redirect.
  Rationale: Preserve default mobile-first routing while providing a reliable escape hatch.
  Date/Author: 2025-02-14 / codex
- Decision: Show a technician-only banner on `/admin` to clarify limited desktop access and offer a one-click return to `/mobile`.
  Rationale: Reduce confusion when technicians open the desktop UI for navigation/testing.
  Date/Author: 2025-02-14 / codex
- Decision: Add guidance text and a logout action to the technician banner using existing `/api/logout`.
  Rationale: Provide clearer next steps without changing permissions.
  Date/Author: 2025-02-14 / codex
- Decision: Add a POST `/logout` handler that reuses logout behavior and redirects to `/mobile`.
  Rationale: Avoid showing raw JSON after logout while keeping API logout intact.
  Date/Author: 2025-02-14 / codex
- Decision: Route both desktop and mobile login through a shared `/login` template and apply role-based redirects after form login.
  Rationale: Ensures consistent UX while preventing technicians from landing in admin UI via `next`.
  Date/Author: 2025-02-15 / codex
- Decision: Redirect human-facing logout to `/login` to keep users in the unified entrypoint.
  Rationale: Avoids dumping users on the mobile shell and matches the new shared login UX.
  Date/Author: 2025-02-15 / codex
- Decision: Use `/logout` as the only human-facing logout target and update desktop UI to avoid `/api/logout`.
  Rationale: Prevents raw JSON responses and ensures the browser navigates back to the unified login page.
  Date/Author: 2025-02-15 / codex
- Decision: Render desktop navigation and admin-only sections server-side based on role to keep unauthorized items out of the DOM.
  Rationale: Ensures UI hardening aligns with security expectations and role-specific navigation tests.
  Date/Author: 2025-02-16 / codex
- Decision: Skip loading admin JS for technician /admin and add defensive guards around map init/kanban polling.
  Rationale: Prevents runtime errors when technician banner-only HTML omits admin DOM nodes.
  Date/Author: 2025-02-16 / codex
- Decision: Use a 2GIS web URL with `m=<lng,lat>` plus optional `query` hint, and open it in the same tab from the PWA.
  Rationale: Keeps navigation consistent in the PWA while allowing the OS to offer “Open in app” on mobile.
  Date/Author: 2025-02-17 / codex
- Decision: Superseded by the 2025-03-05 sync geofence change. Do not require coordinates for `TICKET_ACCEPT`; request and validate technician coordinates for `TICKET_IN_PROGRESS` only when the previous status is `ACCEPTED`.
  Rationale: Acceptance should work without GPS, but starting work must prove the technician is within 500 m of the object.
  Date/Author: 2025-03-05 / codex
- Decision: Treat non-finite or out-of-range technician coordinates as `NO_TECH_COORDS`.
  Rationale: Avoid server errors and keep geofence failures explicit for the mobile client.
  Date/Author: 2025-02-20 / codex
- Decision: Centralize Russian status labels in a Jinja context mapping plus per-UI JS maps with fallback to raw codes.
  Rationale: Keep API/DB enums unchanged while ensuring consistent localized presentation across desktop and mobile.
  Date/Author: 2025-03-05 / codex

(Keep adding entries as decisions occur.)

## Outcomes & Retrospective

At major milestones or completion, summarize what was achieved, what remains, and lessons learned. Compare outcomes to the “Purpose / Big Picture” section.

- Outcome (2026-01-19): Delivered backend versioning + sync endpoint, mobile PWA UI with offline cache/outbox/photo queue, and added automated sync tests + README docs. Manual offline verification on a real device remains.
- Outcome (2025-02-14): Added `/mobile` login UX gating, technician auto-redirect from `/`, and safe redirect handling with automated coverage.
- Outcome (2025-02-15): Unified `/login` UI for desktop and mobile with role-based redirects, updated unauthenticated redirects, and expanded test coverage.
- Outcome (2025-02-15): Updated logout UX to always return users to `/login` and added coverage for logout redirects.
- Outcome (2025-02-16): Restricted desktop navigation and admin-only sections by role, with tests validating role-specific HTML output.
- Outcome (2025-02-16): Prevented admin JS from running on technician banner-only pages and added tests for script omission.
- Outcome (2025-02-17): Added a 2GIS web button in mobile ticket details and ensured ticket payloads surface lat/lng for link generation.
- Outcome (2025-02-17): Hardened 2GIS URL coord parsing to require non-empty, in-range coordinates before using `m=` links.
- Outcome (2025-02-17): Switched 2GIS URLs to routeSearch (lon,lat) destinations and added a URL builder test.
- Outcome (2025-02-17): Added dgis deeplink routing with a 2gis.kz fallback and aligned URL builder tests.
- Outcome (2025-02-17): Verified mobile endpoints return lat/lng values and added coverage for ticket list/detail payloads.
- Outcome (2025-02-17): Updated 2GIS links to /almaty/geo lon,lat URLs and gated debug output.
- Outcome (2025-02-20, superseded 2025-03-05): Initially added geofence enforcement to sync accept events; current behavior moved that check to `TICKET_IN_PROGRESS` for `ACCEPTED → IN_PROGRESS`.
- Outcome (2025-02-20): Hardened sync geofence checks against non-finite coordinates with explicit error codes.
- Outcome (2025-03-05): Moved mobile sync geofence enforcement from accept to `TICKET_IN_PROGRESS` for the `ACCEPTED → IN_PROGRESS` transition; accepting a ticket no longer requires coordinates.
- Outcome (2025-03-05): Desktop and mobile UIs now display Russian status labels consistently while preserving enum codes in the backend.

## Context and Orientation

This repo is a Flask application with SQLAlchemy models and server-rendered templates. Confirmed locations:

- `app.py` starts the Flask app.
- `liftcrm/` contains the backend package:
  - `liftcrm/db.py` defines SQLAlchemy models (Ticket, User, Master, Attachment, Asset) and a sqlite migration helper `ensure_migrations()`.
  - `liftcrm/auth/routes.py` provides `/api/login`, `/api/logout`, and `/api/me`.
  - `liftcrm/tickets/routes.py` contains ticket CRUD/status endpoints and attachment upload (`/api/tickets/<id>/upload`), plus `/uploads/<filename>`.
  - `liftcrm/tickets/service.py` contains status transition validation (`validate_status_transition`) and other ticket logic.
- `templates/index.html` is the admin/dispatcher UI.
- `static/` currently holds PWA assets (`manifest.webmanifest`, `sw.js`, icons).

Current ticket status values: `NEW`, `ASSIGNED`, `ACCEPTED`, `IN_PROGRESS`, `WAITING`, `COMPLETED`, `CANCELLED`. Technician-scoped mobile endpoints now include `GET /api/me/tickets`, `GET /api/me/history`, `GET /api/me/tickets/<id>/timeline`, and `POST /api/sync/events`.

Key terms used in this plan (plain language):

- PWA: a website that can be installed to the phone home screen and can run offline.
- Service worker: a small script that can cache app files and serve them when offline.
- IndexedDB: a browser local database we use to store cached tickets and the offline queue.
- Outbox: the local queue of actions the technician performed while offline (status changes, comments, etc.).
- Sync: sending outbox actions to the server when internet is back.
- Conflict: when the ticket has changed on the server since the technician last saw it; we must not overwrite newer server state silently.

## Plan of Work

We will implement this in milestones. Each milestone must be independently verifiable.

### Milestone 1 — Backend readiness: technician workflow + versioning

Goal: ensure the backend can safely support offline sync with conflict detection.

Work:

- Confirm current ticket status values in the Ticket model and existing code paths.
- Add or confirm technician statuses:
  - `ACCEPTED` (technician confirmed they take it)
  - `WAITING` (paused with a reason)
  Keep existing statuses intact. Do not rename existing values unless absolutely necessary.
- Add ticket versioning:
  - Add `Ticket.version` integer with default `1`.
  - Increment version on every change that matters to technician view (status change, waiting reason, completion, cancellation, reassignment, edits).
- Add minimal technician workflow fields if missing:
  - `accepted_at` datetime nullable
  - `waiting_at` datetime nullable
  - `waiting_reason` text nullable
  If the repo already has equivalent fields, reuse them and document the mapping here.
- Add strict transition rules for technician actions:
  - Only tickets assigned to the technician’s master can be changed by that technician.
  - Completed/cancelled tickets reject further status changes (comments can be allowed or denied; decide and record).
  - Waiting requires a reason.

Proof:

- Start server, login as a technician, and fetch their assigned tickets with `version` included.
- Change a ticket status via existing endpoints and verify `version` increments.

### Milestone 2 — Technician data endpoints

Goal: give the mobile app stable endpoints for list and detail.

Work:

- Add `GET /api/me/tickets`:
  - Requires login.
  - Requires role TECHNICIAN.
  - Finds technician master id from current user (typically `current_user.master_id`).
  - Returns only tickets assigned to that master and not archived.
  - Support optional query params:
    - `include_closed=1` (include completed/cancelled)
- Ensure `GET /api/tickets/<id>` returns details suitable for mobile:
  - Must include `version`, status, address/object, description, due/SLA (if present), timestamps, waiting fields, and attachments list if applicable.
  - Technician must only access tickets assigned to them. Admin/dispatcher can access any.

Proof:

- Request `/api/me/tickets` and confirm it returns only assigned tickets.
- Request `/api/tickets/<id>` as technician for an assigned ticket and for an unassigned ticket; confirm assigned works and unassigned is forbidden.

### Milestone 3 — Batch sync endpoint with idempotency + conflict handling

Goal: allow the mobile app to send offline actions safely.

Work:

- Add a new table to prevent double-applying the same event when the phone retries:
  - `applied_events` with at least:
    - `event_id` (unique string)
    - `user_id`
    - `ticket_id`
    - `applied_at`
- Add `POST /api/sync/events`:
  - Requires login and TECHNICIAN role.
  - Accepts a list of events. Each event has:
    - `id` (uuid string; used for idempotency)
    - `type` (one of a defined set)
    - `ticket_id`
    - `expected_version` (integer)
    - `created_at` (timestamp from device)
    - `payload` (type-specific data)
  - For each event, server returns a per-event result: ok or error.
- Event types (MVP):
  - `TICKET_ACCEPT`
  - `TICKET_IN_PROGRESS`
  - `TICKET_WAITING`
  - `TICKET_DONE`
  - `TICKET_ADD_COMMENT`
- Conflict rule:
  - If `expected_version` does not match current `ticket.version`, return a conflict for that event with current server state (at least `ticket_id`, `server_version`, `server_status`).
  - Do not apply the event when conflict occurs.
- Ownership rule:
  - Technician can only sync events for tickets assigned to their master id.
  - If ticket is reassigned away while offline, return `FORBIDDEN` (or `CONFLICT` with server state; choose one and record decision).
- Idempotency rule:
  - If `event_id` already exists in `applied_events`, do not apply again; return ok with current server version/status.

Keep server-side status transition logic in one place. If there is a `liftcrm/tickets/service.py`, implement functions there and call them from both existing endpoints and the sync handler.

Proof:

- Send one accept event and see status updated.
- Send the same event again and confirm it is not applied twice.
- Modify ticket on server (e.g., by dispatcher), then send event with old expected_version and confirm conflict response.

### Milestone 4 — Mobile UI at `/mobile` with offline cache + outbox

Goal: deliver a technician UI that works offline and queues actions.

Work:

- Add new route `/mobile` that serves `templates/mobile.html`.
  - If not logged in: redirect to login page (or `/`).
  - If logged in but not TECHNICIAN: show a clear “Not a technician account” page or redirect to admin UI.
- Add `static/mobile.js` and load it only on `mobile.html`.
- Implement UI:
  - My Tickets list.
  - Ticket details view.
  - Action buttons: Accept, In progress, Waiting (reason), Done (final comment and close reason).
  - Comments display (optional MVP) and “Add comment”.
  - Sync status banner showing: Online/Offline, Pending count, last sync time, “Sync now”.
- Implement local storage using IndexedDB (use a minimal helper library only if needed):
  - `tickets_list_cache` store: cached list for offline view.
  - `tickets_cache` store: cached ticket details.
  - `outbox_events` store: queued events.
- Offline behavior:
  - On first online load, cache list and ticket details.
  - If offline, render from cache.
  - When user performs an action while offline:
    - Immediately update UI (optimistic).
    - Insert an outbox event with `expected_version` from cached ticket.
    - Increase “Pending count”.
  - Sync behavior:
    - Trigger sync on app start, when `navigator.onLine` becomes true, on “Sync now”, and periodically while online if pending exists.
    - Batch send pending events to `/api/sync/events`.
    - For `TICKET_IN_PROGRESS` from `ACCEPTED`, include technician coordinates and expect the server to enforce the 500 m geofence after version validation.
    - On ok: mark event sent, update local ticket status/version from server response, reduce pending count.
  - On conflict: mark event failed, show a message on that ticket “Needs refresh”, fetch latest ticket details, and require user to re-apply action if still needed.
  - On forbidden: mark failed and show “Ticket reassigned / access removed”.

Proof:

- Online: open `/mobile`, see tickets, open ticket.
- Offline: toggle browser offline mode, refresh `/mobile`, still see cached list.
- Offline: change status; see pending indicator.
- Online: restore connection; pending actions sync and clear.

### Milestone 5 — Offline photo queue + upload on reconnect

Goal: allow technician to capture photos offline and upload later reliably.

Work:

- Add photo capture UI in ticket details:
  - Use file input with `capture` attribute for mobile.
- Store selected photos as blobs in IndexedDB store `outbox_photos` with `ticket_id`.
- Upload strategy:
  - After events sync (or in parallel), upload photos using existing attachment endpoint.
  - If no suitable endpoint exists, add:
    - `POST /api/tickets/<id>/attachments` multipart form upload
  - After successful upload, update local cache by refetching ticket details or appending the returned attachment metadata.
- Error strategy:
  - On upload failure, keep photo queued with retry count and show error state in UI.
  - Allow manual retry via “Sync now”.

Proof:

- Offline: add a photo; it appears as queued/pending.
- Online: photo uploads and appears in server attachments for that ticket.

### Milestone 6 — Tests, docs, and operator playbook

Goal: prove correctness and make it maintainable.

Work:

- Add backend tests (use the repo’s existing test framework; if none exists, add pytest):
  - Technician cannot sync events for a ticket not assigned to them.
  - Idempotency: same event id applied twice results in one real state change.
  - Conflict: mismatched expected_version returns conflict and does not apply event.
  - Happy path: accept → in_progress → waiting → done applies in order.
- Add documentation:
  - README section “Technician PWA (/mobile)”.
  - How to install on Android/iOS.
  - Offline limitations (especially iOS: background sync may require the app to be open).
  - Troubleshooting: “pending stuck”, “conflict”, “reset offline cache”.

Proof:

- Run tests and confirm all pass.
- Follow README steps to install and verify offline.

## Concrete Steps

Update this section as implementation proceeds, but start with a working baseline.

1) Set up and run server.

  In repo root:

    python -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    python app.py

  Expected:
  - Flask server starts and prints the local URL.

2) Locate key files.

  - Open `liftcrm/db.py` and identify the Ticket model.
  - Open `liftcrm/auth/routes.py` and find current user endpoint (often `/api/me`).
  - Open `liftcrm/tickets/routes.py` and find existing ticket status endpoints.

3) Implement Milestone 1 changes.

  - Add ticket columns and safe migrations (do not break existing DBs).
  - Ensure version increments on relevant changes.

4) Implement Milestone 2 endpoints.

  - Add `/api/me/tickets`.
  - Ensure `/api/tickets/<id>` is technician-safe.

5) Implement Milestone 3 sync endpoint.

  - Add `applied_events` table + model.
  - Add `/api/sync/events`.

6) Implement Milestone 4 `/mobile` UI.

  - Create `templates/mobile.html`.
  - Create `static/mobile.js`.
  - Add `/mobile` route and role gating.

7) Implement Milestone 5 photos.

  - Add offline photo queue and upload-on-reconnect.

8) Tests and docs.

  - Add tests and update README.

## Validation and Acceptance

This feature is accepted only if a human can verify all of the following behavior:

1) Technician list offline:

- Login as technician, open `/mobile` online, confirm tickets appear.
- Switch browser to offline mode and refresh `/mobile`.
- Tickets still appear (from cache).

2) Offline actions queue:

- While offline, change a ticket status to Waiting and set a reason.
- UI updates immediately and shows pending count > 0.
- Go online; pending count returns to 0 and server ticket status becomes WAITING.

3) Offline completion:

- While offline, set Done with a required comment.
- Go online; server shows COMPLETED and comment persisted.

4) Photo offline:

- While offline, add a photo to the ticket.
- Go online; photo uploads and appears in ticket attachments.

5) Conflict safety:

- While technician is offline, dispatcher changes the ticket on server (reassign or cancel).
- Technician goes online and syncs.
- App shows conflict/forbidden clearly and does not overwrite server state silently.

6) Permission safety:

- Technician cannot read or update tickets not assigned to them via any of:
  - `/api/me/tickets`
  - `/api/tickets/<id>`
  - `/api/sync/events`

## Idempotence and Recovery

- Database migrations must be safe to run multiple times (no crashes if columns already exist).
- Sync events must be idempotent via `event_id`. Retrying must not duplicate state changes.
- Provide a “Reset offline data” action in `/mobile` (simple button) that:
  - clears IndexedDB stores (`tickets_cache`, `tickets_list_cache`, `outbox_events`, `outbox_photos`)
  - reloads the page.
- If something breaks in mobile UI, admin/dispatcher UI must remain unaffected.

## Artifacts and Notes

Add short evidence snippets here during implementation. Keep them concise.

Examples to record during work (indent them as plain text):

  - A sample `/api/sync/events` request and response proving idempotency.
  - A log line indicating an event was already applied.
  - A screenshot description: “offline refresh shows cached tickets”.

  - Tests: `pytest` (37 passed).

## Interfaces and Dependencies

Be prescriptive:

- Keep the mobile UI minimal: one new template (`templates/mobile.html`) and one new JS file (`static/mobile.js`).
- Use existing session login. Do not introduce token auth for MVP unless the repo already uses it.
- Use IndexedDB for offline storage. If a helper library is needed, choose one tiny dependency or a small local helper module, and document it in README.
- Centralize ticket status logic in one backend place (service functions) so sync and direct endpoints behave identically.

## Notes for Future (not in MVP scope)

Record ideas but do not implement them unless explicitly requested:

- Push notifications.
- Background sync that runs while the PWA is closed (not reliable on iOS).
- A separate “jobs” entity distinct from tickets.
- Multi-tenant SaaS changes.

## End-of-plan change log

When you edit this plan during implementation, append a short note here:

- Change: ...
  Reason: ...
  Date/Author: ...
- Change: Updated progress, decisions, outcomes, and notes for technician PWA backend + mobile implementation.
  Reason: Track completed milestones and decisions made during implementation.
  Date/Author: 2026-01-19 / codex
- Change: Added progress/decision/outcome notes for `/mobile` login UX + safe redirects and tests.
  Reason: Track the focused routing/login UX improvements.
  Date/Author: 2025-02-14 / codex
- Change: Documented unified login UX and role-based redirect updates.
  Reason: Track shared `/login` routing changes and redirect policy updates.
  Date/Author: 2025-02-15 / codex
- Change: Recorded logout UX redirect fix to `/login`.
  Reason: Track the human-facing logout navigation and redirect verification updates.
  Date/Author: 2025-02-15 / codex
- Change: Logged role-based desktop navigation rendering and tests.
  Reason: Track UI hardening to keep unauthorized nav items out of the DOM.
  Date/Author: 2025-02-16 / codex
- Change: Recorded technician banner JS guards and conditional admin script inclusion.
  Reason: Track regression fix for admin JS running without required DOM.
  Date/Author: 2025-02-16 / codex
- Change: Documented 2GIS button addition, payload tweaks, and tests.
  Reason: Track mobile ticket detail navigation enhancement.
  Date/Author: 2025-02-17 / codex
- Change: Logged fix for 2GIS coord parsing to avoid null/empty values mapping to 0,0.
  Reason: Ensure address fallback when coords are missing or invalid.
  Date/Author: 2025-02-17 / codex
- Change: Noted 2GIS routeSearch URL switch and added URL builder test coverage.
  Reason: Ensure navigation links set a destination and enforce lon,lat ordering.
  Date/Author: 2025-02-17 / codex
- Change: Recorded dgis deeplink routing + kz fallback update and test adjustments.
  Reason: Ensure app deeplink opens navigation and web fallback works in Kazakhstan.
  Date/Author: 2025-02-17 / codex
- Change: Recorded mobile endpoint lat/lng payload check and added tests.
  Reason: Ensure /mobile has coordinates for 2GIS routing.
  Date/Author: 2025-02-17 / codex
- Change: Logged switch to 2GIS geo URLs and debug flag for URL logging.
  Reason: Ensure destination pins render reliably with lon,lat ordering.
  Date/Author: 2025-02-17 / codex
- Change: Updated sync geofence enforcement notes. The February accept-time check was superseded by the March behavior: `TICKET_ACCEPT` has no coordinate requirement, and `TICKET_IN_PROGRESS` enforces geofence only from `ACCEPTED`.
  Reason: Track the security fix across backend and mobile UI without preserving stale accept-time wording.
  Date/Author: 2025-02-20 / codex
- Change: Logged non-finite coordinate validation for sync geofence.
  Reason: Track the added validation and error behavior for invalid coordinates.
  Date/Author: 2025-02-20 / codex
- Change: Documented localized status labels for admin/dispatcher and mobile technician views.
  Reason: Track UI localization work and shared status mapping decisions.
  Date/Author: 2025-03-05 / codex
