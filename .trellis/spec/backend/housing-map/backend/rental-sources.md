# Rental source management contract

> 2026-10-23: matched Xingfuli pilots take precedence over Fang for that community. See [Xingfuli rentals](./xingfuli-rentals.md). Confirmed source selection/removal uses `providers.active_sources`; candidate discovery remains Fang-only. Unlink removes the active provider, allowing an existing Fang association to become effective. Snapshots must match provider as well as ID.

> After explicit `tmsf-directory-v1` migration, [TMSF directory workflow](./directory-flow.md) supersedes multi-source admission/review and defines task eligibility. Stored history and pre-migration behavior remain readable.


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

## Unified rental update and review (2026-10-14)
- 2026-10-30：`association.eligible_communities` 在目录迁移前后均排除有效 `new_house`，因此批量 full/incremental/恢复、待关联列表、单小区探查和采集共用相同门槛。迁移后读取 admitted 投影的 `market_state`；迁移前检查 matched TMSF 来源的 `effective_market_state`。售完的历史 new_house 必须按 second_hand 恢复原有资格判断；未知状态或零挂牌不推断新房。不删除历史来源、租金与人工决定。`test_newhouse_rental_skip.py` 覆盖在售/尾盘/待售、目录前后路径、批量零请求、手动探查拒绝及售完恢复。
- With the authoritative directory present, `/rentals/refresh` first checks active Binjiang communities classified residential by effective source evidence. Unknown/pending/non-residential and deleted entries are excluded; Amap alone is not proof of residential use. Existing valid Fang mappings are reused without searching and collected before missing-source discovery.
- Unmapped communities reuse pending candidates, then use bounded keyword discovery (5 searches per run, one name and at most one alias per community). Search must prove the requested keyword was applied. An upstream validation/request failure stops further discovery for that run; existing sources have already entered collection. New associations are collected next round. Empty searches are cached for 24 hours using `searched_at`, which must not be refreshed merely by subsequent checks. Budget-deferred targets are checked first next run. Shared Fang cooldown and detail cache apply; a pre-existing cooldown counts as deferred, not searched/failed, and does not advance searched_at.
- New candidates do not inherit an external district from the internal community. Exact name/alias, uniqueness and actual location/address evidence remain required for automatic association. Manual unlink/reject, ignored identities and existing mappings are never overwritten.
- GET `/rentals/association-tasks` returns current eligible unmapped community reviews with candidates, including communities that have no rental source at all (`reason='missing'`) so the on-demand probe stays reachable from the management list. POST `/rentals/association-tasks/{cid}` accepts `action=bind|skip|reopen`, with one `candidate_id` for bind. Manual writes use the rental service edit/publish exclusion and revalidate pending source, active target, rejected pair and target uniqueness in the binding transaction.
- Review metadata is stored under `community_registry.meta` keys `rental_review:{cid}`. Skip preserves identities, samples and the community, recording the candidate fingerprint; unchanged skipped items stay quiet. Changed candidates reopen review; explicit reopen allows another search. There is no new writable mapping store.
- The update component displays `stage` and `association` counts (targets/excluded/checked/matched/pending/skipped/missing/failed/deferred). A finished check with pending/missing/failed/deferred items is partial_failed, even when no crawl could run; that run never clears old snapshots. Post-bind crawling and publishing recheck membership and current mapping.
- The UI uses the management page review panel: one candidate selection or skip, no pasted URL workflow and no multiple Fang sources for one community. The community detail source manager no longer offers a URL input either; the Xingfuli path is a click-only probe (see [discovery and probe](./xingfuli-discovery.md)). Known sources with no listings differ from missing/failed source discovery. The legacy explicit-link API remains for compatibility but is not part of this user flow.

## Discovery diagnostics
- Source discovery logs start/completion and failures with community identity, requested public URL, stage (`fetch`, `keyword_validation`, `parse_listing`), HTML character count, bounded title/actual keyword, exception type and traceback. Never log full HTML, request headers or cookies. Detail enrichment failures remain reviewable candidates with missing address, but must emit a warning with the detail URL and traceback.
- Batch association logs the triggering search failure and final request/deferred counts. `failed` counts only a community whose actual discovery raised an error. Unattempted communities after upstream pause/budget exhaustion use `deferred` and review reason `search_deferred`, retain their previous searched_at, and are prioritized on the next update. Log `requests` and `deferred` separately. Deferred-only runs remain partial_failed. Frontend defaults absent deferred to 0 for older job payloads; old persisted failed totals are historical and are not guessed/reclassified on read.
