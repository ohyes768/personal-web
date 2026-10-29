# Implementation plan

Status: planning. Review these artifacts before task.py start.

1. Load applicable AGENTS.md, quality-rating-contract, refresh-jobs-contract, code-type guidelines, cross-layer/reuse guides and frontend conventions; inspect backend submodule status/environment.
2. Add failing service/manager/API tests for mixed duplicate/new admission, global concurrency, durable acceptance, last-worker append races and immediate per-stock completion. Preserve financial/M120 regressions.
3. Implement quality-only durable append, FIFO dispatch, lifecycle metadata and server snapshots. Preserve rating parsing, score persistence and Hermes idempotency.
4. Update frontend types/API and hook for repeated submissions, per-stock pending state, reload discovery and resilient polling. Implement queue panel, elapsed timer and per-stock list/modal controls.
5. Add browser tests for A running then B queued with C available, duplicate prevention, multiple running rows, elapsed duration, reload, filter changes, retries and temporary query errors.
6. Run backend focused tests from backend/dividend-select using its environment: `python -m pytest tests/test_quality_service.py tests/test_quality_api.py tests/test_refresh_jobs.py tests/test_hermes_client.py`; use isolated F: basetemp if required.
7. From apps/dividend run `npx tsc --noEmit` and `npm run test:e2e -- e2e/screening.spec.ts`; run refresh-job browser regressions if shared manager changes. Inspect rendered queue/timer using mocked analysis data.
8. Complete Trellis quality review, update changed queue contracts and report verification. Commit/deploy only with applicable authorization.

## Rollback

Keep append opt-in for quality; preserve normal RefreshJobManager.submit behavior. Avoid skill output or historic score-data changes. Drain active work before reverting backend/frontend; restart retains interrupted/manual-retry behavior.
