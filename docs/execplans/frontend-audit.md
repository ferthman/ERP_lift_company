# Frontend Audit and Stabilization — ExecPlan

This ExecPlan is the source of truth for the frontend audit and stabilization pass requested on 2026-07-09. Keep Progress, Surprises & Discoveries, Decision Log, and Outcomes & Retrospective updated as work proceeds.

## Purpose / Big Picture

Audit the current Flask/Jinja/Tailwind/vanilla-JS frontend for the admin, dispatcher, technician mobile PWA, and map workflows. Fix the highest-impact confirmed issues without changing backend data contracts unnecessarily. The goal is not a visual redesign; it is safer daily operation on desktop and mobile: usable navigation, reliable map behavior, clear technician actions, and regression coverage for the fixed behavior.

## Progress

- [x] (2026-07-09 16:49 +05) Inspect repository structure, AGENTS.md requirements, frontend templates/static files, relevant route contracts, and existing tests.
- [x] (2026-07-09 17:05 +05) Audit admin/dispatcher UI in code and HTTP/static paths: navigation, tables, modals, map tab, ticket deep links, and responsive behavior.
- [x] (2026-07-09 17:05 +05) Audit technician mobile PWA in code and HTTP/static paths: header actions, ticket list/detail, offline/outbox indicators, history, 2GIS link, and status controls.
- [x] (2026-07-09 17:05 +05) Audit map behavior in code: object markers, ticket focus from table, fullscreen relocation, resize invalidation, search overlay, and missing-coordinate edge cases.
- [x] (2026-07-09 16:59 +05) Implement focused fixes for confirmed high-impact issues.
- [x] (2026-07-09 16:59 +05) Add or update regression tests for the changed frontend-facing behavior.
- [x] (2026-07-09 16:59 +05) Run focused tests, full test suite where practical, JS syntax checks, and record exact validation results.

## Surprises & Discoveries

- Observation: The main admin/dispatcher UI is a single `templates/index.html` file of 3386 lines containing template markup, CSS, and most JavaScript.
  Evidence: `find templates static -maxdepth 1 -type f -print0 | xargs -0 wc -l`.
- Observation: The technician PWA is separate (`templates/mobile.html`, `static/mobile.js`, `static/mobile-2gis.js`) and already has offline queue tests.
  Evidence: `tests/test_pwa_offline_reliability.py`, `tests/test_mobile_2gis_url_builder.py`, and `tests/test_sync_events.py`.
- Observation: Returning from `WAITING` to `IN_PROGRESS` intentionally does not require new geolocation and preserves the original arrival coordinates.
  Evidence: `tests/test_sync_events.py::test_resume_from_waiting_preserves_arrived_at`.
- Observation: Browser automation could not start with bundled Playwright because the Chromium executable is not installed; system Chrome also failed inside sandbox with `SIGABRT/EPERM`. The local Flask server required escalation to bind to localhost.
  Evidence: node Playwright launch reported missing `chromium_headless_shell-1200`; `channel: "chrome"` launch reported `Target page, context or browser has been closed` and `SIGABRT/EPERM`; `venv/bin/flask --app app run --host 127.0.0.1 --port 5001` succeeded only with escalation.
- Observation: Admin/dispatcher header is a single row with a non-wrapping nav and login controls, so the 7-button admin nav can overflow on phone-width screens.
  Evidence: `templates/index.html` header uses `flex items-center justify-between` and `nav class="flex items-center gap-2"`.
- Observation: Admin JS assumes Leaflet loaded from CDN. If `window.L` is missing, `initCreateMap()` throws before the rest of the admin script finishes, so tickets, filters, and access flows can break even when the user is not using the map.
  Evidence: `templates/index.html` calls `initCreateMap()` during init and that function calls `L.map(...)` without a guard.
- Observation: Non-ticket admin modals use fixed centered cards without a max-height/overflow policy, so forms like the asset modal can be partly unreachable on mobile.
  Evidence: modal cards use `w-[90vw] max-w-*` classes without `max-h`/`overflow-y-auto`.
- Observation: Technician PWA reset clears IndexedDB caches, queued events, and queued photos immediately, with no confirmation.
  Evidence: `static/mobile.js::resetOffline()` calls `clear()` on every store and reloads.
- Observation: Access management tables render `username`, master name, phone, and linked username directly into `innerHTML`.
  Evidence: `templates/index.html::renderUsersTable()` and `renderMastersTable()` interpolate `u.username`, `masterLabel`, `m.name`, `m.phone`, and `m.username` without `escapeHtml`.

## Decision Log

- Decision: Keep fixes tightly scoped to frontend reliability and UX defects found during audit rather than splitting the monolithic template in this pass.
  Rationale: A large template/module refactor would be high blast-radius and hard to validate in the same audit pass.
  Date/Author: 2026-07-09 / codex
- Decision: Use Playwright CLI browser checks in addition to pytest.
  Rationale: Responsive layout, map rendering, fullscreen relocation, and external-link buttons cannot be validated by Python tests alone.
  Date/Author: 2026-07-09 / codex
- Decision: Treat server contracts as stable unless a frontend bug cannot be fixed safely without changing them.
  Rationale: The user requested a frontend audit; backend changes should be minimal and covered by existing API tests.
  Date/Author: 2026-07-09 / codex
- Decision: Proceed with static/HTTP-backed audit plus source regression tests when Playwright browser launch is blocked.
  Rationale: The confirmed issues are visible in source and existing tests already use source assertions for frontend safety; waiting on browser installation would block useful fixes.
  Date/Author: 2026-07-09 / codex

## Outcomes & Retrospective

- Outcome (2026-07-09): Admin/dispatcher header now stacks and scrolls nav controls on narrow screens instead of forcing the whole page wide. Non-fullscreen modals now have max-height and vertical scrolling so long forms remain reachable on mobile.
- Outcome (2026-07-09): Admin map code now guards missing Leaflet and failed assets/tickets fetches. If the map library or assets API is unavailable, the UI shows a Russian status message instead of crashing the whole admin script.
- Outcome (2026-07-09): Technician PWA status buttons now have visible disabled styling. Offline reset now asks for confirmation and explicitly warns when queued events/photos will be deleted. `uid()` now uses `globalThis.crypto` to avoid a ReferenceError on runtimes without a global `crypto` binding.
- Outcome (2026-07-09): Access-management tables now escape usernames, master names, phones, and linked usernames before inserting HTML.
- Validation (2026-07-09): `node --check static/mobile.js` passed; rendered admin inline scripts were extracted and checked with `node --check` (`checked 2 inline scripts`); focused tests passed with `28 passed in 2.09s`; full suite passed with `160 passed, 6 subtests passed in 24.86s`.
- Residual risk: A real browser viewport/map visual pass was not completed because Playwright Chromium is not installed and system Chrome launch is blocked by sandbox/GUI permissions. Source checks, rendered JS syntax checks, Flask render tests, and full pytest passed.

## Context and Orientation

- Backend app factory: `liftcrm/__init__.py`.
- Main admin/dispatcher page: `templates/index.html`.
- Technician PWA page: `templates/mobile.html`.
- Technician PWA logic: `static/mobile.js` and `static/mobile-2gis.js`.
- Service worker: `static/sw.js`.
- Lift/detail/history pages: `templates/lift_detail.html`, `static/lift_detail.js`, `templates/history.html`, `static/history.js`.
- Relevant tests: `tests/test_desktop_nav_rbac.py`, `tests/test_mobile_2gis_url_builder.py`, `tests/test_mobile_ticket_coords.py`, `tests/test_pwa_offline_reliability.py`, `tests/test_sync_events.py`, and map/assets tests.

## Plan of Work

### Milestone 1 — Browser-backed audit

Goal: Produce a repository-specific list of confirmed breakages, likely breakages, and safe improvements for admin/dispatcher, technician mobile, and map workflows.

Work:

- Start the Flask app locally from this checkout.
- Log in as admin, dispatcher, and technician using seeded/test accounts.
- Check admin/dispatcher at desktop and mobile widths:
  - Header/nav wrapping and reachable tabs.
  - Tickets table, filters, ticket modal, cancel modal, and assignment controls.
  - Assets, maintenance, admin metrics, access pages where available by role.
- Check technician `/mobile` at phone width:
  - Header actions and sync controls.
  - Ticket list/detail layout.
  - Status action availability and validation.
  - History and offline/outbox visible states where possible.
  - 2GIS URL construction and button behavior.
- Check map:
  - Initial render on hidden-to-visible tab transition.
  - Search overlay and suggestions.
  - Fullscreen open/close and Leaflet resize.
  - Ticket focus from tickets table to objects map.
  - Behavior when no assets or no valid coordinates exist.

Validation:

- Record findings in this plan with evidence.
- Keep browser screenshots or Playwright observations in the final summary when useful.

### Milestone 2 — Focused fixes

Goal: Fix confirmed high-impact frontend issues without broad refactors.

Candidate work, subject to browser audit confirmation:

- Make admin/dispatcher header navigation usable on narrow screens.
- Make repeated action button groups and map controls wrap predictably without horizontal clipping.
- Harden map loading against failed `/api/assets` or `/api/tickets` fetches and no-coordinate datasets.
- Prevent map fullscreen/tab interactions from leaving the map shell detached or blank.
- Improve technician mobile action affordances, especially disabled state clarity and compact header controls.
- Keep copy/operator guidance concise and in existing Russian UI style.

Validation:

- Repeat browser checks for each fixed workflow.
- Add focused regression tests where static/source assertions can prevent relapse.

### Milestone 3 — Tests, docs, and closure

Goal: Prove the frontend remains stable and document residual risks.

Work:

- Run focused tests related to changed files.
- Run full `venv/bin/python -m pytest -q` if feasible.
- Update this plan with exact test commands and results.
- Add README/RUNBOOK notes only if operator behavior changes.
- Commit small, reviewable changes after validation.

Validation:

- A human can reproduce the checked admin/dispatcher/mobile/map flows from the Validation section.
- Tests pass or failures are documented with evidence and next action.

## Validation

Commands run:

- `node --check static/mobile.js`
- Render `/admin` through Flask test client after admin login, extract inline `<script>` blocks, and run `node --check` on each extracted script. Result: `checked 2 inline scripts`.
- `venv/bin/python -m pytest tests/test_frontend_resilience.py tests/test_pwa_offline_reliability.py tests/test_xss_rendering_guards.py tests/test_desktop_nav_rbac.py tests/test_mobile_login_flow.py tests/test_mobile_2gis_url_builder.py -q` → `28 passed in 2.09s`.
- `venv/bin/python -m pytest -q` → `160 passed, 6 subtests passed in 24.86s`.

Manual reproduction steps for a human browser check:

- Start app: `venv/bin/flask --app app run --host 127.0.0.1 --port 5001`.
- Admin narrow viewport: log in as `admin` / `admin123`, open `/admin`, narrow to phone width, confirm nav scrolls horizontally within the header and page content is still reachable.
- Dispatcher: log in as `dispatcher` / `disp123`, open `/admin`, confirm no admin-only tabs are visible and shared tabs remain usable.
- Technician mobile: log in as `master1` / `master1123`, open `/mobile`, select a ticket, confirm disabled status buttons are visibly disabled and “Сброс офлайн-данных” asks for confirmation before clearing local data.
- Map: open `/admin?tab=objects`, confirm map state message appears if assets have no coordinates or if Leaflet is blocked; otherwise confirm markers/search/fullscreen still work.

## End-of-plan Change Log

- Change: Created frontend audit ExecPlan.
  Reason: The task spans multiple frontend surfaces, roles, responsive layouts, maps, and likely tests; `AGENTS.md` requires an ExecPlan.
  Date/Author: 2026-07-09 / codex
- Change: Completed focused frontend stabilization pass and recorded validation.
  Reason: Track audited issues, implemented fixes, test coverage, and the remaining browser-automation limitation.
  Date/Author: 2026-07-09 / codex
