# index-trends backend

## Pre-Development Checklist

- Read [Weekly pipeline contract](./weekly-pipeline.md) before changing weekly data
  fetching, validation, model fitting, publishing, snapshot ids or the weekly report
  pipeline. It defines the week key, the trading calendar, the model kinds and the
  idempotency key.
- Read [Valuation contract](./valuation-contract.md) before changing the lixinger
  provider, the valuation tables, the status payload or the report valuation line.
  It defines the target date, the state machine and the credential boundary.
- Keep the monthly pipeline (`TrendService`, `monthly_bars`, `models`) untouched:
  it is a legacy archive, not a fallback for the weekly path.
- Never let a supplier failure change the market pipeline semantics: the trend
  refresh result, the chart and the weekly report keep their own success/failure
  contract.

## Quality Check

- `cd backend/index-trends && uv run pytest -q` (offline suite; the provider tests
  use synthetic fixtures and never touch the network).
- Related frontend: `cd apps/index-trends && node --experimental-strip-types --test lib/candleData.test.ts`,
  `./node_modules/.bin/tsc --noEmit`, `npm run build`.
- This package has no lint script — never report "lint passed".
- New supplier code must ship with an offline test that proves: no token means no
  request, error messages carry no token or upstream body, and missing values stay
  `null` (never `0`).
