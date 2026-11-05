# Implementation

1. Add regression tests for removed endpoints, daily scheduler registration/lifecycle and application refresh ownership; verify initial failures.
2. Remove sending services, wiring and obsolete APIs/config; keep historical reads and Web refresh.
3. Replace obsolete report-generation tests; update README, deployment comments and coding specs.
4. Run index-trends backend offline suite, frontend type-check and build if types change, plus git diff --check.
5. Record verification; do not deploy or commit without a new request.
