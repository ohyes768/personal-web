# Technical design

## Baseline
Frontend SourceWorkspace currently manages a per-source queue, plan preview and PublishRequest. RegisterGithubDialog scans and registers separately. Local skills are synchronized into SQLite automatically. Publisher already provides safe per-skill links; GitHub publishing stages skill content plus shared_paths. Reuse these services; do not introduce repo-pack semantics.

## User flows
- GitHub add dialog: URL → scan progress → candidate selection and advanced metadata/resources → automatic read-only install preview → one password confirmation → background progress/results. No separate registration step.
- Local management: single Install/Update or multi-select Install → same automatic preview and confirmation → progress/results.
- Registered GitHub collection/card: Install/Update → same dialog. “All” uses complete registered membership; scanning adds newly discovered members.
- Installation board is Hermes-only. Static export management remains a separate view. Remove normal-flow queue component; share selected items and install dialog across sources rather than duplicate flows.
- On selection changes invalidate preview immediately. Password stays request-local, never in task snapshots, URLs, browser storage or logs.

## Install orchestration (proposed contract)
Extract reusable registration, planning and publish operations from API handlers into a service; do not invoke public routes internally or duplicate publisher safeguards.
- POST /api/skills/install/preview: registered IDs OR GitHub scan token + candidate paths + metadata/shared_paths. Server binds the exact normalized selection to a short-lived plan_id. No registry or target writes. Return per-item add/update/unchanged/blocked and pinned revision/content fingerprint.
- POST /api/skills/install: {plan_id, request_id, password}; verify password before mutations, expiry and selection/source state before execution; return 202 {task_id}. Target is server-fixed Hermes, not user-provided.
- GET /api/skills/install/tasks/{task_id}: phases and per-item registration/install status; exclude credentials. Reuse task infrastructure where suitable, introduce a distinct install kind and explicit contracts.
- Retry uses a new preview of failed members only; client request_id deduplicates concurrent/repeated submit. Keep task/request tombstones long enough for retry UI; unknown task after restart returns a clear interrupted/unknown state and refreshes installed facts instead of blindly resubmitting.
- Existing plan/publish APIs may remain internal compatibility helpers, restricted to Hermes, while UI migrates. Do not keep old OpenClaw write routes operational.

## Revision and source consistency
Preview cannot plan unregistered GitHub candidates via the existing ID-only route directly. Use transient validated RegistrySkill definitions, detect existing source identity (repository + path) and ID collisions; matching registered members reuse IDs, conflicts are blocked.
Scan result is tied to shared cache HEAD and candidate paths. Pin that revision in plan; do not allow a newer check-updates record to silently change installed revision. Fetch/checkout when necessary only after password confirmation; acquire repository lock across cache preparation and staging. A moved candidate/shared resource selection requires fresh preview.
Local plan fingerprints content; revalidate before publishing. Preserve current local-link semantics; do not promise immutable local snapshots. Explain local source edits may affect installed links until separately redesigning local staging.
Revalidate before each mutation, lock per skill/target to prevent concurrent install/unpublish races, and preserve publisher controlled-root checks. No rollback across an entire batch: successful members stay installed. Record registration success independently from installation failure; duplicate source identity and request IDs cannot create extra records.
Plans/tasks are bounded and expire, with documented retry/restart behavior. Preview must not clone or fetch; missing cache is blocked with a prepare-cache action before another preview. First scan remains the cache-preparation step for new GitHub additions.

## OpenClaw removal and legacy migration
Remove OPENCLAW enum/target maps, settings root validation, API root mapping, UI labels/counters/filtering/agent navigation, compose volume/env requirements, dev environment samples and current deployment instructions. All removed-target requests return a stable unsupported-target error without filesystem access.
Legacy records cannot be parsed through the new enum. Migration runs against raw SQLite strings before typed reads. Back up database; preserve removed OpenClaw deployment/history evidence in an archive store outside normal active-target queries, then remove active target records transactionally. Mark migration once; verify re-run safe. Reserve `openclaw` as a retired identifier so dynamic export-target creation never reintroduces it or reclassifies old records as exports.
Removing mounts does not remove existing physical symlinks. Ship a separate one-time inventory/cleanup command, run with the old path available before removing mounts. Default dry run; execution affects only paths identified by deployment records whose current value matches the manager-owned link, without following it. Modified/foreign links and regular files are skipped/reported. Never recursively remove OpenClaw roots, GitHub staging, source repo or Hermes links. Keep cleanup evidence alongside migration backup. Planning itself performs no cleanup.
Historical Trellis records remain historical. Remove obsolete OpenClaw references only from current active docs/config/tests; legacy-migration negative tests still need the literal retired ID.

## Deployment and rollback
Order: backup/inventory → guarded legacy link cleanup (when actually deploying) → migrate state/install new build → remove OpenClaw mounts/env → verify Hermes and exports. Coordinate old backend shutdown so no old worker recreates links during cutover.
Rollback code/config with the preserved database backup and migration archive; reinstall intentionally removed links through old tooling if necessary. No automatic deletion of cache/staging or successful Hermes installs as rollback.

## File boundaries
Frontend: page.tsx, targets/types/api/collections/queue, RegisterGithubDialog, SourceWorkspace, SkillPool, DeployBoard, PublishQueue removal, shared InstallDialog/progress hook.
Backend: models/config/db/migration, routes, task_manager, registry/git_cache/publisher integration; add install orchestration/plan storage module and retired-target cleanup utility.
Deployment: docker-compose.nas.yml, environment samples/dev launch config, docs/skill-manager-nas-setup.md and same-path mount docs. Search references within skill-manager scope; avoid deleting unrelated uses of OpenClaw elsewhere in repository.

## Review decisions
Default choices: keep static exports, no normal queue, one final password, per-member partial success, archived audit rather than silent history erasure, managed-link-only cleanup. Review these artifacts before starting implementation.
