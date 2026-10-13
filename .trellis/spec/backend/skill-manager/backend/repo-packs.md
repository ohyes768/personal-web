# GitHub Repository Packs

## 1. Scope / Trigger

GitHub pack/API/install changes in backend/skill-manager and apps/skill-manager.
Replaces per-SKILL registration and staging for current GitHub UI. Local skills
and legacy ZIP APIs retain their contracts.

## 2. Signatures

- GET /api/github-packs -> {items: GithubPack[]}.
- POST /api/github-packs {repository,password,name?,tags?,summary?} -> 202 prepare_pack.
- GET /api/github-packs/tasks/{id} -> TaskSnapshot with result.pack or result.items.
- GET /api/github-packs/{id} -> pack with readonly inventory/diagnostics.
- POST /{id}/check-update -> metadata check without checkout.
- POST /{id}/update {password} -> 202 update_pack.
- POST /{id}/plan {targets:[hermes|openclaw]} -> PackPlan.
- POST /{id}/install {password,targets} -> 202 install_pack.
- DELETE /{id}/targets/{target} {password} -> removed target.
- DELETE /{id} {password} -> remove unreferenced pack.

SQLite github_pack stores validated Pydantic payload and unique repository;
legacy_github_pack_member preserves old IDs/tombstones; github_pack_history is
append-only. Add prepares/registers the whole repository in one authenticated
task; there is no selection step or separate preview token endpoint.

## 3. Contracts

- One pack, one stable repository checkout, one root symlink per Agent. Never
  staging/rev paths or wrapper SKILL.md; rootless repositories are supported.
- Canonical repository and ID digest prevent case/punctuation/owner-boundary
  collisions. Preserve existing cache path casing rather than rename live sources.
- Explicit updates use repository locks, dirty/ancestry/default-branch checks,
  candidate inventory/conflict validation, and fast-forward only. Every linked
  target reads checkout HEAD; update does not replace the link or require publish.
- Old forced-checkout APIs and GitCacheService.ensure_cached reject pack-managed
  repositories. Passwords are removed at HTTP boundary before creating tasks.
- Startup only merges old data, preserving old cache directories and links.
  Conversion is explicit, with durable undo journal and atomic DB link states.
  Constructors/read requests do not perform filesystem recovery.
- OPENCLAW_CONFIG_PATH exposes an existing JSON config. Older OpenClaw wrappers
  need GROUP roots through the stable pack symlink in skills.load.extraDirs.
- Config ownership is stored separately. Preserve user/preexisting entries.
  Config writes preserve inode for single-file bind mounts; backup/recovery
  journals use restricted permissions and a global cross-process config lock.
  Scoped conversion restore must preserve other packs' later config additions.
- Missing OpenClaw config blocks that target. Link created is not Agent verified.
- Package deletion checks active link/legacy/export references, not removed rows.
  Retained legacy mappings prevent deleted packages reappearing at next startup.

## 4. Validation / Error Matrix

| Trigger | Result |
| --- | --- |
| Bad password | 401 invalid_password before Git |
| Bad URL/extra path field | invalid_repository/invalid_request |
| Duplicate repository | Reuse existing pack |
| Empty candidate inventory | no_skills before live checkout change |
| Local edits/divergence/default branch change | dirty_worktree/branch_diverged/branch_changed |
| Concurrent repository writer | repo_busy |
| Candidate duplicate/root overlap/target conflict | target_incompatible before merge |
| Unknown link/ordinary target directory | blocked; no overwrite |
| Missing OpenClaw config | blocked with diagnostic |
| Legacy partial install | legacy_pending until whole-pack conversion |
| Conversion recovery conflict | Keep journal/diagnostic; service stays available |
| Active references on deletion | pack_in_use |
| Old skill write against pack | pack_managed or blocked publish item |

## 5. Good / Base / Bad Cases

Good: rootless nested skills/tools pack installs to both targets with one link
each; upstream update changes content while link inode/readlink stay unchanged.
Base: root SKILL.md single-skill repo uses the same pack flow; legacy history and
ZIP records survive conversion.
Bad: merge a duplicate-name candidate before validating; move referenced old
caches at startup; restore global OpenClaw JSON and erase another pack's changes.

## 6. Tests Required

test_github_packs.py and test_pack_migration.py cover offline Git, ff-only/dirty,
candidate validation, cache casing, ID uniqueness, legacy/tombstone and recovery.
test_pack_api.py covers auth/tasks/old API guard/startup source preservation.
test_openclaw_pack_discovery.py covers groups, owned vs user entries, scoped
rollback, invalid paths/config and crash journals.
Frontend tests cover pre-202 submission, retry/blocked conversion and statuses.
Validate installed Agent loaders and tools separately from app inventory.

## 7. Wrong vs Correct

Wrong: assume OpenClaw's recursive dependency equals its installed wrapper, then
mark one repository link fully verified.
Correct: retain one pack link, configure necessary GROUP roots and verify actual
installed loader; display unverified state otherwise.

Wrong: checkout --force an old child revision in a live shared repository.
Correct: explicit pack fast-forward update after locks, clean/candidate checks;
stable checkout and link remain unchanged.
