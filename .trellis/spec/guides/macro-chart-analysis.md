# Macro chart-analysis contracts

## Scope / Trigger
Changes to apps/macro's chart explanation drawer, paid model endpoints, raw evidence snapshots, unlock cookies, or expansion to daily charts. First implementation: China government bonds, 2026-10-10.

## Signatures
Public backend prefix `/api/analysis`, browser/nginx prefix `/api/macro/analysis`:
- GET `/charts` → `{charts:[{id,title,description,series_ids,series:[{id,label,unit}],version}]}`.
- GET `/auth` → `{unlocked,configured,model_ready}`; no-store.
- POST `/auth/unlock` `{password}` → HttpOnly, SameSite=Strict cookie, max-age=604800.
- POST `/auth/lock` → revoke current unlock identity and cancel its sessions.
- POST `/sessions` `{chart_id,start_date,end_date}` → `{session_id,snapshot,expires_in,schema_version}`; does not call the model.
- POST `/sessions/{id}/messages` `{request_id,message}` → fetch-readable SSE: meta/delta/done/error.
- GET or DELETE `/sessions/{id}/requests/{request_id}` → result status or cancellation.

## Contracts
`ChartContext` supplies stable chart and curve IDs, transforms/units and visible dates. `MacroEChart` separately fingerprints source display data and curve definitions for stale-answer reminders; the provider also tracks manual refresh revisions. The provider tracks each chart independently; linked panel callbacks must not replace the selected chart. Hiding a legend does not remove analysis membership. Register expected curves in the backend even when all-null series disappear from rendering.

Settings: ANALYSIS_PASSWORD, ANALYSIS_SIGNING_SECRET, ANALYSIS_COOKIE_SECURE (true in HTTPS production), DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL, ANALYSIS_TIMEOUT_SECONDS. No service key/password in frontend bundles or logs. Unlock signing key depends on the configured password; changing password invalidates old cookies. Revocations are in-memory; rotate password/key for cross-restart revocation. Credentials are not reused as model credentials.

Snapshots use `DataService.load_analysis_observations(stores)`, with file signatures before/after the whole read. Read errors or concurrent changes are 503, not empty history. Never ffill observations. China store columns are **中国10y** and **中国10年-2年**, not AKShare's original long names. cn_2y is derived only on common dates. Shared endpoints decompose spread changes using common dates; numeric difference is pp, bp = pp × 100. Other units have change_value, not fabricated bp.

Code computes full-observation statistics. Model observations may be sampled, explicitly marked, with endpoints retained. Snapshot fingerprint ignores generated_at but includes actual values/statistics and chart definition version. First-turn evidence plus completed conversation history are the model context; no arbitrary tool execution. Partial/canceled/failed answers never enter history. Only content is shown, not reasoning_content.

Session defaults: idle 30m, absolute 2h, max 100 sessions, 10 completed turns, 30 request records, global 2 active generations, max 2000 characters/question. Auth and generation are throttled. Sessions belong to signed unlock identities. request_id deduplicates model calls; repeated requests replay events/results. Cancel status must be set before task.cancel(), including cancellation before coroutine startup. Store mutations that may cancel tasks execute on the event loop, not sync FastAPI worker threads.

Production analysis nginx location must preserve **$http_host**, including public port; $host strips the port and breaks Origin checks on e.g. :9443. Disable buffering/cache/gzip for the stream and keep read timeout beyond application timeout. Heartbeat every 10s; only done commits an answer.

## Validation & Error Matrix
| Situation | Behavior |
|---|---|
| No valid unlock | 401 |
| Foreign Origin | 403 |
| Another unlock identity's session | 404 |
| Expired/unknown session | 410, reanalyze |
| Unsupported chart/no observations | 422 |
| Existing active generation | 409 |
| Rate/capacity limits | 429 |
| Unconfigured model or corrupt/changing CSV | 503 |
| Stream timeout/truncation/upstream failure | error event, sanitized message, no history append |
| Changed chart range/data | stale reminder, keep old snapshot until explicit reanalysis |

## Good / Base / Bad Cases
Good: rates.china-bonds includes cn_10y/cn_10y_2y, derived cn_2y and separate dr007 reference, all dated.
Base: DR007 missing, China observations still analyzed with missing reference shown.
Bad: calling query_data's filled display arrays “raw observations”, inferring causality from correlation, or using all rates subplots as one analysis target.

## Tests Required
Backend `tests/test_chart_analysis.py`: unlock expiry/password change/origin/revocation/throttling, common-date decomposition, missing/corrupt/concurrent data, fingerprint updates, second configurable chart/non-rate unit, idempotent SSE, session isolation, timeout/failure/cancel/early cancel/concurrency. Frontend `analysis/api.test.ts`: UTF-8/frame splits, CRLF/heartbeat, incomplete/error stream. Run existing ECharts tests, tsc and production build; browser checks password, refresh, linked zoom/reset, hidden legend, follow-up, cancel, 375px/1440px. Real model and production nginx checks require deployment configuration; do not claim them from fake-model tests.

## Wrong vs Correct
Wrong: calculate cn_2y on independently filled dates or choose analysis target from the most recent linked callback.
Correct: derive cn_2y on joint raw dates; keep Map<chartId,context>, activate the user's clicked chart explicitly.

## Fixed daily chart expansion (2026-10-10)
The registry now covers all 15 fixed daily panels (rates, treasury/FX, liquidity, commodities, stock indices, sentiment and fund flow). Dynamic ComparisonChart and monthly panels are not registered. MacroEChart discovers actions from the server list; do not duplicate per-Tab assistant integrations. Shortcut questions must use the active definition's series, with DR007 reference prompts only on China bonds.

`SeriesDefinition.is_rate` gates bp (turnover uses pp only); `relative_change` permits interval percentage changes for FX/prices/stock indices only with positive observations. Flows and balances are not returns. Each primary evidence item declares raw store/column and source_as_of; interval end and latest source date are distinct. Common-date summaries align all expected primary curves without forward filling; disclose short/missing common windows.

FX evidence remains raw: interval percentage changes start at each series' first interval observation and may differ from the renderer's pre-zoom baseline. Never label them chart-axis values. TGA source is million USD; displayed hundred-billion USD uses 1e-5. The TED-labelled stored spread is SOFR minus Treasury 3M, not traditional LIBOR TED. Northbound turnover is not net buying.

Regression checks verify every registered panel against CSV data, exact frontend panel IDs, missing expected members, independent calendars, turnover pp/bp, relative-change baselines, source freshness and first-turn input budget.
