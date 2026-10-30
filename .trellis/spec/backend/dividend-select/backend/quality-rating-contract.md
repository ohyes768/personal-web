# Hermes Quality Rating (Fundamental Score)

## 1. Scope / Trigger
Applies to the dividend-select fundamental-rating pipeline: the bundled
`basic-quality-rating` skill (automation JSON mode), `hermes_client`,
`quality_service`, the `/quality/*` routes, and the ScreeningTab quality UI.
Triggered whenever the skill output JSON contract, star mapping, idempotency
scheme, or Hermes delivery mode changes. The former standalone
`dividend-quality-scoring` skill was removed on 2026-10-24; its JSON contract
now lives inside `basic-quality-rating` v2.2+.

## 2. Signatures
- `POST /api/dividend/quality/analyze`: `{codes: string[]}` → 202 job; 503 when
  `HERMES_BASE_URL`/`HERMES_API_KEY` unset or the service is closing; 400 for
  codes outside the collected pool, or when the previous job is in its
  admission-drain window past the wait deadline; 422 for non-six-digit codes or
  an empty list. While a quality job is active, new codes append to it
  (`reused: true`) and dispatch FIFO up to `HERMES_MAX_CONCURRENT`; codes
  already queued/running are idempotently skipped without resetting their
  timestamps. (Changed 2026-10-29: the former 400 `已有评级任务在跑`
  extra-code rejection is superseded by durable queue append.)
- `GET /api/dividend/quality/jobs/{job_id}`: quality job or 404 (also 404 for
  non-quality kinds).
- `GET /api/dividend/quality`: `{total, scores: {code: QualityScore},
  per_code, hermes_configured}`; `GET /quality/jobs/{job_id}` also embeds
  `per_code`. `per_code` is the in-memory per-stock live status
  (`{state: queued|running|cancelling|completed|failed|cancelled, error,
  updated_at, name, queued_at, started_at, finished_at, item_id, position}`),
  cleared on restart. `queued` is written at admission (with `queued_at`).
  `running` starts only after a free concurrency slot is claimed
  (`started_at` — the analysis-duration clock base). `cancelling` stays in the
  running group until Hermes confirms a terminal status. `position` is the
  1-based server waiting order and is null once the item is no longer queued.
  `item_id` is that admission's `attempt_id`. Items persist across jobs so
  recent terminal results stay visible for list retry; resubmitting a terminal
  code re-admits it with a new `item_id` and fresh timestamps. The
  ScreeningTab action column renders it row-by-row
  (排队中/评级中 pulse, 失败+原因 tooltip+重试, else 分析/重评 buttons);
  a compact 评级队列 button in the screening toolbar shows running/queued
  counts. Clicking opens the shared Modal with only two groups: 正在分析
  (`running` and `cancelling`) and 排队中 (server `position` order). The header
  shows those two counts. Empty active state is 暂无进行中的任务. The modal
  does not show terminal rows, aggregate job progress, or retry. Reports and
  list retry stay outside it. The modal's per-second local tick computes
  已分析 X分Y秒 from server `started_at`; closing stops only this display
  timer, never polling or work. Queue mutations are
  `POST /quality/queue/{item_id}/cancel` and
  `POST /quality/queue/{item_id}/move` (`{action: front|up|down}`). See the
  active-queue scenario below.
  Reopening restores elapsed time from the original timestamp. Escape,
  backdrop and close button dismiss the modal.
  `hermes_configured=false` disables the UI
  analyze button (grey + hint) instead of waiting for the 503.
- `hermes_client`: `HermesConfig.from_env()` (frozen dataclass, `is_configured`
  property), `submit_run(cfg, prompt, idempotency_key) -> run_id`,
  `poll_run(cfg, run_id) -> output`. Errors: `HermesError` base +
  `HermesApiError` / `HermesRunFailed` / `HermesTimeout`.
- `quality_service`: `build_stock_payload(stock) -> dict`,
  `build_prompt(payload) -> str` (names the skill, demands bare JSON),
  `parse_quality_output(raw, code, name) -> QualityScore`,
  `QualityService.submit_analysis(codes, cfg, stocks, data_date, refresh_jobs,
  submit_run_fn, poll_run_fn) -> job`.

## 3. Contracts
Scoring runs one Hermes run per stock through the Runs API
(`POST {base}/p/{profile}/v1/runs`, Bearer + `Idempotency-Key`, poll to
terminal state). Results are delivered via `run.output` only — no shared
artifact directory, no run bindings. Idempotency key is
`quality-{code}-{data_date}-{skill_version}` where `data_date` is the financial
summary mtime date (fallback: today). Capture the installed version at admission;
version changes must not reuse an old Hermes run. Without a configured installed
version, use `unknown-{attempt_id}` so explicit reanalysis avoids stale cache.

The skill output is a single bare JSON object: `code`, `name`,
`dimensions` (exactly business/moat/industry/management/financial, each 1-5
int or null — evidence-insufficient dimensions are null, and `financial` is
necessarily null for banks/insurers), `weighted_score` (= dimensions ×
0.25/0.25/0.20/0.15/0.15, tolerance ±0.01), `stars` (mechanical mapping
≥4.5→5, ≥4.0→4, ≥3.0→3, ≥2.0→2, else 1), `boundary` (set when within 0.25 of
a tier edge), `summary`, `risks`, `watch_points`, `report_md` (non-empty
Chinese markdown). When any dimension is null the stock is 未评级:
`weighted_score`, `stars` and `boundary` must ALL be null (v3 skill contract;
summary starts with 「灰色地带（证据不足，未评级）」). pydantic enforces the
all-or-nothing in both directions: an unrated stock carrying any non-null
derived field, or a fully rated stock carrying null weighted_score/stars, is
rejected as a per-stock failure. Parsing tolerates
```json fences and stray prose around the object. The screening list shows one
评级结果 column: `4/4/3/2/1（v1.1.1）` in
business/moat/industry/management/financial order. Each score is 1–5; null uses
— in its position, explained as 未评分 in the tooltip and report. A missing
report shows a single —. The entire score/version text is a button opening the
report. Missing provenance shows （版本未知）; 需重评 remains an adjacent hint.
Do not show weighted_score or hide known scores when a dimension is null.
The report modal shows dimension scores and metadata, with no aggregate stars,
overall unrated banner, weighted score or boundary banner. (Changed 2026-10-29: five
scores/version in a compact column supersede the aggregate result. Changed
2026-10-27: v3 null contract adopted; the in-repo skill copy
`backend/dividend-select/skills/basic-quality-rating/SKILL.md` was removed
after drifting stale — the skills repo
`F:\personal-projects\skills\finance-macro\basic-quality-rating\` is the
single source, installed into Hermes via skill-manager.)

### Skill version provenance (2026-10-29)
- Skill 4.3.0 adds `skill_version` as the eleventh output field. Its finalizer
  reads its own SKILL.md metadata.version and its validator rejects mismatches.
- Backend QualityScore accepts optional semantic-version strings for backward
  compatibility; missing versions remain null and are never backfilled.
  Persist the reported version, including on parsed-but-unrated results.
- `GET /quality` adds nullable `current_skill_version`. Read deployed metadata
  fresh from `HERMES_QUALITY_SKILL_PATH`, or the explicit override
  `HERMES_QUALITY_SKILL_VERSION`. No source means null, not latest stored score.
  Never point the path at an unpublished development checkout.
- Capture this expected version per queue item; include it in the prompt and
  reject a missing/different output version without overwriting previous scores.
- List and report show vX.Y.Z or 版本未知. With a known current version, differing
  or missing provenance displays 需重评. Without it, explain comparison is
  unavailable. Historical scores are still immediately usable.
- Publish the changed skill to the configured Hermes profile before configuring
  the expected version. To follow installed metadata automatically, mount that
  skill read-only and set the in-container SKILL.md path; verify symlink targets
  remain readable. Env-only version overrides need updating on each publication.
- Tests: test_quality_version.py checks persistence, legacy/invalid input, fresh
  manifest reads, cache separation and mismatched output. screening.spec.ts
  checks column mapping, partial dimensions and current/old/unknown versions.

### Dimension-only reports (skill 4.4.0)
- Keep the 11 JSON fields and existing stars/boundary arithmetic for machine
  compatibility. Do not copy them into summary/report_md/risks/watch_points.
- Skill finalize rejects aggregate star/boundary presentation in these narrative
  fields. The read-only validator reuses that check and no longer warns that a
  report is missing the former star/boundary section. Business facts such as
  五星酒店 / 三星电子 and risk-boundary descriptions are not rating labels.
- New report sections are title/date, business verification, five dimensions,
  conclusions/risks and sources. No stars, star counts, upgrade/downgrade or
  踩线/非边界档位 presentation. Financial evidence/null handling is unchanged.
- Remove the modal's aggregate star/unrated/boundary header even for old saved
  scores. Historical narrative is not rewritten; publish 4.4.0 and reanalyze
  to replace old report text. Preserve dimension table, duration, dates, version
  warning and reanalysis actions.
- Tests: skill test_no_stars.py checks narrative rejection and retained JSON
  fields; screening.spec.ts injects an old 3-star/boundary record and checks
  the header stays hidden while metadata/dimension rows remain visible.

Bulk analysis reuses `RefreshJobManager` with `kind='quality'` (included in
`_prune` kinds). Each stock is one worker thread bounded by a semaphore
(`HERMES_MAX_CONCURRENT`, default 4); a failed poll/parse marks only that
stock failed. Scores persist to `data/quality_scores.json`
(`{code: {…score, scored_at, data_date, analysis_duration_seconds}}`), merged under a file lock and
written via `atomic_write` after each stock completes.

### Analysis duration (2026-10-29)
- Scope / signature: `QualityService._save_one(score, data_date,
  analysis_duration_seconds)` persists backend-owned metadata; `GET /quality`
  passes it through to the report modal. The skill JSON is unchanged.
- Contract: seconds rounded to 3 decimals, measured with `monotonic()` per
  stock from immediately before submit until poll returns. Excludes local
  semaphore queueing, parsing, saving and waiting for other stocks. A reused
  Hermes run measures this request's retrieval time, not the original run.
- Validation / cases: `155.25` displays `分析耗时 2分35秒`, `3600` displays
  `1小时0分0秒`, and zero displays `0秒`. Missing, null or invalid durations
  display `分析耗时 未记录`; historical records are never backfilled.
- Tests: `test_analysis_duration_is_measured_and_persisted` verifies submit
  plus poll duration survives a fresh service read; screening Playwright
  duration cases verify the report UI and legacy compatibility.
- Wrong: subtract `data_date` from `scored_at` or let the model invent timing.
  Correct: measure the individual request in the backend and save numeric seconds.

Hermes config comes from env only: `HERMES_BASE_URL`, `HERMES_API_KEY`,
`HERMES_PROFILE` (default `ohyes768`), `HERMES_POLL_INTERVAL` (30s),
`HERMES_TIMEOUT` (3600s), `HERMES_MAX_CONCURRENT` (4). Unset base/key keeps
every other feature unchanged (analyze returns 503). The skill source lives in the skills repo
(`F:\personal-projects\skills\finance-macro\basic-quality-rating\`, v3+),
installed into the Hermes profile via skill-manager — the former in-repo copy
was removed 2026-10-27 (see the changed-notes in Contracts); the skill must
never embed dividend backend URLs or schema details. Frontend mirrors the contract in `lib/quality.ts`
(`starsFor` must match the mapping above; `RefreshKind` includes `quality`).

## Scenario: quality queue append admission (2026-10-29, supersedes the admission mutex)

### 1. Scope / Trigger
- Trigger: changing `QualityService.submit_analysis`, quality `per_code`,
  `RefreshJobManager.append_codes`, or `POST /quality/analyze` behavior while
  another quality job is active.

### 2. Signatures
- `QualityService.submit_analysis(...) -> job | None`
- `RefreshJobManager.append_codes(job_id, codes) -> job | None` (quality-only;
  ordinary `submit` reuse rules unchanged). QualityService's admission and its
  dispatch-loop exit decision share one `Condition`; the loop sets
  `_accepting=False` under that lock when the queue drains.

### 3. Contracts
- Admission snapshots stock payload, name and `data_date` per item
  (idempotency key `quality-{code}-{item.data_date}`), so later data refreshes
  never mutate already-admitted work.
- Active quality job + new codes → `append_codes` merges them (job `codes`
  stays unique, `admissions[code]` counts acceptances, `total`/`remaining`/
  `retry_codes` updated) and **persists the job before acknowledging**;
  service-side items enter the FIFO deque under `_cond`. Response is the
  updated job with `reused: true`.
- Codes already queued/running → skipped; duplicate-only requests return the
  job `reused: true` and never reset timestamps or re-run Hermes.
- Resubmitting a completed/failed code re-admits it (fresh `queued_at`;
  `total += 1` so retry work is counted); after it finishes its progress call
  re-counts the code and success removes it from `failed_codes`.
- Queue drained and nothing running → dispatch loop exits with
  `_accepting=False`; a submit landing in the terminal-write window waits for
  the job to turn terminal (bounded by `ADMISSION_WAIT_SECONDS`, then 400)
  and then opens a fresh job. Appends can never be lost between admission and
  the loop's exit decision because both hold `_cond`.
- Service restart: in-memory items clear, the job is marked interrupted with
  `retry_codes` — manual retry only, no automatic replay (unchanged).

### 4. Validation & Error Matrix
| Condition | Result |
| --- | --- |
| Hermes base/key unset | 503 |
| Code not in collected pool | 400，采集池文案 |
| Active quality job, request has queued/running codes only | 202, same `job_id`, `reused: true`, timestamps unchanged |
| Active quality job, request has new codes | 202, same `job_id`, `reused: true`, job codes/total/updated before ack |
| Dispatch loop exited, job not yet terminal | submit waits (≤10s), then opens a new job |
| Previous job interrupted by restart | items empty; job shows 中断 with retry_codes; manual retry |

### 5. Good/Base/Bad Cases
- Good: A running, submit B → same job, B queued after A's running item, both
  complete; submit C afterwards → new job.
- Base: B failed while A still runs → retry B → `total` counts the retry, B
  re-queued; retry success clears it from `failed_codes`, job can end
  `succeeded` even though `failed` (attempt count) is 1.
- Bad: queue drained (loop exited) and a submit arrives before the terminal
  write — it must wait and open a new job, never attach to a job nobody is
  executing.

### 6. Tests Required
- `tests/test_quality_service.py`: append while running (codes/total/queued_at,
  durable persistence read from a fresh manager), duplicate-only resubmit
  keeps timestamps, failed-code retry while active (recount + `failed_codes`
  cleanup + terminal `succeeded`), FIFO dispatch order, `HERMES_MAX_CONCURRENT`
  respected, fresh-service instance waits for the active job then starts a new
  one, contained resubmit leaves unrelated `per_code` untouched.
- `tests/test_quality_api.py`: append returns 202 same id with updated codes
  and `per_code`; duplicate-only 202 `reused: true`.
- `e2e/screening.spec.ts`: queue panel rows/counts, elapsed tick, per-stock
  disabling, reload recovery, failed retry, query-error resilience.

### 7. Wrong vs Correct
#### Wrong
Rejecting extra codes with 400 while a job runs (users cannot queue work), or
mutating `job['codes']` in the service without going through
`RefreshJobManager.append_codes` (job JSON on disk stays stale; restart loses
the appended work).

#### Correct
Append under the service `_cond`, persist via `append_codes` before
acknowledging, and gate the dispatch loop's exit on the same lock.

## Scenario: active quality queue cancel and reorder (2026-10-29)

### 1. Scope / Trigger
- Trigger: changing `QualityService.cancel_item` / `move_item`, Hermes
  `stop_run`, quality `per_code.item_id` / `position`, or the 评级队列 modal.

### 2. Signatures
- `POST /api/dividend/quality/queue/{item_id}/cancel` → `{per_code, running_count, queued_count}`.
- `POST /api/dividend/quality/queue/{item_id}/move` body `{action: "front"|"up"|"down"}` → the same snapshot.
- `QualityService.cancel_item(item_id, refresh_jobs)` / `move_item(item_id, action, refresh_jobs)`.
- `HermesClient.stop_run(cfg, run_id) -> str`: `POST {base}/p/{profile}/v1/runs/{run_id}/stop`, Bearer, no body.
- `RefreshJobManager.note_quality_cancel(job_id, code, queue_order)` and `note_quality_order(job_id, order)`.

### 3. Contracts
- Mutations target `attempt_id`, never the stock code. A later admission of the same code has a new `item_id`.
- Waiting cancel removes that attempt under `_cond` before any Hermes submit, then `note_quality_cancel` writes the job before the response. If the executor has not attached `progress` yet, do not wait for it.
- Reorder changes only `queued` items, keeps `queued_at` / `started_at`, and persists `queue_order` before ack. New admissions still append at the tail. The dispatcher claims a free `HERMES_MAX_CONCURRENT` slot before `queued` → `running`, so an unsent item stays reorderable.
- Running cancel sets `cancelling` and `cancel_requested`. It stores `run_id` when submit returns. If cancel arrives before `run_id`, send stop as soon as the id exists. Do not hold `_cond` across HTTP.
- `stop_run` HTTP 2xx is accepted only when `status` is `stopping` or `cancelled`. `stopping` is not terminal. Keep the row and the slot until a later GET is `cancelled` (release, no score) or `completed` (publish that result). Timeout, poll errors, and any other stop body keep the row and the slot. Surface `取消请求失败` / `取消结果未确认` on the same row.
- Repeated cancel of the same `cancelling` or `cancelled` item returns the current snapshot. Confirmed cancel bumps `data/quality_cancel_generations.json` and the next admission uses `quality-{code}-{data_date}-{skill_version}-c{n}`. An uncertain submit still uses the unscoped key. A waiting cancel that never called Hermes does not bump the generation.
- The modal renders server `position`, not `queued_at`. First waiting row disables 置顶/上移; last disables 下移. One in-flight action per row. 409 refreshes from `detail.per_code`.

### 4. Validation & Error Matrix
| Condition | Result |
| --- | --- |
| Unknown, stale, or already finished `item_id` | 409 `{message, per_code}` |
| Move an item that is already `running` / `cancelling` | 409，当前快照 |
| Move when already first (`front`/`up`) or last (`down`) | 409 |
| Move action outside `front\|up\|down` | 422 |
| Waiting cancel, job still active | snapshot; item leaves the queue; slot never taken |
| Running stop accepted (`stopping`) | row stays 取消中…; slot held |
| Later poll `cancelled` | row leaves the modal; generation increments |
| Later poll `completed` | valid score kept; not counted as cancel |
| Stop HTTP error, timeout, or 2xx without `stopping`/`cancelled` | row stays; error text shown; slot held |
| Same `item_id` cancelled again while `cancelling` | same snapshot, no second stop success claim |

### 5. Good/Base/Bad Cases
- Good: waiting order A/B/C, front C → C/A/B; up on the new first item is rejected; cancel A → C/B with continuous positions. Next free slot takes the new head.
- Base: running cancel shows 取消中… until Hermes GET is `cancelled`. If the run completes first, the new score is saved and the row leaves the active list.
- Bad: cancel during submit, before `run_id` returns — intent is kept and stop is sent when the id arrives. Stopping local polling is not a successful cancel. A stale `item_id` must not cancel the stock's newer attempt.

### 6. Tests Required
- `tests/test_quality_service.py`: waiting cancel submits nothing; front/up/down and boundaries; stale `item_id`; slot claimed before `running`; cancel-before-run-id; stop refusal keeps the slot; completed-before-cancel keeps the score; confirmed cancel changes the idempotency key.
- `tests/test_quality_api.py`: cancel/move snapshots and 409 with `per_code`.
- `tests/test_hermes_client.py`: `stopping` is not terminal; 2xx without `stopping`/`cancelled` is not acceptance; poll `cancelled` is `HermesRunCancelled`.
- `tests/test_refresh_jobs.py`: quality cancel accounting (see that contract).
- `src/lib/quality.test.ts` and `e2e/screening.spec.ts`: active-only groups, empty state, waiting order/cancel, running cancel lifecycle, request failure still visible, conflict refresh, elapsed time restored after reopen.

### 7. Wrong vs Correct
#### Wrong
Sort the modal by `queued_at`, mark `running` before `semaphore.acquire`, treat `stopping` or a stopped poll as cancel success, or reuse `quality-{code}-{data_date}-{skill_version}` after a confirmed `cancelled` run (Hermes replays that run for 24 hours).

#### Correct
Mutate by `item_id`, persist order and waiting cancellation before ack, and release a running slot only after GET `cancelled` or a real completion. After confirmed cancellation, append `-c{n}` to the next idempotency key.
