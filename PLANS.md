# Technician Mobile App (PWA + Offline Outbox + Sync) — ExecPlan

This PLANS.md file is a living execution plan. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

Treat the reader as a complete beginner to this repository. The only context they have is the working tree and this file. Do not assume any prior conversation.

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

## Surprises & Discoveries

Document unexpected behaviors, constraints, or bugs discovered during implementation, with short evidence.

- Observation: No blocking surprises during implementation; backend migrations required a one-time run before ad-hoc DB scripting.
  Evidence: Local scripting failed until `ensure_migrations()` executed.

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

- Decision: Keep geofence enforcement only on the existing `/api/tickets/<id>/arrive` and `/complete` endpoints; sync events do not enforce geofence.
  Rationale: Offline sync cannot reliably depend on GPS and should prioritize data consistency over location checks.
  Date/Author: 2026-01-19 / codex

- Decision: When a technician uses the legacy `/arrive` endpoint from `ASSIGNED`, the backend auto-records `accepted_at` and transitions through `ACCEPTED` for backward compatibility.
  Rationale: Avoid breaking existing technician workflows while introducing the ACCEPTED state.
  Date/Author: 2026-01-19 / codex

(Keep adding entries as decisions occur.)

## Outcomes & Retrospective

At major milestones or completion, summarize what was achieved, what remains, and lessons learned. Compare outcomes to the “Purpose / Big Picture” section.

- Outcome (2026-01-19): Delivered backend versioning + sync endpoint, mobile PWA UI with offline cache/outbox/photo queue, and added automated sync tests + README docs. Manual offline verification on a real device remains.

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

Current ticket status values: `NEW`, `ASSIGNED`, `IN_PROGRESS`, `COMPLETED`, `CANCELLED`. Existing endpoints for technician scope are limited to `/api/tickets` filtering; there is no `/api/me/tickets` yet.

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
