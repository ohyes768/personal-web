# Kids Catalog backend

## Pre-Development Checklist

Read main.py, downloader.py, [device directory contracts](./device-directory.md), [manual import contracts](./manual-import.md), [audio tag rules](../../../guides/kids-audio-tags.md) and [Windows testing](../../testing-environment.md). FastAPI routes are synchronous with background threads for slow work; SQLite connections are operation-scoped. Never use candidate albums/jobs as the sole durable device library. Reuse Mutagen validation, and do not mutate existing audio tags from directory generation.

## Quality Check

Run `.venv/Scripts/python -m pytest -q` from backend/kids-catalog; pytest basetemp stays on the project drive. Keep fixture audio real and assert actual publication, not merely unchanged output. Run frontend TypeScript and production build for API consumer changes. NAS/MA playback remains a separate integration check.
