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
  pool; 422 for non-six-digit codes; active kind job is reused (`reused: true`).
- `GET /api/dividend/quality/jobs/{job_id}`: quality job or 404 (also 404 for
  non-quality kinds).
- `GET /api/dividend/quality`: `{total, scores: {code: QualityScore},
  per_code, hermes_configured}`; `GET /quality/jobs/{job_id}` also embeds
  `per_code`. `per_code` is the in-memory per-stock live status
  (`{state: queued|running|completed|failed, error, updated_at}`), cleared on
  restart; the ScreeningTab action column renders it row-by-row
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
int), `weighted_score` (= dimensions × 0.25/0.25/0.20/0.15/0.15, tolerance
±0.01), `stars` (mechanical mapping ≥4.5→5, ≥4.0→4, ≥3.0→3, ≥2.0→2, else 1),
`boundary` (set when within 0.25 of a tier edge), `summary`, `risks`,
`watch_points`, `report_md` (non-empty Chinese markdown). Parsing tolerates
```json fences and stray prose around the object; pydantic rejects
weight/star/report mismatches as a per-stock failure. `weighted_score` is
shown to users in the screening list's 「评级结果」column as a 1-decimal
number (e.g. `3.4`) alongside the `boundary` flag; stocks without a score
show `-`. The rating report modal itself still shows stars + dimensions and
no weighted score. (Changed 2026-10-24: the previous "never shown to
users — ordinal false precision" rule is superseded.)

Bulk analysis reuses `RefreshJobManager` with `kind='quality'` (included in
`_prune` kinds). Each stock is one worker thread bounded by a semaphore
(`HERMES_MAX_CONCURRENT`, default 4); a failed poll/parse marks only that
stock failed. Scores persist to `data/quality_scores.json`
(`{code: {…score, scored_at, data_date}}`), merged under a file lock and
written via `atomic_write` after each stock completes.

Hermes config comes from env only: `HERMES_BASE_URL`, `HERMES_API_KEY`,
`HERMES_PROFILE` (default `ohyes768`), `HERMES_POLL_INTERVAL` (30s),
`HERMES_TIMEOUT` (3600s), `HERMES_MAX_CONCURRENT` (4). Unset base/key keeps
every other feature unchanged (analyze returns 503). The skill source lives
at `backend/dividend-select/skills/basic-quality-rating/SKILL.md` and is
published to the Hermes profile out-of-band (copy to skills source root, then
install via skill-manager); the skill must never embed dividend backend URLs
or schema details. Frontend mirrors the contract in `lib/quality.ts`
(`starsFor` must match the mapping above; `RefreshKind` includes `quality`).
