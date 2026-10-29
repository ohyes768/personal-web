# Five-dimensional scores and skill version

Use existing dimension names/order to render one compact rating button such as 4/4/3/2/1（v1.1.1）. Null dimensions use — in their position, with the tooltip/report explaining 未评分. A missing report shows a single —. Keep queue and per-stock action behavior.

Extend the skill output with skill_version. Its deterministic finalizer reads metadata.version from its own SKILL.md and stamps the output; validation rejects a mismatching stamp. Bump the contract release from 4.2.0 to 4.3.0. Preserve rating arithmetic and all other fields. The skill lives in F:/personal-projects/skills; edits require filesystem escalation and must preserve unrelated changes.

Backend accepts optional skill_version for legacy compatibility, validates version shape and persists it with the score. Read the current installed version from a configured HERMES_QUALITY_SKILL_PATH pointing to the deployed SKILL.md (not a developer checkout), with an explicit HERMES_QUALITY_SKILL_VERSION override for environments without a shared manifest. If unavailable, return null and do not infer current version from historical scores. UI displays stored version, 版本未知 for legacy results, and 需重评 when a known installed version differs. Surface the current version to explain this comparison.

Use the expected version in prompt and an admission-captured version in the idempotency key; reject mismatching output when the expected version is known. When no installed version is available, use an attempt token so explicit reanalysis cannot retrieve a stale run under the old code/date key. Do not label unversioned responses with the expected version.

No production publication/deployment or historical score backfill. Deployment docs must describe installing the changed skill and configuring the installed manifest/version. Automated stale detection remains unavailable until that source is configured.
