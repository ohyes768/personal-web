# Rental source management contract

> Current deployment now uses [Community directory](./community-directory.md) as the authoritative editable store. This document describes the older fallback/standalone SourceStore contracts. With a directory present, SourceStore delegates to it; automatic evidence-based association is allowed and the header CTA opens the management Tab. Do not add a second writable mapping store or override directory deletion decisions.

## 1. Scope / Trigger
Applies to `rental_reference/sources.py`, `rental_source_routes.py`, source membership in `refresh.py`, rental query snapshot selection and the frontend source manager.

## 2. Signatures
- `SourceStore(mappings_path)` initializes `mappings_path.with_name('rental_sources.sqlite3')`.
- `get(community_id)` -> `{mapping, candidates}`; `confirm(id, source_id)`; `remove(id)`; `reject(id, source_id)`.
- `save_candidates(id, candidates, restore=False)`: repeat automatic discovery preserves rejection; explicit URL import can restore a rejected candidate for review.
- `RentalRefreshService.change_sources(action)`: holds web-start mutex, rejects live worker, and takes `RentalPublishLock(rentals_dir/'rental_publish')` while applying the edit.
- DB tables: `meta(key,value)`, `mappings(community_id PRIMARY KEY, source_id UNIQUE, payload)`, `candidates(community_id,source_id,payload,rejected)` with composite PK.

## 3. Contracts
| Method | Path | Meaning |
|---|---|---|
| GET | `/rentals/sources` | `data.communities[]`: internal id/name/area, mapping and candidate_count |
| GET | `/communities/{id}/rental-source` | current mapping, pending candidates and internal community |
| POST | `.../rental-source/search` | `{keyword?,source_url?}`; persists reviewable candidates, returns found_count |
| PUT | `.../rental-source` | `{source_community_id}`; confirms an existing, non-rejected candidate |
| DELETE | `.../rental-source` | unlinks; does not delete historical snapshots |
| DELETE | `.../rental-source/candidates/{source_id}` | rejects candidate |

External prefix is `/api/map`, backend prefix `/api`. Success envelope remains `{success:true,data}`.

- Initialization imports legacy validated JSON once, or `/app/seed-data/rental_community_mappings.json` if old named volume lacks the file. Docker must COPY this seed separately. `meta.imported` prevents deleted/edited associations being overwritten or resurrected.
- After initialization, SQLite is authoritative. `load_verified_mappings` reads the initialized DB; legacy JSON stays fallback for standalone callers without DB.
- Every candidate is human confirmed. Source name, address when available, internal district/subdistrict, evidence gaps and original source URL are displayed. Coordinates and phase are not inferred.
- Only HTTPS Hangzhou Fang community rental list URLs (`house-xm` numeric id), no query/fragment/userinfo, can be imported. Redirects reuse `FangClient` URL validation. Candidate id/name comes from structured community links in listing records; unrelated navigation links must not be candidates. A recognized empty community list may use its own breadcrumb name.
- Discovery reads one list and at most one detail page; source search must prove its keyword was applied (`pageConfig.keyword`). Current 2026-10-12 live pages ignore query keywords; never expose all-city rows as search results. The UI offers direct community URL import instead, without promising all-community automatic discovery.
- Source edits are forbidden during web refresh and CLI publication. Query snapshots are usable only if their `source_community_id` matches the current confirmed association. Unlinked or rebound old snapshots yield missing data, not old-source rent/yield.
- Header owns the refresh button and management dialog. `housing-rental-data-changed` refreshes summary/detail after confirmation/unlink and refresh completion. Map provider failure must not crash these controls.

## 4. Validation / Error Matrix
| Condition | Result |
|---|---|
| Unknown internal id | 404 |
| Invalid input/source URL | 422 |
| Confirm absent/rejected candidate or source already used by another id | 409 |
| Edit during active web refresh or CLI publish | 409 |
| Ignored keyword, challenge/unrecognized page, upstream unavailable | 502 with actionable link import/retry message |
| Legacy migration invalid / DB unreadable | 503; never silently empty |
| No confirmed associations | refresh 422, with management action in UI |

## 5. Good / Base / Bad
- Good: paste a verified community page, review source address/phase, confirm once, update from header; restart retains it.
- Base: keyword search unavailable -> honest error -> public website search + direct link import.
- Bad: import all-city random rows as keyword matches; auto-confirm a similar name; read old source snapshot after rebind.

## 6. Tests Required
`test_rental_sources.py`: one-time migration; existing volume seed; unlink not resurrected; uniqueness; absent/rejected candidate; explicit rejection restore; source URL constraints; structured links vs unrelated navigation; ignored search query and client cleanup; valid empty page; active worker/CLI exclusion; changed-source snapshot hidden; API lifecycle/upstream errors.
Frontend `rental-sources.test.cjs`: evidence, confirmation action, no-map management CTA, safe source links. Existing rental suites remain mandatory. Browser verify production app, desktop/mobile management, real low-volume URL import and confirmation using disposable SQLite data.

## 7. Wrong vs Correct
```python
# Wrong: request accepted does not mean the site applied the keyword.
return all_community_links(client.fetch('/house/?keyword=target'))
# Correct: verify keyword signal before parsing candidates; otherwise return actionable 502.
if actual_keyword != requested_keyword:
    raise ValueError('来源搜索未应用关键词')
```
```python
# Wrong: recreate seeds every startup; deleted mappings silently return.
# Correct: one transaction + persistent initialization marker; runtime DB owns changes.
if not imported:
    import_validated_seed()
    mark_imported()
```
