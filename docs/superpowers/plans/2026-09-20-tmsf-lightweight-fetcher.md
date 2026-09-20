# TMSF Lightweight Fetcher Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use inline execution with TDD. Steps use checkbox syntax for tracking.

**Goal:** Make housing-map refresh use an in-process, Chrome-fingerprint HTTP client rather than a spawned scraper script or browser runtime.

**Architecture:** `src/services/tmsf_fetcher.py` owns TMSF transport, parsing, snapshot construction and CLI-safe output helpers. `refresh.py` schedules its blocking per-community operation with `asyncio.to_thread`, keeps existing status/backup semantics, and writes only after the job succeeds. Legacy scripts import this service as thin wrappers.

**Tech Stack:** Python 3.12, FastAPI, asyncio, curl_cffi, pytest, Docker/uv.

---

### Task 1: Define the service contract with failing tests

**Files:**

- Create: `backend/housing-map/tests/test_tmsf_fetcher.py`
- Modify: `backend/housing-map/tests/test_refresh.py`

- [ ] Add tests proving a fetcher sends `impersonate="chrome"`, independently tolerates a failed index or tendency page, and never produces a `visible_listing_unit_price_avg` snapshot.
- [ ] Add a refresh test that injects a deterministic fetcher, asserts only residential IDs are scheduled, progress advances, and fresh rows merge without spawning a process.
- [ ] Run the new tests; expected result before implementation: import/contract failure.

### Task 2: Extract TMSF transport and parsing into a service

**Files:**

- Create: `backend/housing-map/src/services/tmsf_fetcher.py`
- Modify: `backend/housing-map/scripts/fetch_tmsf_price_snapshot.py`
- Modify: `backend/housing-map/scripts/fetch_tmsf_binjiang_communities.py`

- [ ] Move `PriceSnapshot`, page parsers, explicit-price snapshot building and CSV/JSONL serialization into `tmsf_fetcher.py`.
- [ ] Implement a `TmsfClient` backed by `curl_cffi.requests.Session(impersonate="chrome")`, with Chinese browser headers, timeout propagation, and response decoding.
- [ ] Implement `fetch_community_snapshots(community_id, timeout)` so index/tendency failures are collected independently and valid partial data remains available.
- [ ] Turn `fetch_tmsf_price_snapshot.py` into a CLI wrapper around the service without duplicating parsing or transport.
- [ ] Run service/parser tests; expected result: all pass without network access.

### Task 3: Replace subprocess refresh with an in-process task

**Files:**

- Modify: `backend/housing-map/src/services/refresh.py`
- Modify: `backend/housing-map/tests/test_refresh.py`

- [ ] Inject a fetch function into the runner boundary so tests use fixtures rather than external TMSF traffic.
- [ ] Replace `asyncio.create_subprocess_exec` and stdout parsing with an `asyncio.create_task` runner that calls the synchronous fetcher via `asyncio.to_thread`.
- [ ] Preserve lock, cancellation, backup, row merge, CSV rewrite and existing public job fields; report item errors in the existing `errorCount` and `error` fields.
- [ ] Run refresh/API tests; expected result: no spawned process and unchanged endpoint contract.

### Task 4: Package and verify the light transport

**Files:**

- Modify: `backend/housing-map/pyproject.toml`
- Modify: `backend/housing-map/uv.lock`
- Modify: `backend/housing-map/Dockerfile` only if lock/runtime verification requires it

- [ ] Add a pinned-compatible `curl_cffi` runtime dependency and regenerate `uv.lock`.
- [ ] Verify dependency installation, compile backend modules, run all backend tests, and build/check the backend Docker image if Docker is available.

### Task 5: Capture the operational contract

**Files:**

- Modify: `.trellis/spec/guides/new-service-onboarding.md` or a housing-map-specific code-spec if one becomes available

- [ ] Record the refresh endpoint, persistence behavior, data-quality rule, light browser-fingerprint dependency, and good/bad failure cases so future maintenance does not restore the page-wide price average.
