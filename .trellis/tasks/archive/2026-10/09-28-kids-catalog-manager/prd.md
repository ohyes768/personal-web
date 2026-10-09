# 0–1岁儿童音频管理服务

## Goal

Provide a NAS-hosted management page that lists the current month's strict 0–1-year-old album candidates, lets the user queue authorised downloads, and remembers completed local files across monthly refreshes.

## Confirmed facts

- The existing collector outputs strict 0–1-year-old candidate snapshots under `scripts/kids-catalog/data/hot-albums/YYYY-MM-0-1.{json,csv,md}`.
- Qingting FM provides the only current high-confidence records through its public 0–1 age filter. Ximalaya entries are accepted only when a visible title or summary explicitly declares an infant age; the current snapshot has none.
- Existing NAS services use a separate Next.js frontend and FastAPI backend, routes through `nginx/web.conf`, and are built by `docker-compose.nas.yml` plus `scripts/deploy-nas.sh`.
- The NAS music destination is `/home/ohyes768/xiaomusic/music`.
- Downloads may only use publicly accessible or otherwise authorised media URLs. A login-, membership-, or rights-gated item must become `needs_authorization`; the service must not bypass platform access control.

## Requirements

1. Serve a management page at `/kids` and an API under `/api/kids`.
2. Show the current Beijing-calendar-month strict 0–1-year-old candidates, including platform, source URL, age evidence, confidence, collection month, and download status.
3. Refresh the candidate list once per month at 03:15 Asia/Shanghai, retaining past snapshots and deduplicating candidates by platform plus album ID.
4. Provide a manual refresh action that reuses the same collection rules and does not retry repeatedly after a source restriction failure.
5. A download action queues an album only once. The backend records each task durably and runs one download at a time.
6. Downloaded output belongs below `/home/ohyes768/xiaomusic/music`; identical platform, album, and track identities must not download twice. Existing verified local files display `downloaded` on later months.
7. Items without an authorised resolved media URL display `needs_authorization`; no anti-bot, credential bypass, or paid-content bypass is implemented.
8. Add frontend, backend, Docker Compose services, named data volume, music bind mount, Nginx routes, root portal link, and a `deploy-nas.sh kids-catalog` target.

## Acceptance criteria

- `/kids` renders the monthly list and communicates with `/api/kids` behind the Nginx path prefixes.
- The API persists candidates, refresh runs, download jobs, and file fingerprints in a SQLite database mounted at `/app/data`.
- A queued authorised item reaches `downloaded` only after its expected file is written below the mounted music directory; duplicate queue attempts are idempotent.
- An unresolvable or gated item reaches `needs_authorization` with an explanatory message and makes no repeated source requests.
- The Compose configuration validates, Nginx syntax validates in the Nginx image, backend tests pass, and frontend production build passes.

## Out of scope

- Platform account login, CAPTCHA handling, reverse engineering, signature generation, proxy rotation, membership/paid audio downloading, and playback UI.
- Age filtering beyond the current strict 0–1-year-old collector rules.