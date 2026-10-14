# Progress

- Direct resolver, installer, legacy publish API and offline startup migration now use repository directories. Snapshot generation removed; legacy cleanup retained. Dev script OpenClaw env/mkdir removed.
- Update planning compares shared cache revision even for unchanged link paths; latest successful repository check is reused across siblings. List versions reflect live cache HEAD, and dangling links are abnormal.
- Removed resource-copy state/UI from RegisterGithubDialog; install confirmation explains that shared repository updates affect installed siblings. Compatibility metadata remains accepted.
- Red/green verified: missing resolver import, stale sibling check regression and resource-copy UI regression failed before implementation, pass afterward.
- Windows full backend: 200 passed, 20 skipped, 1 transient WinError 5 directory-rename failure; the failing test passed independently. Latest direct suite: 9 passed, 3 real-symlink cases skipped.
- Frontend: tsc and lint pass; 37 tests pass. WSL initially blocked by approval-service quota, retried after reset, then explicitly interrupted at user request. Do not claim a completed Linux run; do not start further WSL checks.
- Code review found that checkout deleting one selected member could prevent other healthy members from installing. Added red/green tests for deletion of first or later member; cache fingerprints now refresh even when the checkout's selected path validation fails, while each unavailable member retains registration and fails independently.
- Final fast backend regression: 20 passed, 7 skipped (true symlink privilege); compileall succeeds. Startup migration, legacy snapshot cleanup, direct source validation and export compatibility reviewed. No commit/push or NAS deployment performed.
- Existing unrelated workspace edits belong to parallel tasks; do not stage or overwrite them. User requested no further commits until work is ready.
