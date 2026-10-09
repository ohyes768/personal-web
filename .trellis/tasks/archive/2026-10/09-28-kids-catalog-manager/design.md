# Design: 0–1岁儿童音频管理服务

## Architecture

Create `apps/kids-catalog` as a Next.js page with `basePath=/kids`, and `backend/kids-catalog` as a single-worker FastAPI service. The backend owns monthly collection, SQLite persistence, durable download job state, and the local music directory. The frontend never accesses provider pages or the music filesystem directly.

`nginx/web.conf` exposes `/kids` to the frontend and rewrites `/api/kids/*` to the backend's `/api/*` routes. `docker-compose.nas.yml` attaches both services to `app-net`, mounts a named data volume at `/app/data`, and bind-mounts `${KIDS_MUSIC_HOST_PATH:-/home/ohyes768/xiaomusic/music}` at `/music` for the backend only.

## Data model

- `snapshots`: month, collected_at, source outcome, candidate_count.
- `albums`: platform, album_id, title, source URL, age evidence, confidence, first/last seen month.
- `download_jobs`: album FK, status (`queued`, `downloading`, `downloaded`, `needs_authorization`, `failed`), reason, created/updated timestamps.
- `downloaded_files`: platform, album_id, track identity, relative path below `/music`, byte length, checksum, completed timestamp. A unique platform/album/track key makes queueing idempotent.

## Collection and refresh

The backend imports the collector as an internal library rather than shelling out. It writes a new `snapshots` record and upserts the received candidates. A local scheduler runs at 03:15 on day one in `Asia/Shanghai`; manual refresh has the same source rate limits. Previous snapshots remain available and a failed source response is recorded instead of substituted with broad children content.

## Download flow

Clicking Download posts an album ID. The backend first checks `downloaded_files` and returns the existing result if found. Otherwise it creates one queued job. A single in-process worker takes the next job. The current resolver accepts only a provider-supplied, authorised direct media URL; unavailable, login-required, paid, or unapproved media changes the job to `needs_authorization` and stores the reason. A successful download streams to a temporary file below `/music`, verifies nonzero content, atomically renames it, hashes it, then records the completed file.

No platform credentials are stored in SQLite. A later authorised integration can read secrets from `.env` and provide a resolver without changing the UI or job model.

## UI

The page shows month navigation, the latest refresh time, a manual refresh button, and a compact table of source title, platform, age evidence, status, and action. Download controls disable while queued/downloading and become “已下载” after the backend reports a file. `needs_authorization` presents the recorded reason instead of retrying.

## Operations and rollback

The service gets ports 8098 and 3009, matching the next unused project ports. It uses one backend worker because the scheduler and download worker are in-process. Rollback consists of removing `/kids*` and `/api/kids*` routes plus the two Compose services; music files and the named database volume remain untouched.