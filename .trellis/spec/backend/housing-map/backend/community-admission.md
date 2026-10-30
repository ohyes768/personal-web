# Residential admission and manual veto

> After explicit `tmsf-directory-v1` migration, [TMSF directory workflow](./directory-flow.md) supersedes multi-source admission/review and defines task eligibility. Stored history and pre-migration behavior remain readable.


## 1. Scope / Trigger
Applies to registry admission, management actions, map/score visibility and migration. This contract supersedes the old full-directory display rule; independent collection and historical identity lookup retain their existing scope.

## 2. Signatures
- `CommunityRegistry.admission(cid)` returns the durable decision; `decide_admission(cid, action, *, revision, reason='', property_type=None)` updates it atomically with an audit event.
- SQLite `community_admission(cid PRIMARY KEY REFERENCES communities(id), payload)`; payload includes state, decision_kind, property_type, revision, auto_review_locked, reason, decided_at; lock fields for human veto, evidence/rule_version for migration. `meta.admission_schema_version=1` marks initialization.
- `community_views(store, data_dir, *, deleted=False, coordinates=None, drop_ids=())` returns effective admission and map projection. `load_display_communities` feeds map and score; `load_communities` remains the identity/collection set.

## 3. Contracts
- POST `/api/directory/communities/{cid}/{action}`: action `admit|review|exclude|restore-admission|allow-auto-review`; JSON `{revision: int >=1, reason?: string <=300, property_type?: '住宅'|'别墅'|'排屋'}`. Success envelope returns the new durable admission. Register this generic route **after** legacy static `/restore` and `/merge` routes.
- Admit requires a residential type, sets admitted/manual and clears the veto. Review sets pending/manual and locks. Exclude requires a nonempty reason, sets excluded/manual and locks. Restore-admission requires excluded, returns pending **with the lock**. Allow-auto-review requires durable pending and explicitly clears the lock; it does not admit or run automatic processing.
- All actions require active unmerged identities, compare revision in `BEGIN IMMEDIATE`, increment revision and append an event. No source status, rejected pair, auction round, rental/price snapshot or community ID changes.
- New `create`/`create_from_source` writes pending admission in its existing transaction. Neither source association nor collected property evidence admits a new community in task 1.
- Management list/detail returns `admission` (saved decision), `admission_state` (effective state), `effective_property_type`, `admission_conflict`, `map_status`. Existing `residential_state` remains source classification and is **not** the admission state. Effective state is the filter/count/display contract for tasks 2/3.
- An actual valid address from master or currently matched sources is required for effective admission, rental eligibility and auction community mappings. Missing addresses project to excluded with address_missing/exclusion_reason even for a manually admitted master; preserve its durable decision and audit. Geocoder/coordinate formatted_address is not address evidence.
- Manual admitted types win over source conflicts and display a warning. Migrated/automatic admitted decisions with missing/contradictory current evidence project to pending without overwriting audit history. Clear residential types use current evidence for nonmanual admissions.
- Directory mode blocks the generic `admit` action. The controlled alternative for a mislabeled community is the use confirmation in [Amap use-category review](./use-review.md): it writes a separate `use_rule` decision that overrides the use gate only, is audited, and is never overwritten by a collection refresh.
- Map statuses: displayed, not_admitted, missing_coordinates, check_coordinates, outside_scope, check_name, merged_duplicate, inactive. Shared checks include finite nonboolean GCJ02 numbers, district/address validation, existing scope, road-name protection and legacy drop IDs. An admitted community lacking valid coordinates remains in the residential list.
- `community_views.position_formatted_address` must expose the final coordinate address used by `map_status` (including protected geographic address and verified source-district qualification). `load_coordinates` consumes this same address; falling back to the unqualified residential street address can wrongly drop admitted, valid-position communities before API rendering, with neither polygon nor placeholder despite displayed statistics.
- `/api/communities` admission statistics further require a nonempty polygon `rings` with `source != 'shp'` for `stats.displayed`, matching the frontend visible-polygon rule. Otherwise an eligible coordinate-only record counts under `stats.hidden.missing_boundary` (边界待补); retain it in `data` for the question-mark position placeholder. Boundary completeness does not change admission, collection eligibility or the shared `map_status` projection.
- Established registry with zero eligible map records returns a real empty list; never substitute sample communities. Manual subtype overrides legacy property_types by local master ID for map output only. `load_communities`/TMSF identity and refresh target selection stay independent; local-only IDs never become TMSF request IDs.
- One-time `migrate_admission` uses effective associated TMSF/Fang evidence (Amap alone is insufficient), residential→admitted, nonresidential→excluded, unknown/conflict→pending; deleted/merged identities stay inactive. Uses SQLite backup to `directory-backup/community_registry-before-admission.sqlite3` before admission initialization. Repeat prepare/restart never reseeds decisions. QA must set isolated `HOUSING_DATA_DIR`; production rollout requires separate authorization.

## 4. Validation & Error Matrix

V2 catalog 重新审核/完成审核 use dedicated reopen-review/complete-review routes and a durable review_requested marker; see [collection pipeline](./collection-pipeline.md). This pending hold is not manual exclusion. Manual use confirmation may resolve it; ordinary manual exclusions keep their veto. Legacy generic review/restore behavior stays unchanged.
Malformed action/body/type/revision→422. Stale revision, inactive target, missing exclusion reason/type or invalid transition→409. Directory/SQLite/filesystem initialization or mutation error→503. Detail not found→404. Duplicate submit with the old revision→409, no additional community/event.

## 5. Good / Base / Bad Cases
Good: review 江汉路小区→map empty→reimport/new round/restart keeps lock→exclude→restore pending/locked→manual admit makes map eligible.
Base: admitted without coordinates stays in list with missing_coordinates; current source disagreement flags a manually confirmed community.
Bad: use whole-community delete for residential exclusion; clear lock on restore; use map membership to determine independent collection; equate sources.matched with admitted.

## 6. Tests Required
`test_community_admission.py`: once-only legacy SQLite migration, backup, stable names/aliases/rejections/deletes, new pending identities, revision validation, new rounds, manual locks, subtype and conflict projection.
`test_community_admission_api.py`: UI API→map count/type, real empty list, independent refresh targets/local ID guard, invalid/missing coordinates.
`community-management.test.cjs`: review/exclude/restore controls, mandatory reason affordance, lock and reason text. Isolated browser: desktop transitions, 390×844 withdrawal, matched source preserved.

## 7. Wrong vs Correct
Wrong: `store.delete(cid)` when the user excludes a nonresidential record; it ignores all linked identities and stops independent detail collection.
Correct: `store.decide_admission(cid, 'exclude', revision=current_revision, reason='非住宅')`; the residential projection changes while source identities and history remain intact.

## Second-hand listing threshold (2026-10-14)
`community_listing.listing_gate(records, master=None)` is the shared admission gate: verified TMSF second-hand listing_count 0..2 projects to excluded with an explicit reason; >=3 continues ordinary residential checks. Missing/invalid counts and latest listing_count_error return pending, never zero. New-house source evidence is exempt. Legacy unknown market evidence without listing fields does not establish second-hand eligibility; a same-master historical listing_count can supply the initial count for one TMSF identity until its first detail check.
Projection does not delete sources or rewrite durable human decisions/history. Candidate and direct master admit/merge operations enforce the same gate under the writer transaction; candidates appear in 不收录 and can use existing removal. A fresh sufficient count removes only the derived gate, never a durable manual exclusion. TMSF second-hand detail counts refresh each collection (no 30-day property-fact cache); new-house property evidence may still cache. Auto-review version v4 requires a fresh reviewed enablement.
Tests: test_community_listing covers 0/1/2/3 boundary, missing/invalid/failed counts, new-house exemption, existing-master withdrawal/recovery, and manual bypass rejection.

Newhouse residential projects, failed-attempt retention, independent market state and current-source coordinate projection follow [enrichment](./community-enrichment.md).

## Amap subject address gate (2026-10-27)
`community_address.admission_address(community, records)` is the single read-only address projection for admission, map views, catalog detail, rental eligibility and auction targets; it never writes an Amap address into source facts. Selection order: protected manual actual address → first verified same-identity source actual address → reliable Amap subject address, available only when the collection pipeline is active for the object and the policy flag `admission_address_policy=amap-subject-address-v1` is present in registry meta and the community payload (propagated by `directory_workflow.materialize`); without the flag the projection is byte-for-byte the old rule. The Amap fallback requires position state `matched|manual`, a non-empty truncated-free POI address, normalized category, typecode starting `120`, valid GCJ02 position inside the community district, no foreign-district name in the address text, and `auto_subject_reliable` for matched (not manual) subjects. Evidence carries `origin='amap_subject'` plus poi_id, name, district, coordinates, typecode, checked time and the position identity fingerprint; identity or selected-subject changes invalidate it, human facts stay protected, and ambiguous/attached/conflicting subjects never qualify. `community_views` exposes the projected address, keeps the raw value as `source_address`, attaches `address_evidence`, and the frontend labels the origin (高德主体地址) without implying TMSF 坐落.
`address_policy_migration` provides `preview` (read-only snapshot simulation: per-community before/after address origin, admission/map state and rental/auction eligibility deltas), `apply` (external backup + `--maintenance`), and `disable` (maintenance window only, refuses running jobs, removes meta+payload flags and re-projects; later user writes survive). Activation never happens implicitly on GET/start/deploy and requires the candidate-subject pipeline to be enabled first.
