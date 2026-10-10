# Verification
- Backend: python -m pytest tests/test_screening_service.py tests/test_financial_fetcher.py tests/test_screening_financial_status.py tests/test_status_needs_update.py -q --basetemp=F:/personal-projects/personal-web/.tmp/pytest-profit-final : 93 passed in 1.16s.
- Frontend: node node_modules/typescript/bin/tsc --noEmit : exit 0.
- Storage: node --experimental-strip-types --test src/lib/screening.test.ts : 4 passed.
- Browser: node node_modules/@playwright/test/cli.js test e2e/screening.spec.ts --reporter=line : 5 passed (20.3s).
- git diff --check : clean.
# Review
Verified source -> latest annual CSV amount/year -> missing-safe reader -> stock API -> screening -> frontend types/display; new request default and snapshot; threshold storage/reset/change notice. No additional gates introduced. Finite severe quarter in adjacent pair wins missing peer; nonadjacent remains insufficient. Annual amount <=0 cannot pass by shrinking losses.
# Environment
Sandbox Next async realpath EPERM and backend TestClient hang resolved by permitted unsandboxed test runs. Existing requests dependency warning and Node module-type warning do not fail checks. No package/lock changes.
# Migration
Old cache lacks 最近年度扣非净利润(元) and 扣非利润年度: perform full-pool force=true financial refresh, then rerun screening. Missing source data stays insufficient. Old localStorage automatically supplies threshold30 while preserving prior conditions.
