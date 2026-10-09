# Implementation: 0–1岁儿童音频管理服务

1. Create the FastAPI package, SQLite repository, collector adapter, monthly scheduler, and durable sequential job worker. Write unit tests for candidate upsert, duplicate queueing, gated media status, and atomic local-file completion.
2. Create API endpoints for health, current month list, refresh, download queue, and job status. Test the endpoints against a temporary database and music directory.
3. Create the Next.js `/kids` page, typed API client, status/action UI, base path configuration, Dockerfile, and production build test.
4. Add backend Dockerfile, Compose services and volumes, Nginx upstream/static/page/API routes, root navigation entry, and the NAS deploy target.
5. Run backend tests, frontend build, `docker compose -f docker-compose.nas.yml config --quiet`, and `nginx -t` in an Nginx container. Do not perform a live NAS deployment in this workspace.