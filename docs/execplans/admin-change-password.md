# Admin Change Password — ExecPlan

This ExecPlan defines the work to add an ADMIN-only change-password flow for user accounts and remove the reset-password UI.

## Purpose / Big Picture

Enable administrators to set a specific password for any user account (e.g., technicians) without exposing existing passwords. Replace the reset-password UI with a change-password modal and a new ADMIN-only API endpoint.

## Progress

- [x] (2025-03-10 09:30Z) Read repository routes/templates/tests and identified existing reset-password flow and access management UI.
- [x] (2025-03-10 10:35Z) Implement ADMIN-only password update endpoint with validation and hashing.
- [x] (2025-03-10 10:35Z) Replace reset-password UI with change-password modal and new client-side handler.
- [x] (2025-03-10 10:36Z) Update tests for admin/non-admin and validation cases.
- [x] (2025-03-10 10:52Z) Run pytest and capture results.
- [x] (2025-03-10 10:36Z) Update PLANS.md progress + decision log entries for this feature.
- [x] (2025-03-10 11:20Z) Fix change-password modal to preserve selected user id when resetting the form.

## Surprises & Discoveries

- Observation: `form.reset()` clears the hidden user id field, leading to requests without the target user id.
  Evidence: Change-password modal submission hit `/api/users//password` with a 404.

## Decision Log

- Decision: Reuse existing password hashing via `werkzeug.security.generate_password_hash` for the new endpoint.
  Rationale: Keeps behavior consistent with login and user creation flows.
  Date/Author: 2025-03-10 / codex
- Decision: Track the change-password target user id in a dedicated JS variable to avoid `form.reset()` clearing the hidden field.
  Rationale: Keeps the selected id stable across form resets and avoids invalid API calls.
  Date/Author: 2025-03-10 / codex

## Outcomes & Retrospective

- Outcome (2025-03-10): Admins can set a specific password via the new `/api/users/<id>/password` endpoint and the change-password modal; reset-password UI removed; tests cover admin success, non-admin forbidden, validation failures, and the modal preserves the selected user id after reset.

## Plan of Work

### Milestone 1 — Backend endpoint

- Add `POST /api/users/<user_id>/password` in `liftcrm/access/routes.py`.
- Require authenticated ADMIN role.
- Validate password (non-empty, min length 8).
- Update `user.password_hash` using existing hashing.
- Return `{ "ok": true }` without exposing password.

**Validation**
- Manual: POST with valid password returns 200 and `{ok:true}`.
- Manual: Non-admin returns 403.
- Manual: Short password returns 400 with clear error.

### Milestone 2 — Admin UI

- Remove reset-password buttons in Users and Masters tables.
- Add “Сменить пароль” action for users.
- Add modal with password + confirm fields and validation.
- Show success message “Пароль обновлён” and close modal.

**Validation**
- Manual: Open modal, mismatch blocks save.
- Manual: Save sends request and success message appears.

### Milestone 3 — Tests

- Add pytest coverage for admin success, non-admin forbidden, and validation failure.
- Ensure login with new password succeeds.

**Validation**
- Run `pytest`.

## Validation and Acceptance

- Admin can set a specific password for a technician account via UI and API.
- Non-admin cannot use the endpoint (403).
- Password validation rejects too-short values (400).
- UI no longer shows reset-password actions; change-password modal replaces it.
- Tests pass.

## End-of-plan change log

- Change: Created ExecPlan for admin change-password feature.
  Reason: Required for multi-layer feature change.
  Date/Author: 2025-03-10 / codex
