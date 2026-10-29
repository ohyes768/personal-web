# Execution plan

Status: planning. Do not run task.py start until artifacts are reviewed or implementation is explicitly requested. No application implementation is included in this planning turn.

1. Read applicable AGENTS.md and the dividend quality/refresh-job contracts, code-type guidelines, shared guides and Windows testing constraints. Inspect current diffs: the queue popup and rating-dimensions/version work are already modified; preserve concurrent work and reconcile their final types/API before editing.
2. Verify deployed Hermes cancellation from authoritative source/schema without cancelling a real user's task. Record method, payload, authentication, acceptance versus terminal confirmation, unsupported behavior, submit/cancel races and idempotency after cancellation in research/hermes-cancel.md. This capability check gates implementation of running cancellation. Do not invent an upstream route.
3. Add deterministic failing tests for waiting cancellation/no remote submission, front/up/down ordering, boundaries, concurrent append/dispatch/reorder, and stale attempt IDs. Include the current semaphore boundary so all still-waiting items remain controllable.
4. Implement quality-only action identity, authoritative order, synchronized pending mutations and durable acknowledgement. Ensure ordinary refresh submit and append regressions remain valid.
5. With verified upstream support, test then implement run_id tracking, cancelling/confirmed cancellation, pre-run-id intent, remote refusal/timeout, completion races, slot ownership, previous-result preservation and new admission after a cancelled run. Use fake Hermes clients for tests.
6. Add cancellation accounting tests, including all-waiting-cancelled, mixed success/cancel, duplicate cancel, re-admission of the same code, old job records, restart interruption and shutdown. Implement exact-once quality accounting without affecting financial/M120.
7. Update frontend types/API/hook and active-only queue view. Retain pending/cancelling dedup, authoritative ordering, elapsed time and query resilience. Render only the two active groups, with per-item controls and conflict/error feedback. Remove modal terminal history/progress/retry controls.
8. Update browser regression tests: active-only rows/empty state, running cancel lifecycle, waiting cancel, all ordering actions and disabled boundaries, conflict refresh, hidden/reopened timer, reload ordering, duplicate click, network errors and preserved unrelated actions. Adapt existing tests expecting terminal rows/retry inside the queue modal.
9. Backend checks from backend/dividend-select using the project interpreter: python -m pytest tests/test_quality_service.py tests/test_quality_api.py tests/test_refresh_jobs.py tests/test_hermes_client.py; use isolated F: basetemp per repository testing contract. Frontend from apps/dividend: npx tsc --noEmit, run quality utility tests using the existing runner, and npm run test:e2e -- e2e/screening.spec.ts with isolated test data/port. Verify desktop/mobile popup controls visually.
10. Run Trellis quality review, update quality/refresh-job specs for the final action and accounting contracts, and report tests plus any upstream limitation. Commit/deploy only with applicable authorization.

## Review checkpoints

- Hermes cancellation contract must be verified before promising or implementing a functional running cancel action.
- Product scope is closed to terminal/history/bulk features; do not expand it during implementation.
- Reconcile the in-progress dividend-quality-dimensions task and preserve all unrelated workspace changes.
- Do not prune terminal internal data required for correctness when hiding it from the UI.
