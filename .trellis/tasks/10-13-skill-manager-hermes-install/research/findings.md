# Repository findings (2026-10-13)
- RegisterGithubDialog.tsx currently separates scan and register; SourceWorkspace.tsx separately handles queue/plan/password publish. This is the avoidable navigation gap.
- routes.py publish_plan accepts existing registered IDs only; new candidate preview requires transient definitions, not early registration.
- _publish_one currently resolves GitHub revision from latest successful check record via _ensure_cached_at_recorded_revision. A new confirmed plan must pin version explicitly to avoid installing a different revision after confirmation.
- config.py requires both roots; docker-compose.nas.yml requires OPENCLAW_SKILLS_HOST_PATH mount/env. UI-only removal would not remove runtime dependency.
- LINK_TARGET_IDS distinguishes link installations from dynamic exports; removing openclaw without legacy migration may accidentally classify its records as exports.
- SQLite deployment and deployment_history hold target as raw TEXT, enabling legacy processing before typed API serialization.
- Current GitHub staging remains per skill; collections are display grouping only. Repo pack/symlink experiments have separate tasks and must not silently return in this change.
- Existing task manager is memory based. Background installation must state restart and deduplication limits, not promise durable workflow recovery.
- Trellis package catalog omits skill-manager; task was created without package argument. Explicit relatedFiles/scope identify actual modules rather than adding package specs during planning.
