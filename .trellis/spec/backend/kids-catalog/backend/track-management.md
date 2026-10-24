# Downloaded track management

Applies to src/main.py (Catalog track methods + track routes), apps/kids-catalog/app/track-manager.tsx, apps/kids-catalog/app/page.tsx.

## 1. Scope / Trigger

Downloaded albums can be managed per track: list and delete local audio files. Exists because
manually imported albums are often collections where the user keeps only a few episodes
(e.g. 《听，小蜗牛艾玛》 18 tracks → keep the 完整版 only).

## 2. Contracts

- Track identity is the **file name** on disk (`001-标题.m4a`); the album folder is the source of
  truth — no track table. Audio suffixes: `.mp3` / `.m4a` (`AUDIO_SUFFIXES`, same口径 as device
  collection `scan()`).
- `GET /api/albums/{id}/tracks` → `{'tracks': [{'file', 'title', 'size'}]}` sorted by file name;
  `title` strips the `NNN-` download prefix. 404 only when the album does not exist; an album
  with no folder yet returns an empty list.
- `DELETE /api/albums/{id}/tracks` body `{'file': str}`. Plain file name only (no separators,
  no `..`, suffix whitelisted) — path traversal rejected with 422. Unknown file → 404. Job in
  `queued/running` → 409 (never race the download thread). Success → `{'downloaded_tracks',
  'size_bytes', 'status'}`.
- Job sync after delete: remaining > 0 → `status='partial'`, `downloaded_tracks`/`size_bytes`
  recomputed, reason `用户删除曲目，剩余 N 首`; remaining = 0 → **job row deleted**, album falls
  back to `not_downloaded`. `_backfill_sizes` never overwrites this (it only fills NULL sizes).
- Completion ledger invalidation: `completions.mark_failed(folder)` sets `incomplete` — it is
  **update-only**, so albums never confirmed in the ledger are untouched. Generation re-scans the
  folder anyway (manifest drift detection), regeneration is the fix.
- `queue()` retryable statuses are `('failed', 'needs_authorization', 'partial')`: a thinned
  album can be re-queued via 补全下载; `download_album` skips existing files, so a re-run only
  fetches what was deleted. Statuses `done/queued/running` stay idempotent.

## 3. Frontend

- Card entry: done/partial albums show a `曲目` manage button next to the download button;
  partial's download button becomes enabled `补全下载`.
- Modal (`track-manager.tsx`): fetches tracks on open, per-row delete, refreshes the list and
  the card badges (`onChanged=load`) after each delete; footer explains restore + playlist
  regeneration. Overlay click closes.

## 4. Tests Required

pytest must cover: track listing (sorted, prefix-stripped, empty, unknown album), delete sync
(file gone, job partial with recomputed counts, ledger invalidated), delete-last-track job
removal + re-download path, bad filename variants (traversal, separators, suffix, missing,
running-download 409), and partial requeue. Frontend: TypeScript and production build.
