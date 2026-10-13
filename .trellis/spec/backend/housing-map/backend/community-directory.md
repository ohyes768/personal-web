# Community directory contract

## 1. Scope / Trigger
Applies to community_registry.py, community_directory.py, directory_collection.py, directory_routes.py, CommunityManagement.tsx and community identities consumed by map/price/rental/auction code. User requested one maintained directory in the existing deployment, without fresh-deployment seed or multi-version compatibility design.

## 2. Signatures
- `prepare_directory(DATA_DIR)` backs up current editable inputs to directory-backup once, imports existing IDs/decisions into community_registry.sqlite3, and stores meta.prepared. Restart does not reseed. The same SQLite directory is authoritative thereafter.
- `CommunityRegistry`: communities(deleted=False), sources(), ingest(record), candidates(record), auto_associate(), associate(rid,cid), unlink(rid,cid=None), create_from_source(...), update(...), merge(cid,target), delete(cid,reason), restore(cid), ignore_source(rid), restore_source(rid), resolve(cid), is_ignored(source,kind,sid), events(cid).
- Tables: communities(id,payload,deleted,merged_to), sources(id,source,kind,sid,payload,cid,status,method,evidence,ignored_by), rejected(rid,cid), events(seq,cid,action,payload,created_at), meta(key,value). Source identity UNIQUE(source,kind,sid). Writes use transactions and foreign keys.
- DirectoryJob persists collection_job in meta; thread/event cancellation; restart marks unfinished run interrupted; shutdown joins the worker.

## 3. Contracts
- Existing IDs remain stable; new IDs use local- prefix. Names are not globally unique. Names/aliases are independent from source raw names; NFKC/whitespace normalization never drops phase/directional suffixes.
- New automatic associations require exact name/alias, unique full-name candidate, same district plus exact address or GCJ02 positions within 100m. Missing/ambiguous evidence remains pending; manual decisions and rejected pairs override auto. Geographic closeness alone never associates records.
- Delete means whole community + all currently associated identities, including multiple TMSF or auction sources. It disables subsequent independent detail fetches and business display. History remains. Restore explicitly reactivates records ignored by that community deletion; independent pending-source ignores remain unchanged. Unlink/reject is separate and does not delete the community.
- Source ID renames stay ignored; a new ID with a deleted name is pending and displays possible_deleted, not a global name blacklist. Laipai uses asset/auction identity, preserves observed auction_ids for skip checks across existing rounds.
- Fang active associations remain one per community until snapshot storage supports multiple Fang communities; conflicting manual/auto associations return409. Multiple other source identities are allowed.
- TMSF current list, Fang regional structured links and Laipai asset observations form the candidate union. Unmapped records can become new communities manually, regardless of a TMSF ID. Collection is independent of rental mapping.
- Fang regional samples stay with the source and survive manual association. Queries reuse existing statistics and label regional_sample=true when falling back to discovery samples. Oldest sample date bounds freshness, avoiding false freshness from reimports. Full successful community snapshots take precedence.
- Existing price snapshot IDs are associated through current TMSF mappings; local-only entries are never requested as TMSF IDs. Deleted auction identities disappear even from unmatched auction lists; once registry exists, name fallback cannot override explicit unlink.
- Runtime DATA_DIR defaults to backend/housing-map/data; HOUSING_DATA_DIR can point to an isolated QA directory. Amap is used for geographic enrichment, not name discovery; existing Amap source records remain readable.
- Name collection follows pagination to source exhaustion, detects repeated pages as incomplete, and uses two-second request delays, independent source failures, cancellation and report counters. Shared list pages may still contain ignored records; filter them before independent detail requests. No claim of complete regional coverage.
- Residential classification: tmsf property types (住宅/别墅/排屋/写字楼/商贸/车位) plus fang rental sample property types (住宅/普通住宅) produce a per-community state of residential / non_residential / pending / unknown. Conflicts between tmsf and fang are reported and never silently resolved. tmsf `其他` and fang mixed signals stay pending until verified.
- Filter pipeline: scripts/filter_residential_communities.py consumes the classification report and writes binjiang_residential_communities.json / binjiang_pending_communities.json / binjiang_non_residential_communities.json. The import (prepare_directory) prefers the residential list and excludes the non_residential ids, while leaving sources for non_residential rows untouched. Original inputs are snapshotted to data/diagnostics/pre-residential/ before any rewrite.
- New management Tab fetches independently of map/property filters; default district滨江, existing萧山 records remain selectable. Old header rental-management CTA navigates to this Tab.

## 4. API / Validation & Error Matrix
External /api/map/directory, backend /api/directory. Envelope success/data.
- GET communities?q&district&deleted&page&page_size → items,total,page; POST communities {name,aliases,district,address}; GET/PUT/DELETE communities/{cid}; POST .../restore and .../merge {community_id}.
- GET sources?q&district&source&status&page&page_size; GET sources/{rid} → candidates,possible_deleted,sample_count (raw samples omitted); POST .../associate {community_id}; DELETE .../associate?community_id (reject target or unlink current); DELETE sources/{rid}; POST .../restore and .../create-community {name,aliases,district,address}.
- POST auto-associate → matched; GET/POST/DELETE collection. POST accepts sources from tmsf/fang/laipai; starts202.
- Invalid parameters422; unknown detail404; invalid/deleted target, duplicate Fang binding, active collection or invalid restore409; SQLite/filesystem failures503. Upstream errors are per-source reports. Corrupt directory must not silently fall back to JSON.

## 5. Good / Base / Bad
Good: collect names → sufficient-evidence auto associations → manually resolve pending → delete whole community → restart/collect skips linked identities → explicit restore. Base: a source fails or returns repeated pages or ends before its reported count → retain discovered data and explain partial coverage. Bad: equate same name with same community; overwrite manual edits on startup; delete historical source samples; treat source limits as full-region collection.

## 6. Tests Required
test_community_registry.py: evidence/ambiguity, missing evidence, manual override/unlink, delete/restart/rename/restore, no name blacklist, merge/redirect, late association rejected, ignored rental seed no request. test_directory_collection.py: ignore/report/independent failures. test_directory_api.py: CRUD/association/deleted queries/restore/422. test_directory_integration.py: once-only current-data import, manual names authoritative, map/rental deletion, auction unlink and ignored identities. Frontend community-management.test.cjs: original identity/method/evidence and safe links. Browser isolated create-from-source/delete/restore plus desktop/mobile. Keep rental API regional_sample contract synchronized.

## 7. Wrong vs Correct
Wrong: startup rewrites directory from binjiang_communities.json, restoring deleted communities. Correct: prepare once, then read the durable registry and record all user decisions there.
Wrong: after unlink, auction exact-name fallback immediately reattaches. Correct: when registry exists, only effective registry associations determine identity.
Wrong: source record is inserted then orphan community is created on a failed link. Correct: create_from_source validates pending status and creates+associates in one transaction.
