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
  `HERMES_BASE_URL`/`HERMES_API_KEY` unset; 400 for codes outside the collected
  pool, or when an active quality job exists and this request contains any code
  outside that job (`detail` includes `已有评级任务在跑`); 422 for non-six-digit
  codes or an empty list. An active quality job is reused (`reused: true`) only
  when every requested code is already in that job. `RefreshJobManager` itself
  still reuses any same-kind active job; the extra-code rejection lives in
  `QualityService.submit_analysis`, so m120/financial admission is unchanged.
- `GET /api/dividend/quality/jobs/{job_id}`: quality job or 404 (also 404 for
  non-quality kinds).
- `GET /api/dividend/quality`: `{total, scores: {code: QualityScore},
  per_code, hermes_configured}`; `GET /quality/jobs/{job_id}` also embeds
  `per_code`. `per_code` is the in-memory per-stock live status
  (`{state: queued|running|completed|failed, error, updated_at}`), cleared on
  restart. `queued` is written only after a quality job is actually accepted
  and its `work()` starts, and only for that job's codes — a reused submit
  must not clear or rewrite `per_code`. The ScreeningTab action column renders
  it row-by-row
  (排队中/评级中 pulse, 失败+原因 tooltip+重试, else 分析/重评 buttons).
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
`quality-{code}-{data_date}` where `data_date` is the financial summary file
mtime date (fallback: today), so re-runs on the same data day reuse the run.

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
```json fences and stray prose around the object. In the screening list's
「评级结果」column, rated stocks show the 1-decimal weighted_score (e.g. `3.4`)
alongside the `boundary` ⚠️ flag; parsed-but-unrated stocks show 「未评级」
(still opens the report modal, which shows 未评级 instead of stars and
「未评分」 per null dimension); `-` still means never rated. The rating report
modal itself still shows no weighted score. (Changed 2026-10-24: the previous
"never shown to users — ordinal false precision" rule is superseded. Changed
2026-10-27: v3 null contract adopted; the in-repo skill copy
`backend/dividend-select/skills/basic-quality-rating/SKILL.md` was removed
after drifting stale — the skills repo
`F:\personal-projects\skills\finance-macro\basic-quality-rating\` is the
single source, installed into Hermes via skill-manager.)

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

## Scenario: quality job admission mutex

### 1. Scope / Trigger
- Trigger: changing `QualityService.submit_analysis`, quality `per_code`, or
  `POST /quality/analyze` behavior while another quality job is active.

### 2. Signatures
- `QualityService.submit_analysis(...) -> job | None`
- Active same-kind check uses `refresh_jobs.active("quality")` before any
  `per_code` write. Do not change `RefreshJobManager.submit` reuse rules.

### 3. Contracts
- No active quality job: accept, then `work()` overwrites `per_code` to
  `queued` for this request's codes only.
- Active job whose `codes` contain every requested code: return that job with
  `reused: true` and do not touch `per_code`.
- Active job missing any requested code: `ValueError` whose message contains
  `已有评级任务在跑`. The route maps that to HTTP 400 `detail`. The running
  job and its `per_code` stay as they were.
- Frontend `useQualityAnalysis` already surfaces `detail` as `qualityMessage`.

### 4. Validation & Error Matrix
| Condition | Result |
| --- | --- |
| Hermes base/key unset | 503 |
| Code not in collected pool | 400，采集池文案 |
| Active quality job, request codes are a subset | 202, same `job_id`, `reused: true`, `per_code` unchanged |
| Active quality job, request has a code outside it | 400，`detail` 含「已有评级任务在跑」，`per_code` 不变 |
| Accepted job | only this batch flips to `queued`, then `running`, then `completed`/`failed` |

### 5. Good/Base/Bad Cases
- Good: no active job, two codes finish `completed`.
- Base: resubmit a code already inside the running job; same id, no extra `queued`.
- Bad: running job is `000001`, request is `000001+600519`. Must 400. A previously `completed` code outside the batch must remain.

### 6. Tests Required
- `tests/test_quality_service.py`: extra codes raise `ValueError` and `per_code` is unchanged; contained resubmit is `reused` and does not leave a ghost `queued` or wipe unrelated codes.
- Existing quality API reuse test still expects same-code resubmit to return 202 `reused: true`.

### 7. Wrong vs Correct
#### Wrong
Clear `_per_code` and write `queued` in `submit_analysis` before `refresh_jobs.submit()`. An active job makes `submit()` return the existing job without running `work()`, so the clear is never repaired and new codes stay `queued` forever.

#### Correct
Reject extra codes before writing status. Write `queued` at the start of `work()`, only for this job's codes.
