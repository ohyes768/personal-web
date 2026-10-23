# Device directory contracts

## 1. Scope / Trigger

Applies to device_collections.py, main.py lifecycle hooks and app/device-playlist.tsx. This is a local number-to-album-name directory, independent of MA connectivity, indexing and playback readiness. Do not reintroduce MA calls as publication or resolution gates.

## 2. Signatures / Storage

- DeviceCollections(data_dir, music_dir, candidate_source) owns device_collections.sqlite3.
- completions(folder PK,manifest,status) stores filename/size/mtime_ns evidence, independent of disposable candidates.
- publication(id=1,snapshot,targets) keeps the old schema. New writes set targets to '{}'; queries never read targets. No database reset is needed.
- generation(id=1,token,started,status,error,skipped) provides a 15-minute cross-process lease.
- GET /api/collections returns snapshot and generation in one explicit read transaction. Two independent SELECTs can otherwise combine done with a snapshot read before publication. It also returns `candidates` — this month's done albums as `{folder,title,confirmed}` — read from the catalog without the write lock; `confirmed` means the completion ledger holds a `complete` record, not that the files were validated.
- POST /api/collections/generate →202/409; body is optional: `{"folders":[...]}`. Missing body or `folders:null` = every candidate; `folders:[]` → 422; unknown folder → 422 with the unknown names. POST /api/collections/confirm accepts folder.
- Generation filters candidates by the selected folders. Unselected albums enter neither `items` nor `skipped`, and the end-of-run source-consistency check compares only the selected set, so unrelated changes in unselected albums do not fail the publication.

## 3. Request / Response / Environment Contracts

- GET /api/device/v1/collections → schema_version=1,revision,generated_at,items[number,title,track_count].
- GET /api/device/v1/collections/by-number/{number}?revision=... → revision,number,title,track_count. No media_type, MA URI, MA availability checks or playback side effects.
- Candidate source is the Catalog.device_candidates() context manager: current albums JOIN jobs.status=done. Only scan these sanitized folders, retain original titles, never enumerate the whole NAS root. Empty eligible lists preserve the prior snapshot.
- Acquire/release the source guard to read inputs. Reacquire BEGIN IMMEDIATE on Catalog for the final comparison and hold through the device DB commit; always lock Catalog then device DB, matching queueing.
- Validate actual readable nonempty MP3/M4A and stable manifests. Reject temporary downloads, damaged files, links and nested folders. No filename tracknumber or tag/MA requirement. file_order preserves old numeric filename ordering for stored manifests and supports ordinary names.
- Sort by track_count and stable path hash, then number1-N. Only manual successful generation publishes. Refreshing candidates does not delete publication/completions.
- Maximum500 collections,256 UTF-8 bytes/title,128 KiB compact public snapshot JSON; never silently truncate. Individual collection file counts are independent of MA query limits.
- Directory uses only KIDS_DATA_DIR and KIDS_MUSIC_DIR. Existing MA environment variables are irrelevant to generation and lookup. No MA credentials or filesystem paths in public responses.
- nginx/Next maps /api/kids/* to backend /api/*; avoid frontend /kids basePath for API requests.

## 4. Validation & Error Matrix

| Condition | Result |
| --- | --- |
| No snapshot / unknown number | 404 directory_missing / number_missing |
| Old revision | 409 revision_expired, refresh and reselect |
| Already generating | 409 generation_running |
| Empty folder selection / unknown folder | 422, no generation started, previous snapshot retained |
| Invalid completion confirmation / running download | 422 |
| Unconfirmed or changed local files | Skip with explicit reason |
| NAS/global failure, zero valid items, overflow | Failed generation, prior snapshot retained |
| MA offline, unconfigured, missing associations or500-track limit | No effect on directory generation or name lookup |

## 5. Base / Good / Bad Cases

- Base: downloaded30/8/15-file collections publish8/15/30, numbered1/2/3.
- Good: valid NAS collections with501/1106/3000 files are counted without contacting MA; ordinary filenames are supported.
- Bad: refusing a directory item because MA has album=null, trying to repair MA from directory generation, or resolving old numbers against new snapshots.

## 6. Tests Required

Backend pytest must cover no-network/no-MA generation and lookup, full long-collection counts, current-month filtering, sorting, completion migration, file validation, ordinary filenames, stable numeric manifest compatibility, concurrency, candidate mutation, consistent status reads, overflow, failure preservation and legacy targets being ignored. Folder selection must be covered too: filtering to a subset, empty selection rejected, unknown folder rejected, default full generation, and the candidates payload with its confirmation flag. Frontend: TypeScript and production build. Device/HA playback is a separate integration test.

## 7. Wrong vs Correct

Wrong: couple metadata publication to MA album/track matching, expose a stored MA URI on number lookup, or reuse candidate IDs as permanent screen numbers.

Correct: manual durable number/name snapshots, revision-aware metadata lookup and separate playback integration. MA repair work is paused under the user's revised scope.
