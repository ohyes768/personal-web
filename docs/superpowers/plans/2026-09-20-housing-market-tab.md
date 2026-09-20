# Housing Market Tab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a source-labelled, manually maintained market-reference tab to the Binjiang housing map and let users open a subdistrict-filtered map from the comparison table.

**Architecture:** A versioned JSON snapshot is the only owner of third-party market-reference data. A small backend service validates and returns it via a read-only endpoint; the frontend fetches that endpoint independently of communities and renders an isolated third tab. Map filtering remains client state and never alters the current transparent-sales price fields or score calculation.

**Tech Stack:** FastAPI + pytest; Next.js 16 + React 19 + TypeScript; existing CSS variables.

---

### Task 1: Validate and expose the manual market snapshot

**Files:**
- Create: `backend/housing-map/data/market_reference.json`
- Create: `backend/housing-map/src/services/market_reference.py`
- Modify: `backend/housing-map/src/api/routes.py`
- Test: `backend/housing-map/tests/test_market_reference.py`
- Test: `backend/housing-map/tests/test_api.py`

- [ ] **Step 1: Write the failing validation tests**

```python
def test_load_market_reference_returns_a_normalized_snapshot(tmp_path):
    path = tmp_path / "market_reference.json"
    path.write_text(json.dumps(VALID_SNAPSHOT), encoding="utf-8")
    result = load_market_reference(path)
    assert result["available"] is True
    assert result["price_kind"] == "listing_reference"
    assert result["subdistricts"][0]["name"] == "西兴"

def test_load_market_reference_returns_unavailable_for_invalid_payload(tmp_path):
    path = tmp_path / "market_reference.json"
    path.write_text('{"price_kind":"deal"}', encoding="utf-8")
    assert load_market_reference(path) == {"available": False, "reason": "invalid_snapshot"}
```

- [ ] **Step 2: Run the new tests and verify they fail because the module does not exist**

Run: `python -m pytest tests/test_market_reference.py -v`

Expected: collection failure for `src.services.market_reference`.

- [ ] **Step 3: Add the snapshot and minimal validator**

```python
def load_market_reference(path: Path | None = None) -> dict:
    """Return a display-safe, manually curated listing-reference snapshot."""
    # Read JSON once; accept only the declared listing-reference contract.
    # Missing/invalid source, date, average, or subdistrict rows returns an
    # unavailable status instead of fabricated market values.
```

Populate `market_reference.json` with the reviewed Anjuke snapshot, including `source.name`, `source.url`, `source.captured_at`, `price_kind`, district `overall`, and all reviewed source labels. Each source row must carry `map_subdistrict` and an explicit `map_scope_note`; source labels are not represented as exact map boundaries. Keep the source/date visible in data rather than code.

- [ ] **Step 4: Run the validator tests and verify they pass**

Run: `python -m pytest tests/test_market_reference.py -v`

Expected: PASS.

- [ ] **Step 5: Add an API contract test before the route exists**

```python
def test_market_reference_endpoint_returns_listing_reference_snapshot(client):
    response = client.get("/api/market-reference")
    body = response.json()
    assert response.status_code == 200
    assert body["success"] is True
    assert body["data"]["price_kind"] == "listing_reference"
    assert body["data"]["source"]["captured_at"]
```

- [ ] **Step 6: Run the API test and verify it fails with 404**

Run: `python -m pytest tests/test_api.py::test_market_reference_endpoint_returns_listing_reference_snapshot -v`

Expected: FAIL because `/api/market-reference` is not registered.

- [ ] **Step 7: Register the read-only route**

```python
@router.get("/market-reference")
async def market_reference():
    snapshot = load_market_reference()
    return {"success": snapshot.get("available", False), "data": snapshot}
```

- [ ] **Step 8: Run backend tests**

Run: `python -m pytest tests/test_market_reference.py tests/test_api.py -v`

Expected: PASS.

### Task 2: Add types and a market tab without altering price/score semantics

**Files:**
- Modify: `apps/housing-map/src/lib/types.ts`
- Modify: `apps/housing-map/src/app/page.tsx`
- Modify: `apps/housing-map/src/app/globals.css`

- [ ] **Step 1: Add a frontend API-shape test or compile-time fixture first**

Create a `MarketReference` TypeScript type describing `available`, `source`, `price_kind`, `overall`, and `subdistricts`; add a typed fixture constant consumed by a small pure `isListingReference()` guard. The guard must return false for an unavailable response or a non-`listing_reference` value.

- [ ] **Step 2: Run the frontend type check/build and verify the missing imports fail**

Run: `pnpm build`

Expected: FAIL because the market-reference symbols are not defined.

- [ ] **Step 3: Implement shared types and the independent fetch state**

Add `MarketReference` to `types.ts`; in `page.tsx`, load `/api/map/market-reference` independently from `/api/map/communities`. A failed response sets market data to unavailable and must not affect map loading state.

- [ ] **Step 4: Add the “市场行情” tab and accessible, source-labelled view**

Render an extracted `MarketOverviewPage` component with:

```tsx
<h1>滨江市场行情 <span>挂牌参考</span></h1>
<p>数据来源：<a href={source.url}>安居客</a> · 快照日期：{source.captured_at}</p>
<p>挂牌参考价反映卖方报价，不是网签成交价。</p>
```

Render cards for the district average, month-on-month change, and year-on-year change. Render a source-label table with a text-plus-arrow change indicator, visible approximate-map note, and an `在地图查看` button. Missing data must render `—` and disabled interaction, never `0`.

- [ ] **Step 5: Add visual styles using existing design tokens**

Add only namespaced classes such as `.market-overview`, `.market-card`, `.market-change`, and `.market-table`; preserve responsive single-column behavior on narrow screens and avoid changing existing map/dashboard classes.

- [ ] **Step 6: Run the frontend build and lint**

Run: `pnpm build && pnpm lint`

Expected: PASS.

### Task 3: Link a market subdistrict to the map

**Files:**
- Modify: `apps/housing-map/src/app/page.tsx`

- [ ] **Step 1: Define the desired state transition before implementation**

The market action handler must set `activeTab` to `map`, set one `marketSubdistrict` state value from the reviewed approximate mapping, and leave `searchQuery`, `propertyTypes`, and `priceMode` unchanged. The displayed community collection applies `marketSubdistrict` only when non-empty.

- [ ] **Step 2: Implement the smallest client-state linkage**

Pass `onViewSubdistrict` into `MarketOverviewPage`. On click, set the selected subdistrict and map tab; add a map banner reading `正在查看：{name}` with a button to clear only `marketSubdistrict`. Use the same `filteredCommunities` input for `BinjiangMap`, so map colors/tooltips only cover that selection.

- [ ] **Step 3: Build and manually smoke-test the state boundaries**

Run: `pnpm build`

Manual checks: open market tab; click 西兴; verify map only displays 西兴; clear the banner; verify all communities return; switch to dashboard and confirm its filters are unchanged.

### Task 4: Full verification

**Files:**
- Verify: `backend/housing-map/tests/`
- Verify: `apps/housing-map/`

- [ ] **Step 1: Run all backend tests**

Run: `python -m pytest tests/ -v`

Expected: PASS.

- [ ] **Step 2: Run frontend checks**

Run: `pnpm lint && pnpm build`

Expected: PASS.

- [ ] **Step 3: Inspect the final diff and data semantics**

Run: `git diff --check` and inspect every new visible label for “挂牌参考”, source, and snapshot date. Confirm no external credentials, crawler, or changed scoring calculation appear in the diff.
