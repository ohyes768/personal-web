# Hermes analysis queue design

## Decision

Recommend a server-owned appendable queue with the existing global concurrency configuration. A browser-only queue loses pending work on page closure; separate jobs with separate semaphores can exceed the intended limit. Keep one active quality job and provide explicit quality-only append admission rather than changing ordinary financial/M120 submit reuse.

## Backend

- Coordinate admission and last-worker completion under explicit ownership/locking so appended work cannot be lost while a job becomes terminal.
- Persist appended codes and updated total/remaining/retry_codes before acknowledging acceptance. Deduplicate queued/running codes; duplicate-only requests reuse the job without resetting item timestamps. Snapshot stock payload/data date per admitted item.
- Dispatch pending work in FIFO order up to HERMES_MAX_CONCURRENT. Save scores and update item/job progress immediately after each stock finishes, including individual failures.
- Extend quality snapshots with queue items containing code, name, state, error, queued_at, started_at and finished_at; retain existing score/job fields and Hermes idempotency semantics.
- Discover latest quality job on reload. Preserve existing interrupted/manual-retry restart and bounded shutdown semantics; no automatic replay.

## Frontend

- Queue panel above the screening table remains visible independently of query result/filter changes. Show all running items first, queued items in admission order, then recent terminal items; include running/waiting counts and retry actions.
- Running rows display elapsed minutes/seconds from backend started_at, refreshed locally every second. Polling does not reset the timer. Terminal duration freezes at finished_at; missing legacy timestamps show 未记录.
- Replace global analysis disabling with per-stock submitting/queued/running disabling across list and report modal. Other eligible stocks remain actionable.
- Use authoritative server snapshots and a single resilient polling lifecycle. Additional submissions must not invalidate existing polling. Mount discovers existing work; individual completion refreshes scores. Query errors preserve queue state and trigger retry; unmount cancels local timers only.

## Risks and compatibility

The old extra-code rejection contract is intentionally superseded. Update its tests/specs with implementation. Manager/service synchronization and completion/admission races require deterministic tests. Do not alter ordinary refresh submit behavior or historical score storage. Deploy backend/frontend together; drain active tasks before rollback. No score-data migration is needed.
