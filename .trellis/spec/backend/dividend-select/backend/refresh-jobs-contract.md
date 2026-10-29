# Background Refresh Jobs

## 1. Scope / Trigger
Applies to M120 and financial refresh, scheduler self-calls, refresh progress UI,
and changes to refresh persistence or CSV publication. The deployment uses one
FastAPI worker. This is an in-process thread executor, not a distributed queue.

## 2. Signatures
- `POST /api/dividend/m120/refresh`: `{codes: string[]}` → HTTP 202 job.
- `POST /api/dividend/financial/refresh?force=true|false`: optional `{codes}` → 202 job.
- `GET /api/dividend/refresh/jobs?kind=m120|financial`: latest job or JSON null.
- `GET /api/dividend/refresh/jobs/{job_id}`: job, or 404.
- `RefreshJobManager.submit(kind, codes, work, params=None)`: durable acceptance;
  `work(progress)` runs synchronously in a dedicated executor thread.
- `RefreshJobManager.append_codes(job_id, codes) -> job | None`: quality-only
  durable append into an active job; returns None when the job is missing or
  already terminal. Never called by m120/financial.
- Collectors accept optional `on_progress(code, success)` without changing their
  existing integer/DataFrame return values. Financial batch callbacks remain supported.

## 3. Contracts
Jobs contain `job_id`, `kind`, `status`, `total`, `processed`, `succeeded`, `failed`,
`remaining`, `codes`, `failed_codes`, `retry_codes`, `admissions`, `params`, `error`, `message`,
and Shanghai timezone ISO timestamps. Admission also includes `reused`.
Statuses: queued/running/succeeded/partial_failed/failed/interrupted.
`processed=succeeded+failed`; `remaining=total-processed`. `total` counts
accepted items: one per code initially, plus one per appended acceptance
(quality retry re-admits a code). `admissions[code]` records the expected
number of completions per code; `progress` rejects codes outside `codes`, and
counts repeated progress for the same code only up to quality retry re-admission
(m120/financial still report each code exactly once). Success removes the code
from `failed_codes`; terminal status uses `failed_codes` (current failures), not
the cumulative `failed` attempt count, so a retried-and-recovered quality job
ends `succeeded`. The `message` 失败 figure is `len(failed_codes)`. Success counts collected
rows; publication failure overrides the whole job to failed and retries all codes.
Empty selections produce a zero-count succeeded job.

`append_codes` merges new acceptances into the active job under the manager
lock: new codes extend `codes`, `admissions[code]` increments, `total`/
`remaining`/`retry_codes` update, and the job is saved before the caller
acknowledges. It never touches a terminal job.

One active job per kind owns all writes, including scheduled refresh. Different
kinds may run concurrently. Synchronous routes perform only preparation/admission;
collector work never runs inside the async event loop. Admission and status are
protected by a thread RLock; worker threads do not manipulate asyncio locks.

Records live in `data/refresh_jobs/*.json`, at most 20 terminal records per kind.
Acceptance and final state are atomically saved; intermediate progress is saved
at most once per second. Startup marks unfinished records interrupted and never
replays collection. Interrupted and publication-failed jobs retry all original
codes conservatively. Failed/remaining codes from normal completion are exact.
File writes use a unique temporary file in the destination directory then
`os.replace`. Financial reads use `read_csv(strict=True)` before merging to avoid
overwriting unreadable caches. Codes remain six-digit strings. M120 publishes to
the captured current-week destination and preserves previous snapshots.

Financial force/90-day throttle and pool selection remain in place. Duplicate
active requests bypass throttle and reuse the task. UI retries financial jobs
with force=true. M120 limits reset per attempt; five consecutive failures stop
collection, leaving unprocessed stocks in remaining. Invalid/nonfinite M120s fail.

Scheduler accepts 202, skips reused jobs, and polls until a real terminal result.
History stores count (collected successes), failed, remaining and refresh_job_id.
Legacy HTTP 200 remains supported for staged migration. A polling timeout reports
waiting failure, never background success or cancellation.

UI polls every two seconds (ten seconds while hidden), rediscovers latest jobs
from the server, retains active state through network errors and resets discovery
after 404. Unmount cancels polling only. Terminal state refreshes status, tables,
and applied screening conditions while retaining unsaved form inputs.

Shutdown rejects admission and waits for at most 30 seconds after scheduler drain.
It never cancels executor futures or releases ownership while collection is still
writing. Python executor threads may finish after lifespan's wait deadline;
operational restart must not overlap old and new writer processes.

## 4. Validation & Error Matrix
| Condition | Result |
| --- | --- |
| Invalid code or kind | 422 |
| Financial updated within 90 days, not forced | 429 |
| Missing manager / closing admission | 503 |
| Active same-kind request | 202, same id, reused=true |
| Some failed or remaining stocks, at least one success | partial_failed |
| All attempted stocks fail / publication fails | failed |
| Service restarts during collection | interrupted; no automatic replay |
| Progress query loses network | display query error; do not mark collection failed |
| Corrupt old financial cache | fail before collection/publication; preserve bytes |

## 5. Good / Base / Bad Cases
Good: two successes, 2/2 processed, succeeded terminal, then refresh page data.
Base: one success and one failure, 2/2 processed, partial_failed, retry failed code.
Bad: five failed requests in a seven-stock M120 batch, 5/7 processed, failed,
two remaining; no success message. Bad: fetched row but disk full → whole job
failed, old CSV readable, all requested codes eligible for forced retry.

## 6. Tests Required
`test_refresh_jobs.py`: prompt acceptance, concurrent dedup, counts, shutdown,
restart interruption, empty jobs, terminal persistence and publication errors.
`test_refresh_jobs_api.py`: ASGI acceptance/query, 404/422, financial throttle,
force merge and string codes. `test_refresh_collectors.py`: real collector
limit/retry, invalid numeric values, failed atomic publication, corrupt cache.
`test_scheduler_jobs.py`: 202 waits and reused skips. Run alongside rollover,
financial, screening and scheduler shutdown regressions with an F: basetemp.
`e2e/refresh-jobs.spec.ts`: reload recovery, partial result/retry, reused acceptance,
disabled running action, close/reopen and network recovery.

## 7. Wrong vs Correct
Wrong: treat HTTP 202 as completion, display success, then reload data immediately.
Correct: retain the job id, poll terminal state, display real result and reload then.
Wrong: cancel an asyncio wrapper and allow a second collector to write its CSV.
Correct: retain thread ownership until work finishes; restart marks persisted
unfinished records interrupted. Never increase proxy timeouts as the solution.
