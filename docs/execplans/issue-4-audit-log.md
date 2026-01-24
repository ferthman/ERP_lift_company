# ExecPlan — Issue 4: Audit Log + Ticket History UI

## Purpose / Big Picture

Deliver a B2B-grade audit log for tickets/masters/attachments and expose a ticket history timeline in the admin UI. The audit log must capture who changed what and when, with RBAC enforcement (masters can only see assigned tickets). The UI should surface a “History” timeline in the ticket details card without breaking existing flows.

## Scope

- Add/verify `audit_log` table creation/migration and indexes.
- Build a defensive audit logging helper that records old/new/changed diff JSON.
- Log ticket/attachment/master events (create/assign/status/edit/archive/unarchive/cancel/upload).
- Provide `GET /api/tickets/<id>/history` response with actor info and RBAC.
- Update ticket details UI to render history timeline (labels, diff summaries).
- Add/adjust tests to cover audit logging and history RBAC.
- Update RUNBOOK with history usage + test commands.

## Non-Goals

- No refactor of unrelated code paths.
- No changes to auth or global error handling.

## Milestones

1) **Plan & discovery**: locate current audit/table helpers, history endpoints, UI hooks, and tests.
2) **Audit helper + DB migration**: ensure audit table/indexes exist and update `log_audit` to build `{old,new,changed}` safely.
3) **Backend wiring**: add/update audit logging for ticket/master/attachment operations and update history endpoint response shape + RBAC.
4) **UI timeline**: update labels and rendering for diff changes in ticket detail history.
5) **Tests + docs**: adjust/add tests for audit logs and RBAC; update RUNBOOK; run validation commands.

## Progress

- [x] (2025-02-19 10:05Z) Reviewed repo structure, existing audit logging, history endpoint, and UI hooks.
- [x] (2025-02-19 10:25Z) Audit helper updated to emit old/new/changed diff payloads defensively.
- [x] (2025-02-19 10:40Z) Backend logging updated for master/ticket/attachment events and history endpoint payloads.
- [x] (2025-02-19 10:45Z) UI history timeline labels and diff rendering aligned with audit payloads.
- [x] (2025-02-19 11:05Z) Tests updated, RUNBOOK documented, and validation commands executed.

## Surprises & Discoveries

- Existing `audit_log` table + `log_audit` helper already present but diff payload lacks `changed` and is not defensive.
- Ticket history UI already exists in `templates/index.html`, but action labels and diff handling need alignment with new audit diff format.

## Decision Log

- (2025-02-19) Keep existing audit table and extend payload format instead of introducing new schema changes.
- (2025-02-19) Use action `UPLOAD` for attachment audit events; keep entity types restricted to `ticket`, `master`, `attachment`.
- (2025-02-19) Include attachment audit events in ticket history by joining attachments to ticket history queries.

## Validation

- `python -m compileall liftcrm`
- `python -m unittest -v`
- Manual: open a ticket card → verify History timeline renders action labels and diffs.

## Outcomes & Retrospective

- (2025-02-19) Audit logging now covers ticket/master/attachment changes with `old/new/changed` diffs; history endpoint returns actor info with RBAC; UI timeline renders history.

## End-of-Plan Change Log

- Change: Initial plan created for Issue 4 audit log and history UI.
  Reason: Required ExecPlan for multi-layer feature.
  Date/Author: 2025-02-19 / codex
- Change: Updated progress, decisions, and outcomes after implementation/testing.
  Reason: Track milestone completion and validation.
  Date/Author: 2025-02-19 / codex
