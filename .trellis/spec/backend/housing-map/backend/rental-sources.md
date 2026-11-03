# Rental source management contract

> 2026-11-03: Fang is retired. The Fang crawler, request policy, detail cache, mapping ledger (`rental_sources.sqlite3`), candidate pool and link-import flow are deleted; `providers.CURRENT_RENTAL_PROVIDER` is `xingfuli` and the community registry is the only authority. Historical Fang associations, samples and snapshots stay readable but never act as a current source, never enter current rent statistics and never count as residential-use evidence. The live contract is [Xingfuli rentals](./xingfuli-rentals.md) plus [Xingfuli discovery](./xingfuli-discovery.md).

> 2026-10-23 (superseded by the 2026-11-03 retirement): matched Xingfuli pilots took precedence over Fang for that community. Confirmed source selection/removal uses `providers.active_sources`; candidate discovery was Fang-only. Unlink removed the active provider, which used to let an existing Fang association become effective — that fallback no longer exists.

> After explicit `tmsf-directory-v1` migration, [TMSF directory workflow](./directory-flow.md) supersedes multi-source admission/review and defines task eligibility. Stored history and pre-migration behavior remain readable.

> The community registry ([Community directory](./community-directory.md)) is the authoritative editable store. `SourceStore` is now only a thin adapter over it: no second writable mapping store, no candidate pool, and directory deletion decisions are never overridden.

## 1. Scope / Trigger
Applies to `rental_reference/sources.py`, `rental_source_routes.py`, source membership in `refresh.py`, rental query snapshot selection and the frontend source manager.

## 2. Signatures
- `SourceStore(mappings_path)` reads the community registry next to `mappings_path`; it raises `SourceRegistryUnavailable` when no registry exists. It never creates a mapping database.
- `get(community_id)` -> `{mapping, candidates}`; `candidates` is always `[]` (the retired Fang candidate pool is neither exposed nor confirmable).
- `all_mappings()` -> `{community_id: mapping}` for the current Xingfuli sources only.
- `pending_counts()` -> `{}`; there is no pending Fang candidate queue.
- `remove(community_id)` unlinks the current Xingfuli source. It never falls back to a historical Fang association.
- `RentalRefreshService.change_sources(action)`: holds web-start mutex, rejects live worker, and takes `RentalPublishLock(rentals_dir/'rental_publish')` while applying the edit.
- Data lives in the registry tables `sources`/`communities`/`meta`; `rental_sources.sqlite3` and the `rental_community_mappings.json` ledger are gone as runtime dependencies.

## 3. Contracts
| Method | Path | Meaning |
|---|---|---|
| GET | `/rentals/sources` | `data.communities[]`: internal id/name/area, current mapping and candidate_count (always 0) |
| GET | `/communities/{id}/rental-source` | internal community, current mapping and the (always empty) candidate list |
| POST | `.../rental-source/search` | retired: 410, no side effect, no request to any platform |
| PUT | `.../rental-source` | retired: 410, no side effect; use the Xingfuli homepage selection |
| DELETE | `.../rental-source` | unlinks the current Xingfuli source; does not delete historical snapshots and never reverts to Fang |
| DELETE | `.../rental-source/candidates/{source_id}` | retired Fang candidate endpoint: 410, no side effect |

External prefix is `/api/map`, backend prefix `/api`. Success envelope remains `{success:true,data}`.

- The registry is the only authority. The old legacy JSON ledger, its one-time seed import and the Docker seed copy are removed; the file may still exist in a data directory but is never read and never re-imported.
- Source selection is `providers.active_sources(registry)`: matched, non-deleted Xingfuli sources only. Historical Fang associations stay in the registry for audit and explicit unlink/ignore, but they are not active sources and never compete for a community.
- The only way to create a rental source is the Xingfuli probe/matching flow (see [discovery and probe](./xingfuli-discovery.md)). The 410 shells above keep the old request models so malformed bodies still fail validation (422) before the 410 is raised.
- Source edits are forbidden during web refresh and CLI publication. Query snapshots are usable only if their provider and `source_community_id` match the current confirmed association. Unlinked or rebound old snapshots yield missing data, not old-source rent/yield.
- Header owns the refresh button and management dialog. `housing-rental-data-changed` refreshes summary/detail after unlink and refresh completion. Map provider failure must not crash these controls.

### Retired Fang flow (history, no longer executable)
The Fang keyword/link discovery, the `FangClient` URL validation, the keyword-proof rule (`pageConfig.keyword`), the structured-link candidate parsing and the one-time JSON seed import described in the 2026-10-12 contract are all removed with the Fang modules. They are kept here only as history: the live source is chosen by clicking a homepage in the Xingfuli probe.

## 4. Validation / Error Matrix
| Condition | Result |
|---|---|
| Unknown internal id | 404 |
| No community registry | 503「小区目录尚未准备好，租金来源暂不可用」; never silently rebuilt from an old file |
| Registry unreadable / corrupt | 503 |
| Retired Fang write entry (search / confirm / candidate reject) | 410, no side effect and no platform request |
| Malformed search/confirm body | 422 (the old input models still validate) |
| Edit during active web refresh or CLI publish | 409 |
| No current source for a community | refresh 422, with the management action in the UI |

## 5. Good / Base / Bad
- Good: probe finds the community homepage, the human selects it, the entry and the listing ownership are verified, the source is bound; restart retains it and the header can update the rent.
- Base: the community has no source yet -> the pending list shows `reason='missing'` and the on-demand probe stays reachable from the management list.
- Bad: read an old Fang snapshot as current rent; fall back to Fang after unlinking Xingfuli; re-import the legacy mapping JSON on startup; expose the retired candidate pool again.

## 6. Tests Required
`test_rental_sources.py`: registry-backed mapping read; no registry -> 503; no mapping database or seed file is created; retired search/confirm/candidate endpoints answer 410 with no side effect; unlink does not resurrect a historical source; edit exclusion during refresh/CLI publish; changed-source snapshot hidden; API lifecycle errors. The retired Fang-only cases (seed migration, keyword discovery, link import, candidate rejection) are removed together with the code they covered. Frontend `rental-sources.test.cjs`: evidence, unlink action, no-map management CTA, safe source links. Existing rental suites remain mandatory. Browser verify the production app, desktop/mobile management and the unlink flow using disposable registry data.

## 7. Wrong vs Correct
```python
# Wrong: a second writable mapping store next to the authoritative registry.
store = SourceStore(path.with_name('rental_sources.sqlite3'))
# Correct: adapt the registry; without it the feature is unavailable, not rebuilt.
registry = existing_registry(path.parent)
if not registry:
    raise SourceRegistryUnavailable('小区目录尚未准备好')
```
```python
# Wrong: recreate seeds every startup; deleted mappings silently return.
# Correct: the registry owns the changes; the old ledger is never imported.
if not imported:
    import_validated_seed()
    mark_imported()
```

## Unified rental update and review (2026-10-14)
- 2026-10-30：`association.eligible_communities` 在目录迁移前后均排除有效 `new_house`，因此批量 full/incremental/恢复、待关联列表、单小区探查和采集共用相同门槛。迁移后读取 admitted 投影的 `market_state`；迁移前检查 matched TMSF 来源的 `effective_market_state`。售完的历史 new_house 必须按 second_hand 恢复原有资格判断；未知状态或零挂牌不推断新房。不删除历史来源、租金与人工决定。`test_newhouse_rental_skip.py` 覆盖在售/尾盘/待售、目录前后路径、批量零请求、手动探查拒绝及售完恢复。
- With the authoritative directory present, `/rentals/refresh` collects the eligible Binjiang communities that already have a current source. Unknown/pending/non-residential and deleted entries are excluded; Amap alone is not proof of residential use.
- 2026-11-03：采集任务不再发起房天下搜索，缺来源的小区由独立的「匹配租金来源 / 按需探查」流程处理（见 [Xingfuli discovery](./xingfuli-discovery.md)）；采集默认只消费台账里已确认的幸福里来源。
- New candidates do not inherit an external district from the internal community. Exact name/alias, uniqueness and actual location/address evidence remain required for automatic association. Manual unlink/reject, ignored identities and existing mappings are never overwritten.
- GET `/rentals/association-tasks` returns current eligible unmapped community reviews with candidates, including communities that have no rental source at all (`reason='missing'`) so the on-demand probe stays reachable from the management list. POST `/rentals/association-tasks/{cid}` accepts `action=bind|skip|reopen`; `bind` stays 410 and points to the Xingfuli homepage selection, `skip`/`reopen` keep working. Manual writes use the rental service edit/publish exclusion and revalidate the pending source, active target, rejected pair and target uniqueness in the writing transaction.
- Review metadata is stored under `community_registry.meta` keys `rental_review:{cid}`. Skip preserves identities, samples and the community, recording the candidate fingerprint; unchanged skipped items stay quiet. Changed candidates reopen review; explicit reopen allows another search. There is no new writable mapping store.
- The update component displays `stage` and `association` counts (targets/excluded/checked/matched/pending/skipped/missing/failed/deferred). A finished check with pending/missing/failed/deferred items is partial_failed, even when no crawl could run; that run never clears old snapshots. Post-bind crawling and publishing recheck membership and current mapping.
- The UI uses the management page review panel: one candidate selection or skip, no pasted URL workflow and no second rental source for one community. The community detail source manager no longer offers a URL input either; the Xingfuli path is a click-only probe (see [discovery and probe](./xingfuli-discovery.md)). Known sources with no listings differ from missing/failed source discovery.

## Discovery diagnostics
- Source discovery logs start/completion and failures with community identity, the requested name/channel and the failing step (search / community info / rental entry), bounded title/keyword, exception type and traceback. Never log full HTML, request headers or cookies. Detail enrichment failures remain reviewable candidates with missing address, but must emit a warning with the detail URL and traceback. The per-step and per-stage semantics live in [Xingfuli discovery](./xingfuli-discovery.md).
- Batch association logs the triggering search failure and final request/deferred counts. `failed` counts only a community whose actual discovery raised an error. Unattempted communities after upstream pause/budget exhaustion use `deferred` and review reason `search_deferred`, retain their previous searched_at, and are prioritized on the next update. Log `requests` and `deferred` separately. Deferred-only runs remain partial_failed. Frontend defaults absent deferred to 0 for older job payloads; old persisted failed totals are historical and are not guessed/reclassified on read.
