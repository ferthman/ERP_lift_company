# AGENTS.md

This repository uses execution plans (“ExecPlans”) to deliver complex features and refactors safely and repeatably.

An ExecPlan is a single, self-contained design-and-implementation guide that a coding agent can follow with no prior context beyond the current working tree and the ExecPlan itself.

## When to use an ExecPlan

Use an ExecPlan for any of the following:

- A new feature that spans multiple files or layers (backend + frontend).
- Any change that impacts data models, migrations, authentication, or authorization.
- Offline sync, background processing, queues, or other stateful workflows.
- Refactors that change module boundaries or core flows.
- Work expected to take more than ~30–60 minutes of focused effort.
- Any task where ambiguity could cause wrong assumptions.

If a task is complex, do not start coding immediately. Create or update an ExecPlan first.

## Source of truth

- The ExecPlan is the source of truth for the work.
- If there is conflict between an implementation idea and the ExecPlan, update the ExecPlan first, record the decision, then proceed.


## Non-negotiable requirements for agents

When implementing an ExecPlan, the agent must:

1) Read the full plan first  
   Do not code until the plan is understood.

2) Work milestone-by-milestone  
   Each milestone must produce observable, verifiable behavior before moving on.

3) Keep the plan updated while working  
   The sections below must be updated continuously:
   - `Progress` (checkboxes, with timestamps)
   - `Surprises & Discoveries`
   - `Decision Log`
   - `Outcomes & Retrospective`

4) Be explicit and repository-specific  
   Name exact files and functions. No “magic” steps.

5) Validate continuously  
   Run relevant tests and provide simple reproduction steps after each milestone.

6) Commit frequently  
   Prefer small commits that keep the system working. Avoid huge unreviewable diffs.

7) Resolve ambiguities autonomously  
   Do not ask the user “what next”. Make a reasonable decision, record it in the Decision Log, and proceed.

8) Keep changes safe and idempotent  
   Migrations must not break existing databases. Steps should be repeatable without damage.

## What to do when stuck

If implementation reveals unexpected constraints:

- Create a small “prototype milestone” inside the ExecPlan to de-risk the unknown.
- Capture evidence in `Surprises & Discoveries`.
- Record the chosen path (and rejected options) in the `Decision Log`.
- Continue with the next most verifiable step.

## How to validate work (minimum bar)

An ExecPlan is not complete until:

- A human can follow the Validation section and observe the feature working.
- Tests (if present) pass.
- The new behavior is demonstrable (not just “code compiles”).
- Documentation is updated for operators/users.

## Example: Technician PWA work

For the Technician PWA (offline outbox + sync), the agent must:

- Follow the dedicated ExecPlan (e.g., `PLANS.md` or `docs/execplans/technician-pwa.md`).
- Implement backend endpoints, then sync, then UI, then offline storage, then validation.
- Prove offline behavior using browser offline mode and an end-to-end scenario.
