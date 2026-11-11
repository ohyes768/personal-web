# Valuation (four-level price levels via Hermes)

## 1. Scope / Trigger
Applies to the dividend-select favorites-tracking valuation pipeline: the
`stock-four-level-valuation` skill (automation JSON mode), `valuation_service`,
`valuation_version`, the `/valuation/*` routes, the alerts/enabled toggle, and
the FavoritesTrackingTab UI. Triggered whenever the skill output contract,
idempotency scheme, apply/monitor semantics, or delivery mode changes. The
skill source lives in `F:\personal-projects\skills\investment-analysis\stock-four-level-valuation\`
(v1.0.0) and must be published into the Hermes profile via skill-manager before
`HERMES_VALUATION_SKILL_PATH`/`HERMES_VALUATION_SKILL_VERSION` is configured.
A local skill checkout is never proof of deployment.

## 2. Signatures
- `POST /api/dividend/valuation/analyze`: `{codes: string[]}` → 202 job (kind
  `valuation`); 503 when Hermes is unset or closing; 400 when codes are outside
  the collected pool or the previous job is in its admission-drain window past
  the wait deadline; 422 for empty/invalid codes. Active valuation job + new
  codes → `RefreshJobManager.append_codes` (reused=true, durable before ack);
  queued/running codes are idempotently skipped without resetting timestamps.
- `GET /api/dividend/valuation/jobs/{job_id}`: valuation job + per_code, or 404.
- `GET /api/dividend/valuation`: `{total, reports: {code: record}, per_code,
  hermes_configured, current_skill_version}`. `per_code` is in-memory
  (queued/running/completed/failed + attempt_id/position), cleared on restart;
  job is marked interrupted, saved reports persist.
- `POST /api/dividend/valuation/{code}/apply`: `{evaluated_at}` → writes
  favorites alerts `{enabled: true, levels: <report four prices incl. pe/pb>}`
  and returns the favorites response. 404 without report or favorite; 409
  `{message, evaluated_at, status}` when the report identity is stale; 400 when
  status is not `ready`.
- `PUT /api/dividend/favorites/{code}/alerts/enabled`: `{enabled}` → flips
  `alerts.enabled` only (levels preserved). 404 not favorited; 400 no alert
  levels configured.
- `GET /api/dividend/refresh/jobs?kind=`: pattern is
  `^(m120|financial|quality|valuation)$` (2026-11-11: quality/valuation added so
  mount-time job rediscovery works; previously quality rediscovery silently 422'd).
- `ValuationService.submit_valuation(codes, cfg, stocks, data_date, refresh_jobs,
  quality_scores, submit_run_fn, poll_run_fn, market_snapshot_fn) -> job | None`.
- `parse_valuation_output(raw, code, name) -> ValuationReport` (pydantic).
- `build_valuation_payload(stock, quality_record, market_snapshot) -> dict`,
  `build_prompt(payload, skill_version, data_date) -> str`.

## 3. Contracts
- Skill output is a single bare JSON object with exactly 17 fields
  (`schema_version/skill_version/code/name/currency/as_of/status/levels/
  valuation/evidence/data_gaps/confidence/risks/invalidation_conditions/summary/
  analysis/report_md`). `status` ∈ ready/insufficient_data/blocked/not_applicable.
  Only `ready` carries `levels` (four keys heavy_position < add_position <
  reduce_position < full_exit, positive strictly increasing prices, each
  `{price, pe, pb}`) and a non-empty `valuation`. Non-ready reports have
  `levels`/`valuation` null; the backend normalizes all-null level dicts to null
  and never synthesizes prices for non-ready results. Parsing tolerates
  ```json fences and stray prose; a reported `code` differing from the request
  is a per-stock failure (identity error), missing code/name are backfilled.
- `analysis` must contain exactly business/normalization/dividend/valuation/risk
  non-empty sections; `evidence` entries keep the skill contract (unique id,
  known kind, verification present) — deep semantic review stays with the skill
  finalize/check step, the backend does light structural validation only.
- Persistence: `data/valuation_reports.json` `{code: {…17 fields, evaluated_at,
  data_date, analysis_duration_seconds}}`, merged under a file lock and written
  via `atomic_write` after each stock. A re-evaluation replaces the record with
  a new `evaluated_at`; the compare-old/new duty lives in the UI (report modal
  compares against current alerts levels), the backend keeps only the latest.
- Idempotency key `valuation-{code}-{data_date}-{skill_version}`; `data_date`
  is the financial summary mtime (same helper as quality). Without a deployed
  version the key degrades to `unknown-{attempt_id}` and version comparison is
  skipped. A mismatched/missing output version fails that stock without
  overwriting previous reports.
- Prompt names the skill, demands bare JSON, declares the expected deployed
  version, and marks inline materials: the stock payload (financial facts),
  an optional `existing_quality_rating` block (reusable evidence only — scores
  must never be mapped to prices), and `market_snapshot` (realtime/close/pe/pb,
  nullable) explicitly labeled as reference-only so the model cannot scale
  levels off the current price. Admission snapshots payloads; later data
  refreshes never mutate queued work.
- Application is user-confirmed and identity-checked: `evaluated_at` must equal
  the stored report; failures, non-ready results and stale applies never touch
  favorites alerts. Applying writes enabled=true and the four prices with
  pe/pb — the AlertService monitor then treats it like any hand-configured
  alert. Pause/resume flips `enabled` only and is available regardless of how
  the levels arrived.
- FavoritesTrackingTab row states derive from alerts + report + per_code:
  monitoring / paused (effective levels exist), pending_apply (ready report
  newer than `alerts.updated_at`; overlaps monitoring/paused), evaluating,
  failed, not_ready, unevaluated. Filters: 全部收藏 / 待评估 (never-applied and
  no pending report) / 待应用 (pendingApply) / 监控中 / 已暂停. Bar semantics:
  effective bar (≥2 levels) solid; candidate bar dashed with the
  「评估结果 · 未启用监控」badge for a first ready report; single-level configs
  render text instead of a bar; nothing renders without prices. Out-of-range
  current prices show 低于重仓线/高于全卖线 with edge arrows; missing realtime
  and close show 现价缺失.
  Price bar layout (2026-11-11 revised after user review: 248px read as too
  narrow, now 400px inside the table column): explicit layers instead of
  ad-hoc absolute offsets — row1 four level prices + current price label
  (staggered when close), row2 track + four clickable dots (click shows the
  dividend yield at that price) + current-price marker, row3 per-level PE
  (omitted entirely when no PE data), row4 zone names that fit, row5 current
  zone plus distance to each level. Labels never collide: price/PE rows
  stagger independently and threshold positions map to [8, 92] so edge labels
  are not clipped.

## 4. Validation & Error Matrix
| Condition | Result |
| --- | --- |
| Hermes base/key unset | 503 |
| Code outside collected pool | 400，采集池文案 |
| Active job, new codes | 202, same job, reused=true, durable append |
| Active job, duplicate-only | 202, reused=true, timestamps unchanged |
| Run failed / parse failed / version mismatch | per-stock failure, report untouched |
| Non-ready report | saved with null levels/valuation; apply → 400 |
| Apply with stale evaluated_at | 409 + current identity; alerts unchanged |
| Apply unfavorite / missing report | 404 |
| Toggle enabled without levels | 400；未收藏 404 |
| Service restart | job interrupted, per_code cleared, saved reports kept |

## 5. Good/Base/Bad Cases
- Good: first ready report → candidate bar + 确认后开启监控 → apply writes four
  prices, monitoring on; re-evaluation later → 监控中 + 新评估待应用 overlap,
  old levels keep monitoring until confirmed.
- Base: insufficient_data report → reasons readable, no prices, no apply;
  retry available; old alerts untouched.
- Bad: applying a stale report after a newer evaluation completes — must 409,
  never overwrite the newer result or the old config.

## 6. Tests Required
- `tests/test_valuation_service.py`: 17-field validation (ready/non-ready/
  identity mismatch/fence tolerance/levels ordering/evidence duplicates),
  duration persistence, FIFO append while running, duplicate-only idempotency,
  failed poll, version mismatch keeps old reports, idempotency key shape,
  restart interruption.
- `tests/test_valuation_api.py`: analyze 202/503/400/422, GET /valuation,
  apply success/stale 409/non-ready 400/not-favorited 404, enabled toggle,
  failed evaluation never touches alerts.
- `e2e/favorites-tracking.spec.ts`: filter counts and overlap semantics,
  effective/candidate/single-level/hidden bar states, apply flow with identity,
  stale 409 dialog, non-ready gaps, pause/resume, out-of-range/missing price,
  narrow-viewport overflow.
