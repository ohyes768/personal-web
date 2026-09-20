# OSM Only Community Boundaries Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the stale Shapefile fallback so community boundaries are emitted only when an OpenStreetMap match is sufficiently credible.

**Architecture:** The offline polygon builder will keep its existing OSM containment, nearest-boundary, and normalized-name strategies. It will no longer read, transform, or match `Hangzhou_202302.shp`. Communities without an OSM match will be absent from the polygon output and the API will therefore return only their point location.

**Tech Stack:** Python 3.12, pytest, OpenStreetMap GeoJSON.

---

### Task 1: Lock the OSM-only matching contract with tests

**Files:**
- Create: `backend/housing-map/tests/test_build_merged_polygons.py`
- Modify: `backend/housing-map/scripts/build_merged_polygons.py`

- [ ] **Step 1: Write the failing test**

```python
def test_main_does_not_need_shapefile_for_unmatched_community(monkeypatch, tmp_path):
    monkeypatch.setattr(builder, "SHP_PATH", str(tmp_path / "legacy.shp"))

    builder.main()

    assert json.loads(output_path.read_text(encoding="utf-8"))["polygons"] == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_build_merged_polygons.py::test_name_match_rejects_a_boundary_more_than_300_metres_away -v`

Expected: FAIL with `FileNotFoundError` because the existing builder tries to read the missing legacy Shapefile.

- [ ] **Step 3: Write minimal implementation**

Remove `match_shapefile`, the Shapefile read/coordinate-conversion path, and its output metadata. `main()` should call only `match_osm`; unmatched communities must not receive an entry in `polygons`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_build_merged_polygons.py -v`

Expected: PASS.

### Task 2: Verify API behavior remains safe without a boundary

**Files:**
- Modify: `backend/housing-map/tests/test_api.py`
- Modify: `backend/housing-map/src/api/routes.py` only if test identifies a regression

- [ ] **Step 1: Write the failing test**

```python
def test_communities_without_polygon_keep_their_point_but_omit_boundary(client, monkeypatch):
    monkeypatch.setattr(routes, "load_polygons", lambda: {})

    record = client.get("/api/communities").json()["data"][0]

    assert record["latitude"]
    assert record["longitude"]
    assert "boundary" not in record
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_api.py::test_communities_without_polygon_keep_their_point_but_omit_boundary -v`

Expected: PASS or, if it fails, identify an API regression before changing production code.

- [ ] **Step 3: Run focused and full verification**

Run: `python -m pytest tests/test_build_merged_polygons.py tests/test_api.py -v --basetemp .tmp_pytest`

Run: `python -m pytest tests/ -v --basetemp .tmp_pytest`

Expected: all tests pass.

### Task 3: Expose OSM boundary rebuilding in the map UI

**Files:**
- Create: `backend/housing-map/src/services/boundary_refresh.py`
- Modify: `backend/housing-map/scripts/build_merged_polygons.py`
- Modify: `backend/housing-map/src/api/routes.py`
- Modify: `backend/housing-map/tests/test_api.py`
- Modify: `apps/housing-map/src/app/page.tsx`

- [ ] **Step 1: Write failing API tests**

```python
def test_boundary_rebuild_status_returns_the_dedicated_job(client):
    response = client.get("/api/boundaries/rebuild")

    assert response.status_code == 200
    assert response.json()["data"]["phase"] == "idle"
```

- [ ] **Step 2: Add an in-process boundary job**

The job calls the polygon builder through `asyncio.to_thread`, returns the OSM match count and unmatched count, and refuses a second concurrent rebuild. It writes only `binjiang_polygons_merged.json`; it never fetches prices or starts the transparent-housing crawler.

- [ ] **Step 3: Add the maintenance control**

Add a secondary `🗺️ 重建轮廓` button beside the price refresh button. While its dedicated job runs, disable that button and show `轮廓重建中`; on success, refetch communities so the map uses the new boundaries. Do not add a drawing tool, authentication flow, or an OSM network fetch.

- [ ] **Step 4: Verify**

Run: `python -m pytest tests/ -v --basetemp .tmp_pytest`

Run: `pnpm --dir apps/housing-map build`

Expected: backend tests and the production frontend build pass.
