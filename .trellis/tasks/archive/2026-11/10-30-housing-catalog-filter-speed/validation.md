# Validation

- Cache tests first: 12 expected failures because repeated reads rebuilt projections; 2 existing invalidation cases passed.
- Backend focused initial run found an in-memory migration preview sharing the live disk path. Bypassed disk caches for nonstandard registry implementations; rerun 69 passed.
- Full backend run: 1277 passed, 1 failure due Windows PermissionError while reading a concurrently replaced rental job file. Targeted rerun of rental-refresh and all new cache/index tests: 39 passed.
- New frontend effect test first failed because a classification filter repeated the summary request. After splitting effects, it passes.
- Frontend full suite: 186 passed. An existing position-status assertion also failed with the HEAD component: it incorrectly rejected explanatory text containing 跳过. Scoped that assertion to the result status line.
- Frontend lint and TypeScript checks: exit 0.
- Production build: default Turbopack failed spawning its CSS worker in the Windows sandbox. Webpack compiled, type-checked and generated pages, then standalone packaging failed on Windows symlink permissions. No successful complete production build claimed.
- NAS: only a temporary diagnostic directory and a copy of the original service file were created. The interrupted upload left services/ empty. Live backend explicitly reports LIVE_CACHE_NOT_INSTALLED. No rollout or measured performance improvement claimed.

Other chats changed/committed overlapping frontend files during this session. Commit must stage only the summary/list loading hunks from DirectoryFlowWorkspace.tsx and the projection-reuse section of directory-flow.md; do not include the independent TMSF detail update work.
