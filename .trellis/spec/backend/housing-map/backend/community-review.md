# Unified community review workspace

## 1. Scope / Trigger
ReviewWorkspace, review routes, directory/auction publication and CommunityWorkspace UI build on community-admission.md. A review row is a community candidate; sources remain evidence and identity records.

## 2. Signatures
- `ReviewWorkspace(store,data_dir).refresh()`, `.reviews(state='pending')`, `.summary()`.
- `.decide(id,action,*,revision,name='',property_type=None,target_id=None,reason='',member_ids=None)`, `.split(id,*,revision,member_ids)`, `.restore(id,*,revision)`.
- SQLite review_candidates(id PRIMARY KEY,payload), review_members(rid PRIMARY KEY REFERENCES sources(id),candidate_id REFERENCES review_candidates(id)); one current candidate owner per source. meta.review_schema_version=1.
- Registry `_decide_admission`, `_associate`, `_merge` accept the writer transaction; public methods retain their signatures. `_associate(review_override=True)` is only for validated review decisions.

## 3. Contracts
- External /api/map/directory, backend /api/directory. GET reviews accepts q/district/source/state=pending|excluded/page/page_size(max100). Detail includes members/reasons/suggestions and saved rounds. GET summary returns global residential/pending/excluded, collection and auction_needs_sync. GET communities adds admission_state/source/property_type filters.
- POST reviews/{id}/decision: action=admit|merge|exclude, revision>=1, name<=100, residential property_type, target_id, reason<=300, optional member_ids. Split requires a proper nonempty member subset; restore requires excluded+revision. POST reviews/sync reads saved auction JSON under StoreLock, performs no upstream requests and returns inventory.
- Candidate payload: id/state/revision/fingerprint/existing_cid/manual_group/auto_review_locked/reason, optional admission_revision. Master candidate ID is master-{cid}; source-only review- IDs persist. Resolved rows are omitted. Raw rental samples stay stored.
- Group only exact normalized full names, same district and equal known addresses, or GCJ02 position within100m when address evidence is incomplete. Different known addresses, missing/disabled names and different phases never collapse. Every member pair must agree; no distance chains. Stable source/kind/sid order and sorted member fingerprints prevent UUID-dependent results.
- Existing unknown/conflicting/withdrawn masters enter review; admitted sources only enrich masters. The effective admission_state governs membership, rather than source residential_state or matched status.
- Current member identity/status/content and master admission revision are checked inside BEGIN IMMEDIATE. Master creation, admission, all associations, candidate result and event form one transaction. Fang collision rolls everything back. Partial decisions split inside that transaction; UI explicitly splits different groups before deciding. Splits retain IDs/rejections, set a lock, and never auto-recombine.
- Admit creates/reuses a master and confirms a residential type. Merge requires active effective admitted target; master merge preserves redirects/aliases. Exclude retains source statuses and auctions, locks candidates and delegates existing-master exclusion to task1. Restore returns pending with the lock. Legacy source bind/create and automatic association cannot bypass excluded/locked members.
- Auction sync aggregates rounds by source+asset_id, then communities by evidence. Missing asset keeps separate auction IDs and sets auction_identity_uncertain; assets counts known IDs, rounds counts unique rounds. Missing community names are explicit; original title is only source evidence. Promotion retains source ID/manual decisions; old round conflicts remain unresolved.
- Successful auction publication calls sync_records→refresh; failure retains durable JSON for retry. Directory collection materializes candidates after saving sources; queue failure records a review-stage error without losing sources. GET review reads can update candidate projection but never import auction JSON or fetch upstream. Historical auctions require explicit sync.
- UI has residential/review tabs. Tabs/list totals use current filters; top inventory is labeled all regions. Excluded is a review state filter. Source collection time/counts/errors are separate. Rental missing-source business tasks are independent; raw unmatched Fang sources can enter review. Auction legacy action dispatches housing-open-community-review and opens the laipai-filtered queue.
- QA uses isolated HOUSING_DATA_DIR. Task2 never automatically admits new communities; task3 must reuse revisions/member snapshots and human locks.
- Task3 now implements [automatic review](./community-auto-review.md) through the shared _decide transaction. Splits lock both halves (including existing-master admission); pending candidates support explicit allow_auto_review without direct admission.
- Management performance: `refresh()` returns current effective community views; `reviews(state,refresh=True,include_suggestions=True)` retains the default contract. `add_suggestions(rows)` enriches only returned page/detail rows. Summary refreshes once, omits matching suggestions and returns global counts plus `filtered={residential,pending}`. Shared community_matches/review_matches keep filtering identical between count and list APIs.
- GET summary additionally accepts q/district/source/property_type. Review listing filters lightweight rows and only then adds suggestions to the selected page; detail refreshes once and enriches one candidate. Counts must never invoke registry.candidates. Existing source/admission mutation transactions and snapshots are unchanged.
- Frontend current-page loading is independent from filtered/global stats, and only requests the current list. Text search alone has200ms debounce; tab/structured filters are immediate. Limited60s caches use full request paths, isolate tabs/filters/page/state and clear on manual actions, automatic execution, rental changes, collection completion or explicit refresh. If a fetched page exposes expired stats, refresh stats independently. Stats errors display unknown badges and never block a usable list.
- Collection completion invalidation checks both running→stopped and changes of finished_at, so a short run entirely between polls still invalidates caches. Cache expiry and server revision checks protect external edits; caching never approves a stale decision. Only one list-loading message is rendered.

## 4. Validation & Error Matrix
Invalid action/type/page/member limits→422; missing/resolved detail→404; stale candidate/admission/member, duplicate decide, invalid split/restore/target or Fang collision→409/full rollback. Read corruption/SQLite/filesystem failures→503. Historical sync while StoreLock is held→409.

## 5. Good / Base / Bad Cases
Good: TMSF+Amap+two assets/three rounds→one candidate→one residential with all identities linked. Base: uncertain identities stay separate with suggestions and unknown asset-total labels. Bad: count rounds as properties, use titles as community names, undo human splits, or use ignored/deleted for residential exclusion.

## 6. Tests Required
test_community_review: stable pairwise grouping, phases/addresses, inventory, round counts, stale members, rollback, partial decisions, splits/locks, master merge/redirect and collection publication. test_community_review_api: filters/pages/422, stale409, summary and restore. Existing admission/directory/auction/rental regressions remain mandatory. Frontend covers tables/counts/actions/auction jump; isolated browser covers desktop/mobile decisions and live map/inventory.
test_directory_performance asserts one refresh/no suggestions for counts, page-only matching and filtered count/list agreement. community-page-cache.test covers tab/filter isolation, expiry, eviction and explicit invalidation. Browser checks warm switching produces zero list/stat requests, slow/failed stats do not block list, decisions/expiry/short completion refresh, and excluded totals do not overwrite pending badges.

## 7. Wrong vs Correct
Wrong: public create→associate→admit in separate transactions leaves an orphan on Fang collision.
Correct: one store.db transaction using _decide_admission/_associate/_merge, then persist candidate outcome after validation succeeds.
