# Lift History (per-elevator timeline) — ExecPlan

This ExecPlan is the source of truth for the Lift History feature. Update Progress, Decision Log, Surprises & Discoveries, and Outcomes & Retrospective as work proceeds.

## Purpose / Big Picture

Add a lift-specific history view reachable from the “Лифты” list. Authorized users (ADMIN, DISPATCHER) can open a lift and see a timeline of ticket activity, comments, and related events. Technicians should not have access to this desktop page.

## Progress

- [x] (2025-02-16 13:20Z) Review existing lift/ticket models, identify lift ↔ ticket relationship, and confirm available event sources (comments, attachments, audit log).
- [x] (2025-02-16 13:40Z) Implement lift history API with role gating, filters, and sorted timeline items.
- [x] (2025-02-16 14:05Z) Add lift history page route + template and update “Лифты” table with History action.
- [x] (2025-02-16 14:35Z) Add tests for permissions, ordering, and filtering.
- [x] (2025-02-16 15:05Z) Validate via pytest and document simple reproduction steps.

## Surprises & Discoveries

- None yet.

## Decision Log

- Decision: Use a server-rendered template (`templates/lift_history.html`) that fetches timeline data via `/api/lifts/<id>/history`.
  Rationale: Keeps UI consistent with existing server-rendered pages and avoids adding a front-end framework.
  Date/Author: 2025-02-16 / codex

- Decision: Use the existing `tickets.asset_id` → `assets` relationship to represent lift history instead of adding a new `lift_id`.
  Rationale: The lift model already exists as assets; no migration needed.
  Date/Author: 2025-02-16 / codex

- Decision: Timeline items will include core ticket events and comments; attachments/audit log entries will be included only if models exist.
  Rationale: Keeps MVP scope safe while leaving extensibility for richer sources.
  Date/Author: 2025-02-16 / codex
- Decision: Link history items to `/admin?ticket_id=<id>` and auto-open the ticket modal.
  Rationale: Provides a direct ticket drill-down without new ticket pages.
  Date/Author: 2025-02-16 / codex

## Outcomes & Retrospective

- Outcome (2025-02-16): Added lift history API, history page, timeline rendering, and tests for permissions/order/filtering. History links deep-link to ticket modals on `/admin`.

## Context and Orientation

- Backend is Flask with SQLAlchemy models in `liftcrm/db.py`.
- Routes live in `liftcrm/*/routes.py`.
- Templates live in `templates/`, static JS/CSS in `static/`.
- Tests live in `tests/`.

## Plan of Work

### Milestone 1 — Data model and API

Goal: Provide `/api/lifts/<id>/history` with timeline items and filters.

Work:
- Inspect Ticket model for `lift_id` (or equivalent). If missing:
  - Add `tickets.lift_id` nullable + safe migration using `ensure_migrations()` pattern.
  - Add lift select to ticket create flow (minimal dropdown).
- Implement API:
  - Role gate: ADMIN, DISPATCHER only.
  - Query tickets for lift; gather events from ticket fields and related tables (comments, attachments, audit log if present).
  - Support `from`, `to`, `q` filters.
  - Sort items by timestamp desc.

Validation:
- Manual: call endpoint with and without filters, ensure ordering.
- Tests: permissions + ordering + filtering.

### Milestone 2 — UI

Goal: Add “История” action on lift list and dedicated history page.

Work:
- Update “Лифты” table to include History button linking to `/lifts/<id>`.
- Add `templates/lift_history.html` with header card and timeline container.
- Add JS to fetch API and render list.
- Add server route `GET /lifts/<id>` with role gating (ADMIN, DISPATCHER).

Validation:
- Manual: open history page, see timeline entries, use query params.

### Milestone 3 — Tests + docs

Goal: Ensure test coverage and update operator guidance if needed.

Work:
- Add pytest coverage for permissions, ordering, q filter, date range.
- Run tests and capture output.
- Add brief notes to README or docs if UI workflow needs mention.

Validation:
- `pytest` passes.

## Artifacts and Notes

- Tests: `pytest` (60 passed).

## End-of-plan Change Log

- Change: Created lift history ExecPlan.
  Reason: New multi-layer feature spanning backend + UI + tests.
  Date/Author: 2025-02-16 / codex
- Change: Completed lift history milestones with API, UI, and tests; recorded outcomes and artifacts.
  Reason: Track delivered work and verification.
  Date/Author: 2025-02-16 / codex
