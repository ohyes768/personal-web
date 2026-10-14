# Hermes profile contracts

## 1. Scope / Trigger

Changing configured installation targets, publishing, install preview/execution, target classification, startup migrations or registry/cache removal.

## 2. Signatures

- `GET /api/skills/install-targets` -> `{items:[{id,provider,profile_name,name,install_path,configured,available,unavailable_reason}]}`.
- `POST /api/skills/install/preview`: exactly one of `skill_ids`, `items:[{skill_id,targets}]`, or `scan_task_id + candidates`; optional `target_ids` for IDs/candidates. Candidate `targets` optionally overrides the batch selection for exact failure retry.
- Preview returns `plan_id`, pair-level `items` (including target), `affected_installations:[{skill_id,name,target}]`, and `expires_in`.
- Execute keeps `{plan_id,request_id,password}`; background results include target. Old publish/plan/unpublish routes accept profile IDs too.
- SQLite `install_target(id,provider,profile_name,name,last_root)` complements unchanged deployment/history keys. Old database gets a `.before-hermes-profiles` backup before additive schema migration.

## 3. Contracts

`SKILL_MANAGER_HERMES_TARGETS` JSON array entries contain `id,name,profile_name,skills_root`. `hermes` preserves legacy identity; named IDs use `hermes:profile:<slug>`. Absent/empty environment variable uses legacy HERMES_SKILLS_ROOT; explicit `[]` is invalid. Config roots are absolute, unique, non-overlapping and separate from sources/cache/state; missing target directories degrade individually without mkdir.

TargetResolver owns authorization and captures configured canonical roots. Persistent catalog metadata does not authorize old roots. A root change with active records fails initialization. Classification uses is_install_target, including unavailable namespaced profiles, never a fixed set complement.

Plan limits: 100 Skills, 20 unique targets, 500 pairs; duplicates of a pair deduplicate. Validate all target IDs and availability before scan/source preparation. Source fingerprints are per Skill, target fingerprints include root path/device/inode and link state, affected installations include unselected and inaccessible active profiles. Recheck before submission and each write; changes require new preview. Lock confirmed checkout and target writes together. Registry upsert is once per new Skill; shared repository checkout is reused; conflicts remain pair-local.

Multi-profile links share live source content. Checkout updates siblings' expected source hash/revision only after the confirmed HEAD is observed, including when a deleted member fails validation. Removed members fail independently. Unpublish deletes only that target's managed link. Active unavailable records block registry/cache deletion. Startup offline migration only republishes recorded, available profile links; export and new profile links are untouched.

## 4. Validation & Error Matrix

| Condition | Result |
| --- | --- |
| Duplicate/overlapping roots, bad ID or relative path | Settings validation error |
| Active ID changes canonical root | Initialization fails with original root |
| Unknown/unavailable target | 400 target_unavailable before source work |
| Empty targets, mixed modes, excess pairs | 400 invalid_request |
| Target root/link/source/impact set changes | 409 stale_plan |
| Wrong password | 401 invalid_password; no execution |
| Ordinary target occupant or escaping link | Pair blocked; other pairs proceed |
| Missing/expired plan or restarted task | 410 plan_expired / 404 task_not_found |
| Active configured or offline profile on source deletion | 409 skill_active |
| Profile target on export/delete-export | 400 invalid_target_kind |

## 5. Good / Base / Bad Cases

Good: one Skill links into two directories, one conflict retries only its pair, one unpublish leaves the other link and source intact.
Base: no JSON keeps legacy hermes directory/rows/history; adding a profile creates only catalog metadata.
Bad: reinterpreting offline profile rows as export, restoring write access from last_root, accepting a new root with an old plan, or repeating registration per target.

## 6. Tests Required

`tests/test_profiles.py`: two/three targets, real dual links and independent unpublish, conflicts/exact retry, candidate registration once, shared checkout once/all-profile impact, source/root/link/impact invalidation, password/idempotence, missing roots, retained offline records and config validation.
Existing full backend suite must remain green, especially direct-cache removed-member tests, export, legacy migration and retired OpenClaw behavior.

## 7. Wrong vs Correct

Wrong: `record.target not in LINK_TARGET_IDS` means export, or parse profile IDs through TargetKey enum.
Correct: classify using `is_install_target(record.target)` and resolve writes only through Publisher.targets. Persistent metadata provides display/history only.
