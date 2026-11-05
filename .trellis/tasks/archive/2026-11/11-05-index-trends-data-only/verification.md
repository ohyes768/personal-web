# Verification (2026-11-05)

- Initial new regression run: 9 failures demonstrated the report endpoints and weekly job still existed.
- Final backend offline suite: `.venv/Scripts/python.exe -m pytest -q` in backend/index-trends: **200 passed**, one existing Starlette/httpx deprecation warning.
- New lifecycle coverage: daily-only registration, custom cron/timezone, graceful drain and timeout cancellation, startup valuation initialization, all combinations of market/valuation success and failure, historical rows/settings preserved across restart.
- Frontend: `node --experimental-strip-types --test lib/candleData.test.ts`: **9 passed**; `./node_modules/.bin/tsc.cmd --noEmit`: passed.
- `npm run build`: passed. Initial sandboxed build emitted a Windows standalone-copy permission warning; rerunning with normal host permissions completed successfully without that warning. npm still reports the existing unknown node-linker configuration warning.
- NAS Compose parsed with PyYAML; index-trends no longer injects webhook or report URL/cron settings; Lixinger token configuration retained.
- `git diff --check`: passed.
- Production was not changed. Backend rebuild/deployment is required to stop the previously deployed weekly sender. No Hermes schedule/delivery setup was performed.
- User requested commit and push after reviewing the completed implementation.
