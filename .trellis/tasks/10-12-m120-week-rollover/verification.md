# Verification

- Initial regression run: 8 failed, 3 passed. Reproduced missing historical M120 data and Sunday execution of numeric `6`.
- Status regression before endpoint fix: 1 failed, 11 passed; fallback data existed but last_updated was null.
- Final checks: 39 passed, 3 live-market cases deselected. Includes snapshot rollover, CSV paths, M120 price merging, status behavior and scheduler jobs.
- Command (from backend/dividend-select): `python -m pytest tests/test_m120_rollover.py tests/test_csv_path_service.py tests/test_m120_service.py tests/test_status_needs_update.py tests/test_scheduler_jobs.py -q -k 'not get_realtime_prices_batch_single and not get_realtime_prices_batch_multiple and not get_m120_from_aliyun' --basetemp=F:/personal-projects/personal-web/.tmp/pytest-m120-final-2`
- Existing local requests dependency warning remains; no market network requests are needed for these checks.
- Implementation and source review complete. Git commit, push and production deployment have not been performed in this turn.
- Deployment must rebuild/restart dividend backend and verify `/api/dividend/scheduler/jobs` next weekly run is Saturday 02:00 Shanghai. Confirm `/api/dividend/m120/status` and preserved historical snapshot timestamps.
- Unrelated nginx, housing-map and RSS changes are untouched.
