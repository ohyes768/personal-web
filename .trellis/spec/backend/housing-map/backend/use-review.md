# Amap use-category review and human use confirmation

## 1. Scope / Trigger
Applies to `use_review_policy.py`, `directory_use_review.py`, the `use_review` payload on the master, `community_registry.confirm_use`, the type gate in `directory_policy.eligibility`, the `/directory/workflow/use-reviews` endpoints and `UseReviewPanel` in DirectoryFlowWorkspace. Runs only after explicit directory-flow migration. The review reads a second source (Amap) for the residential use of a catalog community; it never creates sources or masters, never changes the actual address, and never admits or excludes a community on its own.

## 2. Signatures
External prefix `/api/map/directory/workflow` (backend `/api/directory/workflow`):
- GET `/catalog?use=conflict|uncertain|pending_retry|agree|none` filters before pagination, alongside the district/market/use/position filters.
- GET `/catalog/{cid}/use-review` returns the review projection `{state, category, result, checked_at, error, evidence, candidates_count, human, re_review}`.
- POST `/catalog/{cid}/use-review`, no body: explicit re-check of one community; returns the same projection plus `errors:string[]`.
- POST `/catalog/{cid}/use-review/confirm` accepts `{revision:int>=1, decision:'residential'|'non_residential', property_type?:'住宅'|'别墅'|'排屋', use_evidence:[{source,url,note}] (non-empty, url required), reason (required for non_residential)}`.
- GET/POST/DELETE `/use-reviews` is the persistent batch job: status/start202/cancel. Error or conflicting startup409, storage503.
- `amap_category(typecode)`, `tmsf_category(types)`, `compare(types, amap)`, `select_evidence(pois, community)` are pure. `use_identity(target)`, `use_review_view(target)`, `use_review_projection(community, records, admission, facts)` are pure projections. `review_one(store, data_dir, cid, client=None, *, cancelled=..., force=False)` performs one bounded lookup then publishes it. `UseReviewOutcome(ValueError)` means an outcome was persisted; ordinary stale/eligibility ValueErrors remain conflicts.

## 3. Contracts
- Store additive `use_review` in the master payload: identity fingerprint, rule_version `use-review-v1`, state (`checked`/`not_found`/`error`/`uncertain`), category (`residential`/`mixed`/`non_residential`), checked_at, error, evidence and candidates_count. No schema migration and no startup upstream calls. The catalog row exposes the projection, never the internal identity token.
- The decision matrix is the only consumer of Amap categories: TMSF residential + Amap residential → keep the current verdict; TMSF non-residential + Amap non-residential → keep the current verdict with its reason; either direction disagreeing → `use_conflict` (incomplete, pending human review); an unclear or mixed side → `use_uncertain` (incomplete); no usable evidence (not found / error / uncertain match) → `pending_retry`, the TMSF verdict stays unchanged. A failed or missing lookup is never a non-residential verdict.
- Amap classification codes: `120300|120301|120302|120303|120304` (any segment of a compound code) → residential; `120203` → mixed; any other non-empty code → non-residential; empty → no category. Only same-district, name-matched POIs count: the reuse of the position name rules (flatten parentheticals, middle dots and generic estate suffixes; equality or containment with the shorter side >= 3; alias names included) is the shared implementation in `poi_names.py`, never a second copy. Incomplete paging or disagreeing candidates yield no evidence in either direction.
- `AmapClient.search_name(name, district, types=None)` omits the `types` parameter entirely, so the review sees every category; the default keeps the residential whitelist so position lookups stay narrow. The position query and the review query are independent requests.
- Search requests restrict `city` to the target district adcode (`滨江` → `330108`, `萧山` → `330109`) with `citylimit=true`. Same-district POI validation still applies. `search_name(..., page=1)` stays a single-page primitive for position lookups; use review alone requests subsequent pages (25/page, maximum 8 pages per name), including alias queries. It deduplicates raw POI IDs before name/district filtering and accepts evidence only when the distinct ID count equals the stable upstream total. Partial overlap continues paging; empty/repeated pages with no progress, missing IDs, changed totals, or exhaustion of 8 pages remain uncertain. Transport failures on any page persist error without partial evidence. Cancellation is checked before/after every page and before publication.
- The identity fingerprint covers community_id/name/aliases/district but not the actual address: the address is corrected during enrichment and is unrelated to the use category, so including it would silently drop a confirmed conflict back to the TMSF verdict. A changed fingerprint or a changed rule_version invalidates the stored evidence (it projects as no evidence).
- A human use decision is stored in `community_admission` (`use_rule='use-review-v1'`, `use_decision`, `use_evidence`, `reason`, `decided_at`) and is authoritative over the TMSF type gate only — region, address and listing gates still apply. It is never overwritten by a collection refresh or a review run. New contrary evidence after `decided_at` (an Amap category pointing the other way, or a TMSF property type refreshed after `decided_at`) sends the community back to `use_conflict`; the stored decision is kept, not deleted.
- A plain manual exclusion or review lock stays the highest priority: `confirm_use` refuses to write over it and the projection keeps excluding the community.
- Batch snapshots every non-deleted, non-merged master with a TMSF record (admitted and excluded), skips targets that already hold valid evidence, limits 256 community lookups with 2s pauses, supports cancel/restart-interrupted/shutdown, and reports by outcome (`updated`/`conflict`/`not_found`/`uncertain`/`error`/`skipped`) plus the community lookup count (`requests`, not HTTP page count). Each lookup has at most 4 names (primary + 3 aliases), each at most 8 HTTP pages. An empty run needs no upstream key and issues no request.
- Network work happens outside writer transactions. Publication compares the complete master/source/admission snapshot and re-checks the identity fingerprint inside the writer; a cancelled response cannot write.

## 4. Validation & Error Matrix
- Inactive flow409; unknown/deleted/merged target409. Stale revision409. DB/filesystem failures503.
- Invalid enum/missing or empty `use_evidence`/missing evidence url/missing `property_type` for residential/missing `reason` for non-residential → 422.
- A query that finds nothing, fails or cannot match uniquely returns 200 with the saved state and an explanatory error.
- Active batch + single query/confirmation409. Empty batch succeeds without an upstream key.

## 5. Good / Base / Bad Cases
Good: TMSF says 商贸, Amap says 住宅小区 → `use_conflict` (incomplete) → the reviewer confirms residential with a 克而瑞 link → the community is admitted and enters the rental/auction target set.
Base: TMSF says 商贸 and Amap finds nothing → the TMSF verdict stands unchanged and the community stays retryable.
Bad: treating a failed lookup as a non-residential verdict, letting an Amap code admit a community directly, or letting a review run overwrite the human decision.

## 6. Tests Required
`test_use_review_policy.py`: typecode mapping (compound codes, empty, unknown), the TMSF category, every matrix branch, evidence selection (exact/alias/loose, other district, attached places, disagreeing candidates, agreeing candidates).
`test_directory_use_review.py`: one review stores evidence; not_found/error/truncation persist; no write after cancellation; a changed snapshot refuses the write; a valid evidence is skipped unless forced; the alias retry; an identity change invalidates the evidence.
`test_use_review_confirm.py`: the decision and its audit event; the required evidence, url, reason and type; a stale revision; a deleted target; a manual exclusion cannot be overridden; a refresh never overwrites the decision; the contrary-evidence rule.
`test_directory_policy.py`: the whole matrix, the no-evidence equivalence with the previous verdict, the human decision passing only the use gate, and a plain manual exclusion staying untouched.
`test_use_review_job.py`: admitted and excluded targets, skipping, outcome counting, the request budget, an empty run without a key, cancellation, restart-interrupted and the human decision surviving the run.
`test_use_review_api.py`: the single query and confirm endpoints, the 422/409 matrix, the `use=` filter before pagination, the batch lifecycle and the batch/single-write exclusion.
`test_use_review_scenario.py`: the end-to-end 风雅钱塘 case from `non_residential` to `use_conflict` to a human residential confirmation to admitted.
`use-review.test.cjs`: the review buckets and badges, the excluded column, the panel evidence and re-review warning, the required confirm fields, the job summary wording and its legacy fallback.

## 7. Wrong vs Correct
Wrong: `if amap_says_non_residential: exclude(community)` or storing the human decision in the master payload.
Correct: the review only produces a conflict or a pending-retry state; the admission table keeps the human decision and `eligibility` decides the single verdict.
