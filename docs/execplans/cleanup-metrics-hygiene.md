# Cleanup and Metrics Stabilization PR — ExecPlan

This ExecPlan is the source of truth for the cleanup/stabilization PR. It is intentionally scoped to repository hygiene and the `/api/metrics` edge-case bug. It must not add features, alter CSRF/CORS/session behavior, touch PWA/offline behavior, or change deployment, Docker, or Postgres files.

## Purpose / Big Picture

Remove generated runtime artifacts from Git tracking, make ignore rules explicit, and fix `/api/metrics` so it returns all masters and also succeeds when there are zero masters. Add focused regression tests that prove the frontend-facing metrics response shape remains stable.

## Progress

- [x] (2026-04-30 23:29 +05) Inspect current branch, `.gitignore`, tracked generated artifacts, metrics route, and existing test patterns.
- [x] (2026-04-30 23:33 +05) Update `.gitignore` and remove runtime/generated artifacts from Git tracking without deleting source files.
- [x] (2026-04-30 23:33 +05) Fix `/api/metrics` return indentation while preserving the existing JSON contract.
- [x] (2026-04-30 23:33 +05) Add regression tests for multiple masters, zero masters, response shape, and seeded/default DB behavior.
- [x] (2026-04-30 23:36 +05) Run focused metrics tests, full pytest suite, Git cleanliness checks, and Git tracking checks.
- [x] (2026-04-30 23:37 +05) Record outcomes and exact validation results.

## Surprises & Discoveries

- Observation: `.gitignore` only ignored `__pycache__/` and `*.pyc`, while `lift_crm.db`, `archive.xlsx`, and many `vendor/openpyxl/**/__pycache__/*.pyc` files were tracked.
  Evidence: `sed -n '1,220p' .gitignore`; `git ls-files lift_crm.db archive.xlsx`; `git ls-files 'vendor/openpyxl/**/*.pyc' 'vendor/openpyxl/**/__pycache__/*'`.
- Observation: `/api/metrics` returns inside the `for m in masters` loop, so only the first master is emitted and an empty master table falls through with no response.
  Evidence: `liftcrm/tickets/routes.py` around `metrics()`.
- Observation: Focused metrics regression tests pass after moving the response outside the loop.
  Evidence: `venv/bin/python -m pytest tests/test_metrics_api.py -q` returned `3 passed in 0.86s`.
- Observation: The first full-suite run failed because the new metrics tests added default-admin login attempts to the same in-memory rate-limit bucket used by later existing tests.
  Evidence: `venv/bin/python -m pytest -q` returned one `429 != 200` failure in `OpsHistoryTest.test_ops_limit_completed_cancelled`.
- Observation: Isolating metrics test login requests with a reserved test IP removed that shared-test-state interference.
  Evidence: The next `venv/bin/python -m pytest -q` returned `92 passed in 13.82s`.

## Decision Log

- Decision: Add a dedicated metrics regression test module that follows the repository's existing `unittest` + Flask test client style.
  Rationale: Existing tests already use this pattern, so the new coverage stays local and requires no new tooling.
  Date/Author: 2026-04-30 / codex
- Decision: Use `git rm --cached` for generated artifacts so they leave Git tracking while remaining on the user's filesystem if present.
  Rationale: The task asks to remove artifacts from tracking, not necessarily delete local runtime files.
  Date/Author: 2026-04-30 / codex
- Decision: Send metrics-test login requests with `REMOTE_ADDR = 198.51.100.77`.
  Rationale: Login attempts are rate-limited by IP and username in process memory; using a reserved test IP keeps this regression module from consuming the default admin login bucket used by unrelated tests.
  Date/Author: 2026-04-30 / codex

## Outcomes & Retrospective

- Outcome (2026-04-30): Added explicit ignore rules for runtime DB/archive/upload/venv/cache artifacts. Removed `lift_crm.db`, `archive.xlsx`, and 208 tracked `vendor/openpyxl/**/__pycache__/*.pyc` bytecode files from Git tracking with `git rm --cached`, leaving local runtime files present. Moved the `/api/metrics` response outside the master loop so every master is returned and zero-master datasets return HTTP 200 with an empty `masters` list. Added `tests/test_metrics_api.py` covering seeded/default DB behavior, multiple masters, zero masters, and stable frontend-facing response keys.
- Validation (2026-04-30): `venv/bin/python -m pytest tests/test_metrics_api.py -q` passed with `3 passed in 0.86s`; `venv/bin/python -m pytest -q` passed with `92 passed in 13.82s`; `git ls-files lift_crm.db`, `git ls-files archive.xlsx`, and `git ls-files 'vendor/openpyxl/**/*.pyc' 'vendor/openpyxl/**/__pycache__/*'` returned no output after tests. `git status --short` showed only intended source/plan/test edits plus staged deletion entries for the previously tracked generated artifacts.

## Plan of Work

### Milestone 1 — Repository hygiene

Goal: Generated runtime artifacts are no longer tracked, and future local artifacts are ignored.

Work:

- Update `.gitignore` with explicit patterns for `lift_crm.db`, `uploads/`, `archive*.xlsx`, `venv/`, `.venv/`, `.pytest_cache/`, `__pycache__/`, `*.pyc`, `*.pyo`, `*.pyd`, and `.DS_Store`.
- Remove `lift_crm.db`, `archive.xlsx`, and tracked `vendor/openpyxl/**/__pycache__/*` / `.pyc` files from Git tracking using `git rm --cached`.
- Do not remove `vendor/openpyxl` source `.py` files.

Validation:

- `git ls-files lift_crm.db archive.xlsx` returns no files.
- `git ls-files 'vendor/openpyxl/**/*.pyc' 'vendor/openpyxl/**/__pycache__/*'` returns no files.

### Milestone 2 — Metrics route fix

Goal: `/api/metrics` returns the same top-level contract but includes every master and returns a valid JSON response when there are zero masters.

Work:

- In `liftcrm/tickets/routes.py`, move the `return jsonify(...)` block outside the `for m in masters` loop.
- Leave the keys consumed by `templates/index.html` intact: `overall`, `masters`, `total_tickets`, SLA breach counts/percentages, `tickets_by_close_reason`, `sla_breaches_by_reason`, and `tickets_by_priority`.

Validation:

- Focused metrics tests prove multiple masters are returned and the empty-masters case returns HTTP 200.

### Milestone 3 — Regression tests and verification

Goal: Capture the fixed behavior and prove the repository remains clean after tests.

Work:

- Add `tests/test_metrics_api.py`.
- Cover multiple masters, zero masters, stable response shape, and default seeded DB behavior.
- Run focused tests and the full suite.
- Run `git status --short` and artifact tracking checks after tests.

Validation:

- Record exact commands and results in this plan and final response.

## End-of-plan change log

- Change: Added Cleanup and Metrics Stabilization PR ExecPlan.
  Reason: The requested work spans route behavior, tests, and repository tracking hygiene, so `AGENTS.md` requires an ExecPlan.
  Date/Author: 2026-04-30 / codex
- Change: Completed cleanup and metrics stabilization milestones and recorded validation.
  Reason: Track the exact behavior fixed, artifact-tracking checks, and full-suite result.
  Date/Author: 2026-04-30 / codex
