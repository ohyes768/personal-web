# Plan

- [x] Read installation, planning, migration, cache, export contracts.
- [x] Add failing direct-source and update regression tests.
- [x] Replace snapshot construction with validated cached directory resolution.
- [x] Adjust planning, update metadata and offline migration; clean dev script.
- [x] Update affected tests/docs, verify on Windows and review direct-link logic. WSL stopped at user request; no further WSL checks.

Design: one validated GitHub source resolver serves plan/install/startup migration. Keep safe legacy staging cleanup only. Cache HEAD remains the shared installed revision; changed HEAD requires update even when link path is stable. List update badges compare checked remote with current cache HEAD, not stale check-time cached_revision.
