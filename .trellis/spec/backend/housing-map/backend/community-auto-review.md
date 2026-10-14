# Automatic residential review

## 1. Scope / Trigger
Task3 builds on community-admission.md/community-review.md. AutoReview owns rules, local snapshots, explicit enablement, execution and publication reports. Source identity association remains separate from residential admission.

## 2. Signatures
- `AutoReview(store,data_dir).preview()`, `.status()`, `.configure(enabled,reviewed_snapshot=None)`, `.execute(reviewed_snapshot)`, `.after_collection()`.
- Pure `decide(group,members,*,groups,sources,masters,admissions,rejected,facts)` returns candidate_id/revision/member_ids/name/action/reasons/evidence and optional target_id/property_type.
- Rule `community-auto-v2`; actions admit/merge/pending/exclude/protected. Exclude is advisory only; protected retains existing exclusions. No automatic exclusion/deletion or batch resurrection.
- Meta keys auto_review_enabled/auto_review_rule_version/auto_review_report; enabled defaults false and only applies to its reviewed rule version. Batch events preserve snapshot, rule, evidence, decision time and actual outcomes.

## 3. Contracts
- Preview opens existing SQLite with mode=ro and a fixed read transaction, backs up into memory and runs the shared ReviewWorkspace projection there. It never invokes prepare_directory/import/migration, source fetches or business writes. New projection IDs derive from the seed source ID; sorted input and omission of projection creation times make previews reproducible.
- Snapshot hashes communities/sources/admissions/rejections/review candidates/members and property facts, including row statuses, manual locks and targets. The report excludes wall-clock preview timestamps. Legacy TMSF fallback facts are included in the evidence; a latest source attempt supersedes legacy facts.
- Evaluation order: existing exclusions/manual locks → reliable names → actual address → scope → member/master identity → duplicates/rejections → residential classification. Full names/aliases keep phase suffixes. Known different addresses never use distance to override disagreement. Grouping/matching reuse same_community; no distance chains or global name blacklist.
- Missing actual addresses return exclude advice before scope/type analysis; current projection provides 不收录 without automatic durable exclusion. Rule v5 requires a new reviewed preview before enabling; older rule enablement does not carry over.
- Binjiang requires a Binjiang address. Xiaoshan additionally requires a valid GCJ02 position in the shared adjoining scope. Missing/unreliable/outside coordinates, road/attached-facility names, conflicting member evidence and ambiguous identities cannot auto-admit. Road suspicion is never direct exclusion.
- New admission requires classify_sources=residential from TMSF/Fang, reliable name/area/address, and no existing master or pending similar-name/phase doubts. Amap and auction titles alone never establish use. Mixed/unknown/conflicting evidence stays pending; a failed refresh retains the last effective use fact. Associated pending masters must agree with their source identity and are admitted without rewriting existing matched members.
- A uniquely admitted matching target may receive supplemental sources; manual residential confirmation stays authoritative. Amap/Laipai identity clues may supplement a proven target without claiming new residential use. New TMSF/Fang disagreement or Fang collision stays pending. Existing pending masters are never automatically merged/deleted.
- Excluded/locked source identities, deleted/locked masters, ignored sources and rejected bindings are conservative veto evidence. Changed external IDs cannot cover a reliable same-identity veto; different names/addresses are not globally blacklisted. The low-level legacy auto association also rejects target locks, known different addresses, same-identity candidate vetoes and rejected bindings.
- Execute requires enabled=true for the current rule. Inside BEGIN IMMEDIATE, compare the complete current snapshot and property facts before copying the shared in-memory candidate projection. Reuse ReviewWorkspace._decide and registry _decide_admission/_associate; every candidate uses a savepoint, so creation/admission/all members/events either succeed together or roll back. Stale whole snapshots reject409; per-candidate conflicts are explicit outcomes. No network work occurs under the transaction.
- Automatic admissions save decision_kind=automatic, rule_version/evidence/batch_id/decided_at in the admission event and payload. Associations have method=auto and readable string evidence. Sources already matched to the admitted master retain their original association audit. Human review/exclude locks, restore keeps locks, explicit allow-auto-review unlocks without admitting. Splits lock both halves and existing-master admission durably.
- Directory and saved-auction publication refresh candidates then preview/execute according to the switch. Suggestions/actual results are separate from original source collection counts. Auto-review failure preserves saved sources/queue/auction JSON and reports a retryable error; disabling stops future decisions and does not alter prior ones.
- UI shows read-only preview, reasons/source evidence, a confirmation for enablement and another for execution, a disable action, last actual report and per-collection report. Automatic admissions are labeled and reversible through the existing admission controls. Excluded restore is pending/locked; explicit candidate allow-auto-review is separately confirmed.

## 4. API / Error Matrix
- GET `/directory/auto-review` → enabled/rule_version/last_report.
- POST `/directory/auto-review/preview` → snapshot_id/rule_version/items/counts; no body.
- PUT `/directory/auto-review/config` → {enabled,snapshot_id?}; enable requires a current reviewed snapshot, disable does not.
- POST `/directory/auto-review/execute` → {snapshot_id:64 lowercase hex}; returns actual applied/skipped/conflict results.
- POST `/directory/reviews/{id}/allow-auto-review` → {revision}; only pending, no execution.
- Invalid input422; disabled/stale snapshot or invalid human action409; corrupt/IO/SQLite read503. Per-candidate ValueError rolls back its savepoint; unexpected SQLite failures roll back the whole batch.
- CLI `python -m src.services.community_auto_review --data-dir <isolated-dir> --report` exports only to diagnostics/auto-review/<snapshot>.json; no enable/execute/migration. Production deployment and switch enablement require separate user authorization.

## 5. Good / Base / Bad Cases
Good: TMSF verified residential + trustworthy identity → preview → explicitly enable/execute → one master → human withdraw → repeat preview/collection remains pending. Base: missing actual address → exclude advice and effective 不收录; only Amap 江汉路小区, same-name phase or latest failure → explained pending. Bad: recover excluded IDs automatically, treat an auction dwelling as whole-community use, rebind already matched members, or auto-recombine a human split.

## 6. Verification
test_community_auto_review covers readonly/reproducible bytes, explicit opt-in, conservative evidence matrix, stale facts/sources, human veto/new IDs, candidate rollback, differing addresses, both split locks and diagnostic CLI. Integration covers APIs/unlock, existing-target enrichment, existing pending-master admission without rebinding, rule-version disablement, collection lifecycle and stale splits. Run full backend and frontend suites plus isolated desktop/mobile admission/withdrawal/map verification and old-copy preview.

## 7. Wrong vs Correct
Wrong: call reviews() on the live registry during preview, or create→associate→admit across public transactions.
Correct: project the shared workspace only into memory; on approved execution verify a fresh snapshot inside one writer transaction and call the shared private transaction methods.

Newhouse project identity, separately verified address district and coordinate provenance follow [enrichment](./community-enrichment.md).
