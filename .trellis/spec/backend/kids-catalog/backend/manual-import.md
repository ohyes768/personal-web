# Manual album import contracts

Applies to src/link_import.py, src/main.py (Catalog/import endpoint), apps/kids-catalog/app/page.tsx.

## 1. Scope / Trigger

Manual import is a second source of albums besides the monthly chart. It exists because the chart
cannot cover albums the user finds on their own. It reuses the existing download and device
collection pipeline; it does not introduce a second downloader or a second catalog.

## 2. Signatures / Storage

- `parse_album_link(url) -> (platform, album_id)`; platform is `喜马拉雅`, `蜻蜓FM`, `网易云歌单`
  or `网易云专辑`, matching the strings `Downloader.list_tracks` dispatches on. Accepts missing
  scheme, www/m/no subdomain, trailing slash and query string. WeChat share paths
  `selfshare/albumnew/{id}` and `selfshare/album/{id}` parse to the same album id. Single-track
  links are rejected.
- `probe_album(platform, album_id) -> dict` with `title`, `url`, `track_count`, `sale_type`;
  raises `LinkImportError` for paid, offline, missing and network failures.
- `POST /api/albums/import` body `{"url": str}` → 200 `{album_pk, title, job_id, status, reason}`;
  422 with a user-readable `detail` for every rejection.
- `albums.source` is `chart` or `manual`. Existing rows default to `chart`; the column is added in
  place with `alter table ... add column source text not null default 'chart'`.

## 3. Platform paid detection (verified against live APIs)

- Ximalaya mobile track API: paid state lives on the **track** (`isPaid`); the album payload has no
  paid field. Sample page 1; if every sampled track is paid, re-check the last page before
  rejecting, so an album whose first page happens to be free is not misread as wholly paid.
  `ret == 924` means offline **or** nonexistent — but since 2026-10 the platform retires albums
  from this new track API while the legacy `mobile/v1/album/single` endpoint still serves them
  (album metadata, track list, and `tracks/{id}.json` direct links all stay live; verified on
  2026-10-24 with albums 16350309 / 3715099). Track listing therefore goes through
  `downloader.xm_tracks_page`, which falls back to the legacy endpoint on 924 and normalizes its
  response to the new shape (album title injected into each track's `albumTitle`). Only when both
  endpoints return 924 is the album treated as truly offline. Chart-side
  `ximalaya_album_available` stays strict on the new API: the chart must not collect retired
  albums.
- Qingting capi: paid state lives on the **channel** (`vip_label == "会员畅听"`, equivalent to the
  web chart's `sale_type == 1` — 9/9 paid and 5/5 free channels matched). Track-level `isfree` is
  NOT a paid signal: it marks the free episodes inside a member album, and those are the ones that
  actually download. A missing channel returns HTTP 400.
- Netease (2026-11-02 verified against live APIs, all anonymous): paid state is **per track**,
  read from `fee` on `/api/song/detail/?ids=[...]` — `fee=8` downloads, `fee=1` is VIP.
  `privilege` is null on that endpoint and must not be used. The authoritative download decision
  is still the player endpoint: `code=200` + url → downloadable, `code=-110` → VIP not released,
  `code=404` or missing url → no source. A Netease playlist mixes free and VIP tracks, so
  **album-level paid detection does not exist**: `probe_album` returns `sale_type=None` for both
  playlists and albums. Never return `sale_type=1` for Netease — that would make `Catalog.queue()`
  skip the whole collection as paid.

### Netease interface contracts (2026-11-02, all anonymous, no login or signature)

- Playlist metadata + full track ids: `GET /api/v3/playlist/detail?id={id}` → `playlist.trackIds`
  is complete (verified 965 tracks, no truncation). `playlist.tracks` holds only the first 10 and
  must not be used as the track source.
- Album metadata + full tracks: `GET /api/v1/album/{id}` → `songs[]` in one response (verified
  742 tracks). `/api/album/{id}` (no `v1`) returns an empty `songs` array — always use `/v1`.
- Track details: `GET /api/song/detail/?ids=[...]` — **batch cap 200** (300 ids returns 201
  songs, 965 returns 0). Request order is preserved.
- Direct links: `GET /api/song/enhance/player/url?ids=[...]&br=128000` — **batch cap 200**, and
  **the response order does NOT match the request order**. Always index by `id`; zipping the
  response against the request produces silently wrong downloads (this happened during
  implementation and reversed the paid/free conclusion). Links expire in ~20 min (`expi=1200`),
  so fetch a batch, download it, then fetch the next one.
- `br=128000` is the sane choice; `br=999000` silently downgrades to 320k.
- Download needs only a `User-Agent`; no Referer is required (a Netease Referer is sent anyway).
- `/song/media/outer/url?id={id}.mp3` is NOT a usable availability signal — the same id returns a
  real redirect on one request and `302 → /404` on another.

### Netease identity and links

- **Playlist ids and album ids share one numeric space** (verified: id `2884035` is both the
  playlist 「原创榜」 and the album 「소녀괴담 OST」). They must use two distinct platform names
  (`网易云歌单` / `网易云专辑`) so `albums`' `(platform, album_id)` key stays unique. Do not prefix
  `album_id` instead: it is interpolated into request URLs.
- Supported link shapes: `music.163.com/playlist?id=`, `music.163.com/album?id=`, the `/m/` mobile
  variants, the `#/playlist?id=` hash route (strip the `#` segment before matching), and a missing
  scheme.
- `163.cn` short links are **not** supported (the host was unreachable: TLS EOF / HTTP 502).
  Reject them with a message asking for the full link; do not follow the redirect.
- Single-track `music.163.com/song?id=` links are rejected like the other platforms.

### Per-track skip reasons

`DownloadReport` carries `skip_reasons: tuple[SkipReason, ...]` (a `NamedTuple`, so the frozen
dataclass stays hashable) and `DownloadReport.skip_summary()` renders it. `main.py` appends the
summary to the job `reason`. Netease 403/404 on the direct link counts as **skipped** (source
gone), while timeouts and other errors count as **failed** — a network fault must never be
reported as a successful download.

## 4. Lifecycle

- `Catalog.refresh()` only retires `source='chart'` rows; manual albums and their jobs survive the
  monthly refresh. The refresh upsert never overwrites `source`.
- Import upserts the album with `source='manual'` and then delegates to `Catalog.queue()`, so the
  idempotency rules (existing non-failed job returns as-is; `failed`/`needs_authorization` requeue)
  and the download thread stay in one place.
- Re-importing an album that is also in the chart flips it to `manual`: the user asked for it
  explicitly, so it must survive the next refresh.
- Device collections are unchanged: candidates are `albums join jobs where status='done'`, so a
  manual album becomes a collection candidate with no extra work.

## 5. Frontend

- The import bar is permanent in the catalog header: paste a link, press 获取, one step.
- A manual album shows a 手动添加 badge and does not claim an age basis; its detail line reads
  用户自主选择 · 不做年龄筛选.
- The 本月精选 heading takes its timestamp from chart rows only — a manual album's `last_seen` is
  its import time and would otherwise relabel the month.
- The import placeholder lists every supported source: 喜马拉雅 / 蜻蜓FM / 网易云歌单·专辑.
- `sale_type == null` renders the 付费未知 badge; Netease rows instead show 逐曲判定 with a
  tooltip explaining that a playlist mixes free and VIP tracks.

## 6. Tests Required

pytest must cover link parsing (every platform, scheme-less, trailing slash, single-track
rejection), every probe rejection branch with the network layer mocked, import idempotency, and
manual albums surviving `POST /api/refresh`. For Netease, also cover: the hash route and mobile
`/m/` paths, short-link and single-track rejection, the playlist/album id-collision split, batch
capping at 200, **player-url responses whose order differs from the request order**, and the
distinction between skipped (VIP / no source) and failed (network). Frontend: TypeScript and
production build.
