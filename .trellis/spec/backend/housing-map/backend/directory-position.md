# Known-community Amap position status

## 1. Scope / Trigger
Applies to directory_position.py, directory_position_state.py, directory_workflow inventory/API, DirectoryFlowWorkspace and PositionPanel. Runs only after explicit directory-flow migration. Position evidence never creates sources/masters, establishes residential use, changes actual addresses, or reactivates ignored Amap discovery records.

## 2. Signatures
External prefix `/api/map/directory/workflow` (backend `/api/directory/workflow`):
- GET `/catalog?position=matched|pending|review|not_found|error|manual` filters before pagination, alongside existing district/market/type filters.
- GET `/catalog/{cid}/position` returns position plus `revision` (SHA256 of complete master, linked-source rows and admission payload).
- POST `/catalog/{cid}/position/query`, no body: explicit known-name retry; returns current position plus `errors:string[]` for durably saved query outcomes.
- POST `/catalog/{cid}/position/confirm` accepts `{revision,poi_id}` for an existing server-side candidate, or `{revision,longitude,latitude,address}` for a verified manual GCJ02 point.
- GET/POST/DELETE `/positions` retain the existing persistent/cancellable batch job.
- `position_view(target, records=())` is a pure projection; `position_one(...,client=None,cancelled=...,force=False)` performs bounded lookup then optimistic publication. `PositionOutcome(ValueError)` means an outcome was persisted; ordinary stale/eligibility ValueErrors remain conflicts.

## 3. Contracts
- Store additive `amap_position` in the master payload: identity fingerprint (id/name/aliases/district/actual address), state, checked_at, candidates, selected, error and optional confirmed_at. No schema migration or startup upstream calls. API position projection omits the internal identity token.
- matched requires genuine Amap POI identity evidence; historical_amap/TMSF IDs/coordinates alone remain pending. Existing source `coordinate_evidence.source=amap` with a real POI ID and valid GCJ02 position may supply legacy matching evidence; ignored/unlinked sources cannot.
- manual records include explicit chosen POIs and manually entered coordinates; absence of a POI ID must say so. Manual origin/evidence on the master or active source is protected, including later manual edits overriding a previous automatic result.
- Batch snapshots current admitted targets, processes pending/error only, skips matched/manual/review/not_found without constructing a client. Explicit single retry can re-query matched/review/not_found; manual results remain protected. Keep256-request budget,2s pauses, cancel/restart-interrupted/shutdown behavior. Queries use the existing server key configuration; no key-bearing URL enters reports.
- Lookup keeps exact full-name/alias, supported district, residential category and boundary validation. Name filtering also accepts containment (loose) hits: a POI name and a community name/alias containing each other count as candidates when the shorter normalized side has length >= 3. An untruncated result (count <= 25) with exactly one candidate auto-matches regardless of loose (containment) naming or address differences; multiple candidates, or any candidate under truncation (count > 25), persist review candidates and never choose silently. When the primary name yields no candidates and the result is untruncated (count <= 25), the lookup retries up to 3 normalized-deduplicated aliases in order and stops at the first candidate hit (loose hits count); alias retry requests are not added to the batch per-community `requests` count, so the budget still counts communities and upstream requests stay bounded at <= 4 per community. Empty reliable matches persist not_found; transport/config failure persists error. A failed/ambiguous explicit re-query retains the last valid match and error, without clearing coordinates.
- Preserve any existing valid master/source/historical-file map position during automatic POI completion; selected POI coordinates remain separately inspectable. Only explicit human confirmation replaces the map point. Geographic address remains separate from TMSF actual address. Changed identity invalidates old automatic POI state; retaining map coordinates never implies the new identity matched.
- Network work is outside writer transactions. Publication compares complete master/source/admission snapshot and re-evaluates current eligibility inside the writer; cancelled responses cannot write. Confirmation accepts only the saved candidates under current identity and supplied revision; a candidate missing map address requires verified manual input. Manual points require a real address, finite GCJ02 values and the correct district boundary. Single writes and batch starts serialize through the existing job lock; running batch refuses single writes.
- UI shows independent map status and POI state, has-coordinate text, server-side state filter, per-row detail action, candidate evidence/links and manual coordinate form. Refresh the full detail after a successful operation to avoid stale geographic address display. Persisted query time and human confirmation time are distinct. Bulk does not follow the list's search/state filters; its card explicitly targets all admitted pending/error entries.

## 4. Validation & Error Matrix
- Inactive flow409; unknown/deleted/not-admitted/stale target or stale candidate409. DB/filesystem failures503.
- Invalid enum/revision/numeric bounds/non-finite input422. Missing/wrong-district manual point or forged/stale candidate409.
- Query review/not_found/upstream failure200 with saved state and explanatory errors. A stale result must never be downgraded to200 merely because an older checked_at exists.
- Active batch + single query/confirmation409. Empty/all-complete batches succeed without an upstream key.

## 5. Good / Base / Bad Cases
Good: history geocoder point → pending/has_coordinates → POI lookup adds evidence while retaining original map point → user explicitly confirms candidate if a location change is needed.
Base: two name-matching POIs, or a single candidate under truncation → review; user selects one with latest revision → manual, next batch skips it. Source edit during HTTP → conflict, no publication.
Bad: label every valid coordinate as matched, use the TMSF ID as a POI ID, clear an old point on lookup failure, or restore deleted discovery sources to show a badge.

## 6. Tests Required
`test_position_status.py`: legacy coordinate distinction, preserving valid points, matches/empty/ambiguity persistence, single-candidate auto-match across exact/loose names and differing addresses (including alias retry hits), truncated unique candidates staying review, first-query failure, alias retry after an empty untruncated primary query (dedup, cap of 3, stop on first hit), manual candidate/coordinate validation, manual source/late manual edit protection, stale identity/confirmation/source snapshots, cancellation, batch skip/no-network behavior, API filtering before pagination and batch write conflicts. Existing directory-flow budget test must use an actually pending target; review candidates are no longer automatic retry targets. `position-status.test.cjs`: independent map/POI labels, admitted-row actions, candidate evidence and human protection. Isolated browser with fake upstream: state filtering, candidate save, history POI completion, desktop1440px/mobile390px, no horizontal overflow.

## 7. Wrong vs Correct
Wrong: `if valid_position(c): skip_lookup()` or render `coordinate_evidence.source_id` unconditionally as POI.
Correct: `position_view(c, matched_sources)` requires Amap POI evidence, preserves historical coordinates separately, and defaults batch work to pending/error states.
