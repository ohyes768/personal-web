# Implementation plan (planning only)

1. Review PRD/design and confirm scope. Inspect latest dirty files and concurrent skill-manager tasks; re-read applicable spec and package scripts. Start only after user approves implementation.
2. Backend Hermes-only target model and migration: reserve retired ID, raw legacy parsing, backup/archive active records, remove mandatory OpenClaw config and mounts. Test old DB/startup/export classification/deletion blocking before removing typed enum support.
3. Extract reusable registration/plan/publish service; implement candidate source-identity deduplication, version-pinned preview, expiring plan/request IDs, repo/target locks. Reuse staging and publisher checks.
4. Add background install endpoints and task phases, credentials validation, partial registration/install results, retry and restart behavior. Cover no-double-install and no-auto-version-switch regressions.
5. Shared frontend installation dialog: automatic plan, one confirmation, invalidation and progress. GitHub scan selection connects directly; local single/multiple install connects directly; collection all uses full membership. Keep advanced resource/metadata options.
6. Remove OpenClaw UI, normal queue step and obsolete client targets; installation board becomes Hermes. Normalize legacy agent URLs; preserve static exports and existing safe unpublish.
7. One-time managed-link cleanup command with dry-run report; test matching links, foreign/modified links, plain files, missing root, interrupted cleanup and re-run. No real NAS writes during development.
8. Update deployment docs/environment templates/current specs. Explain rollout order, backups, physical-link cleanup and rollback; retain historical task evidence.
9. Validate backend full pytest, frontend package-defined tests/type-check/lint/build and compose configuration with only Hermes settings. Linux/macOS isolated directory link tests; don't infer real symlink behavior from mocked browser tests.
10. Browser verification desktop/mobile: new GitHub install, already registered member, multi-select/resource edit, local install/update, collection all under filter, stale plan, partial failure/retry, wrong password, missing cache and restart. Verify Hermes installed content matches pinned revision and exports still work.
11. Final review, record evidence, update spec; propose scoped commits after implementation. Deployment and external cleanup are separate actions, not performed by this planning task.

## Acceptance gates
- Functional: both source flows have one final confirmation, no target selection or queue diversion.
- Safety/data: wrong password/expired plan no writes; legacy records never become exports; controlled links only; exactly confirmed revision.
- Reliability: concurrency/idempotence, partial success, registry/install split and restart recovery.
- Compatibility: old state and OpenClaw-free configuration start; Hermes links and export targets intact.
