# Residential admission and manual veto

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
- Map statuses: displayed, not_admitted, missing_coordinates, check_coordinates, outside_scope, check_name, merged_duplicate, inactive. Shared checks include finite nonboolean GCJ02 numbers, district/address validation, existing scope, road-name protection and legacy drop IDs. An admitted community lacking valid coordinates remains in the residential list.
- Established registry with zero eligible map records returns a real empty list; never substitute sample communities. Manual subtype overrides legacy property_types by local master ID for map output only. `load_communities`/TMSF identity and refresh target selection stay independent; local-only IDs never become TMSF request IDs.
- One-time `migrate_admission` uses effective associated TMSF/Fang evidence (Amap alone is insufficient), residential→admitted, nonresidential→excluded, unknown/conflict→pending; deleted/merged identities stay inactive. Uses SQLite backup to `directory-backup/community_registry-before-admission.sqlite3` before admission initialization. Repeat prepare/restart never reseeds decisions. QA must set isolated `HOUSING_DATA_DIR`; production rollout requires separate authorization.

## 4. Validation & Error Matrix
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
