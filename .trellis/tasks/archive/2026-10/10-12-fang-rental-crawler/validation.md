# Validation — 2026-10-12

- New tests first failed with missing implementation; layout regression subsequently failed (title 3室 overriding structured 3室2厅), then passed after correction.
- `python -m pytest tests/test_fang_rentals.py tests/test_tmsf_fetcher.py -q --basetemp=.pytest-tmp-fang-final`: 18 passed.
- CLI `--help` succeeded.
- Online CLI with communities 2011095896 and 2010067741, max-pages=1, details=true: 2 lists + 8 details, 8 samples, 0 errors. Outputs at `.tmp/fang-rentals-final/`.
- Confirmed 璞悦湾 89㎡ / 6400元/月 / 3室2厅 / 住宅 and address; shared rentals marked separately.
- Existing curl_cffi + TMSF text decoding reused. No new dependency, price/API/frontend/scheduler changes.
- Limitations: source-ID dedup only; missing publish dates stay null; split-rental keyword flags require review; listing counts are not market coverage guarantees.
- No commit requested; changes retained for review.
