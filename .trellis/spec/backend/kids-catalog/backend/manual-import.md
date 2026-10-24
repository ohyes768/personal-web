# Manual album import contracts

Applies to src/link_import.py, src/main.py (Catalog/import endpoint), apps/kids-catalog/app/page.tsx.

## 1. Scope / Trigger

Manual import is a second source of albums besides the monthly chart. It exists because the chart
cannot cover albums the user finds on their own. It reuses the existing download and device
collection pipeline; it does not introduce a second downloader or a second catalog.

## 2. Signatures / Storage

- `parse_album_link(url) -> (platform, album_id)`; platform is `喜马拉雅` or `蜻蜓FM`, matching the
  strings `Downloader.list_tracks` dispatches on. Accepts missing scheme, www/m/no subdomain,
  trailing slash and query string. Single-track links are rejected.
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
  `ret == 924` means offline **or** nonexistent.
- Qingting capi: paid state lives on the **channel** (`vip_label == "会员畅听"`, equivalent to the
  web chart's `sale_type == 1` — 9/9 paid and 5/5 free channels matched). Track-level `isfree` is
  NOT a paid signal: it marks the free episodes inside a member album, and those are the ones that
  actually download. A missing channel returns HTTP 400.

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

## 6. Tests Required

pytest must cover link parsing (both platforms, scheme-less, trailing slash, single-track
rejection), every probe rejection branch with the network layer mocked, import idempotency, and
manual albums surviving `POST /api/refresh`. Frontend: TypeScript and production build.
