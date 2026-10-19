# Device directory contracts

## 1. Scope / Trigger

Applies to device_collections.py, music_assistant.py, download lifecycle hooks in main.py, and the /kids device-playlist component. Read before changing numbering, completion tracking, generation or MA matching.

## 2. Signatures / Storage

- `DeviceCollections(data_dir, music_dir, ma)` owns `/app/data/device_collections.sqlite3`.
- `completions(folder PK, manifest, status)` survives candidate cleanup. Manifest is ordered `[filename,size,mtime_ns]` records; status is downloading/incomplete/complete.
- `publication(id=1,snapshot,targets)` contains only the current published snapshot and number-to-MA-URI mapping.
- `generation(id=1,token,started,status,error,skipped)` provides a SQLite cross-process lease. Acquire with `BEGIN IMMEDIATE`; an expired 15-minute lease permits a new worker. Only the matching token may publish or finish.
- `POST /api/collections/generate` → 202; `GET /api/collections` → `{snapshot,generation}`; `POST /api/collections/confirm` accepts `{folder}`.
- Device endpoints: `GET /api/device/v1/collections` and `GET /api/device/v1/collections/by-number/{number}?revision=...`.

## 3. Contracts / Environment

- Public snapshot: `schema_version=1,revision,generated_at,items[{number,title,track_count}]`.
- Successful resolution also includes `media_type=album,ma_media_uri`. Check current revision before resolving; never reinterpret an old number against a new snapshot.
- Generate only on a manual request. Sort `(track_count,stable_path_hash)` then number 1-N. Download success does not publish.
- Candidate albums/jobs are disposable; migrate legacy done rows with matching totals before candidate refresh. Never overwrite a newer ledger entry during migration.
- Validate direct MP3/M4A files with Mutagen, reject temporary files, links, directories and invalid/duplicate filename numbers. Generation does not write tags or audio.
- Complete manifests must still match at generation and immediately before publication. Recheck ledger status in the publication transaction. Zero valid collections and global failures preserve the prior snapshot.
- MA variables: `KIDS_MA_URL`, `KIDS_MA_TOKEN`, `KIDS_MA_MUSIC_ROOT` (default `/music`). Only backend receives the token. Music root converts MA absolute paths into relative NAS identities.
- MA 2.8.2 JSON-RPC: `music/tracks/library_items` paginated by limit/offset; `music/albums/album_tracks` with `in_library_only=false` validates actual full playback expansion; `music/item_by_uri` checks target availability on resolution. Use available filesystem_local provider mappings and require an exact file set, unique album, correct filename-derived track numbers and a single disc. Similar titles alone are never proof.
- Maximum 500 published collections, 256 UTF-8 bytes per title, 128 KiB compact snapshot JSON. No silent truncation. Skipped reasons are visible.
- nginx and Next map `/api/kids/:path*` to backend `/api/:path*`. Never add the frontend `/kids` basePath to those API requests.

## 4. Validation & Error Matrix

| Condition | Result |
| --- | --- |
| No snapshot / unknown number | 404 directory_missing / number_missing |
| Old revision | 409 revision_expired; refresh and reselect |
| MA target unavailable | 503 target_unavailable |
| Generation already running | 409 generation_running |
| Invalid manual completion / running download | 422, no completion change |
| Unconfirmed / incomplete / mismatched files | Skip with reason, no guessed mapping |
| MA auth/network/format failure, capacity overflow, file mutation during generation | Failed generation, old snapshot retained |

## 5. Good / Base / Bad Cases

- Base: completed 30/8/15-track folders publish as 8/15/30, numbered 1/2/3.
- Good: a newly downloaded 5-track folder leaves current numbering untouched until generation; new generation puts it first and invalidates prior revision lookups.
- Bad: a one-file local album expands to two MA tracks because a remote provider added an extra track. Reject this album rather than publishing a misleading one-track mapping.

## 6. Tests Required

Run `.venv/Scripts/python -m pytest -q` inside backend/kids-catalog. Assert actual publication and counts, old-revision rejection, durable completion migration, failure preservation, generation mutual exclusion, file changes during generation, overflow, and actual album expansion. Adapter tests verify Bearer auth, pagination, path mapping and sanitization of upstream failures. Frontend checks: `pnpm exec tsc --noEmit`, `pnpm build`, desktop/mobile UI and generation action. Real NAS/MA/ESP32 validation remains distinct from fixtures.

## 7. Wrong vs Correct

Wrong: reuse albums/jobs IDs as stable device IDs, publish on every downloaded file, resolve old number using the newest snapshot, or match albums by title.

Correct: independent completion ledger and publication, manual whole-snapshot replacement, revision plus number resolution, and exact file/track/album matching.
