# index-trends backend

## Pre-Development Checklist

- Read [Weekly pipeline contract](./weekly-pipeline.md) before changing weekly data
  fetching, validation, model fitting, publishing or snapshot ids. It defines the
  week key, the trading calendar, the model kinds and the daily refresh boundary.
- Read [Valuation contract](./valuation-contract.md) before changing the lixinger
  provider, the valuation tables or the status payload.
  It defines the target date, the state machine and the credential boundary.
- Keep the monthly pipeline (`TrendService`, `monthly_bars`, `models`) untouched:
  it is a legacy archive, not a fallback for the weekly path.
- Never let a supplier failure change the market pipeline semantics: the trend
  refresh result and the chart keep their own success/failure
  contract.
- Web owns daily market/valuation collection (weekdays 16:30 Asia/Shanghai), manual
  refresh and startup valuation initialization. Hermes owns brief generation,
  scheduling and delivery; do not reintroduce DingTalk/webhook or report catch-up.
- Preserve report/settings/attempt tables and GET /api/reports as legacy history.
  Report configuration and job-trigger APIs are retired (404).

## Quality Check

- `cd backend/index-trends && uv run pytest -q` (offline suite; the provider tests
  use synthetic fixtures and never touch the network).
- Related frontend: `cd apps/index-trends && node --experimental-strip-types --test lib/candleData.test.ts`,
  `./node_modules/.bin/tsc --noEmit`, `npm run build`.
- This package has no lint script — never report "lint passed".
- New supplier code must ship with an offline test that proves: no token means no
  request, error messages carry no token or upstream body, and missing values stay
  `null` (never `0`).
- `tests/test_refresh_lifecycle.py` verifies daily-only scheduling, bounded task
  shutdown, valuation collection after market failure, and legacy report retention.
