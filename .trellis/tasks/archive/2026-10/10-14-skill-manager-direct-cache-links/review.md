# Review

Reviewed installation preview/execution, repository version selection, directory boundary checks, startup migration, legacy cleanup, exports and UI wording.

Resolved: same direct-link path incorrectly skipping pending updates; stale per-member checks suggesting older repository revisions; sibling badges retaining old cached version; unmigrated snapshots needing stale indication; a deleted member preventing healthy members from installing.

No remaining blocking issue identified in code review. Frontend type check/lint and 37 tests pass. Final targeted Windows backend regression: 20 pass, 7 true-symlink tests skipped; compileall passes. Earlier full Windows run had 200 pass / 20 skip / one transient WinError 5 rename failure, which passed independently. WSL run was interrupted at explicit user request and is not counted as a completed validation. NAS runtime not touched.
