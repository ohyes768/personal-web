# Housing Map Price Quality Implementation Plan

> **Status:** Superseded during source verification on 2026-09-20. The page-wide
> `<text>元/㎡</text>` values are recommendation cards, not a community price
> sample. They are now retired entirely; only explicit `listing_avg` and recent
> `monthly_deal_avg_latest` values are eligible for display.

> **For agentic workers:** Execute the test-first steps below in order. Do not commit unless the user explicitly requests it.

**Goal:** Stop the housing map from displaying obviously stale or misparsed TMSF prices while preserving valid current deal and listing prices.

**Architecture:** Keep quality validation inside `load_price_snapshots`, the single JSONL-to-API projection. It will first validate all source rows collectively (needed to detect a repeated listing-card vector), then select the best valid price per community. The API contract and frontend fields remain unchanged: rejected rows simply yield no price.

**Tech Stack:** Python 3.11+, pytest, FastAPI data loader, JSONL snapshots.

---

## File map

- Modify: `backend/housing-map/src/services/data_loader.py` — central validation and deterministic selection.
- Modify: `backend/housing-map/tests/test_data_loader.py` — regression tests for unsafe price rows.
- Create: `docs/superpowers/plans/2026-09-20-housing-map-price-quality.md` — this plan.

### Task 1: Make bad source rows fail tests first

**Files:**

- Modify: `backend/housing-map/tests/test_data_loader.py`
- Test: `backend/housing-map/tests/test_data_loader.py`

- [ ] **Step 1: Add a test for a zero-listing fallback price**

```python
def test_price_loader_rejects_visible_listing_when_listing_count_is_zero(tmp_path):
    path = _write_jsonl(tmp_path, [{
        "community_id": "A", "avg_price": 30000,
        "price_type": "visible_listing_unit_price_avg", "listing_count": 0,
        "raw_payload": {"visible_listing_unit_prices": [30000]},
    }])

    assert load_price_snapshots(path) == {}
```

- [ ] **Step 2: Run the one test and verify it fails because the current loader returns A**

Run: `python -m pytest tests/test_data_loader.py::test_price_loader_rejects_visible_listing_when_listing_count_is_zero -v`

Expected: `FAIL`, with `A` present in the actual result.

- [ ] **Step 3: Add a test for a listing-card vector shared by two communities**

```python
def test_price_loader_rejects_reused_visible_listing_vector(tmp_path):
    shared = [44688, 60948, 22651, 26929]
    path = _write_jsonl(tmp_path, [
        {"community_id": "A", "avg_price": 38804, "price_type": "visible_listing_unit_price_avg", "listing_count": 4,
         "raw_payload": {"visible_listing_unit_prices": shared}},
        {"community_id": "B", "avg_price": 38804, "price_type": "visible_listing_unit_price_avg", "listing_count": 4,
         "raw_payload": {"visible_listing_unit_prices": shared}},
    ])

    assert load_price_snapshots(path) == {}
```

- [ ] **Step 4: Run the one test and verify it fails because both rows are currently accepted**

Run: `python -m pytest tests/test_data_loader.py::test_price_loader_rejects_reused_visible_listing_vector -v`

Expected: `FAIL`, with `A` and `B` present in the actual result.

- [ ] **Step 5: Add a test for an outdated monthly deal value**

```python
def test_price_loader_rejects_monthly_deal_older_than_six_months(tmp_path):
    path = _write_jsonl(tmp_path, [{
        "community_id": "A", "avg_price": 20000,
        "price_type": "monthly_deal_avg_latest",
        "raw_payload": {"tendency": {"latest_month": "2025-01"}},
    }])

    assert load_price_snapshots(path, today=date(2026, 9, 20)) == {}
```

- [ ] **Step 6: Run the one test and verify it fails because the current loader accepts the historical value**

Run: `python -m pytest tests/test_data_loader.py::test_price_loader_rejects_monthly_deal_older_than_six_months -v`

Expected: `FAIL`, with `A` present in the actual result.

### Task 2: Implement one centralized quality gate

**Files:**

- Modify: `backend/housing-map/src/services/data_loader.py`
- Test: `backend/housing-map/tests/test_data_loader.py`

- [ ] **Step 1: Add `date` and `Counter` imports, a six-month freshness constant, and a private helper that reads `raw_payload.tendency.latest_month`**

The helper must parse `YYYY-MM`, return false for malformed or missing months, and compare month starts against `today - relativedelta`-free calendar arithmetic (six months back). The loader accepts an optional keyword-only `today: date | None = None`, defaulting to `date.today()`. Add `from datetime import date` to the test module before using the deterministic date fixture.

- [ ] **Step 2: Pre-compute counts of non-empty `visible_listing_unit_price_avg` vectors across all parsed JSONL rows**

Use `tuple(raw_payload.get("visible_listing_unit_prices", []))` as the vector key. A visible-listing row is valid only when `listing_count > 0`, its vector is non-empty, and its vector occurs exactly once in the file.

- [ ] **Step 3: Filter rows before selection**

Accept a monthly deal only when it has a positive price and a recent valid trend month. Accept a visible listing only when it passes the collective-vector rule. Preserve the existing monthly-deal-over-listing precedence for valid rows; reject unsupported `price_type` values instead of allowing file order to label them as listing prices.

- [ ] **Step 4: Run the three new tests and verify they pass**

Run: `python -m pytest tests/test_data_loader.py::test_price_loader_rejects_visible_listing_when_listing_count_is_zero tests/test_data_loader.py::test_price_loader_rejects_reused_visible_listing_vector tests/test_data_loader.py::test_price_loader_rejects_monthly_deal_older_than_six_months -v`

Expected: `3 passed`.

- [ ] **Step 5: Add a positive regression for a fresh deal price and a unique, nonzero listing price**

The fixture must set `latest_month` to `2026-09` and pass `today=date(2026, 9, 20)`. Assert both communities remain available, and assert the fresh deal wins when both types exist for one community.

- [ ] **Step 6: Run the loader test module**

Run: `python -m pytest tests/test_data_loader.py -v`

Expected: all tests pass.

### Task 3: Validate the API result and snapshot impact

**Files:**

- Test: `backend/housing-map/tests/test_api.py`
- Verify: `backend/housing-map/data/price_snapshots.jsonl`

- [ ] **Step 1: Add an API regression test where an injected invalid price fixture is absent from the assembled `price` projection**

Use the existing FastAPI test-client fixture pattern. Assert the community remains in the response, but its `listing_avg_price` and `deal_avg_price` are both `None`.

- [ ] **Step 2: Run the new API regression and verify it fails before its supporting implementation is present, then passes after it is present**

Run: `python -m pytest tests/test_api.py -v`

Expected: all API tests pass after the implementation.

- [ ] **Step 3: Run the complete backend suite**

Run: `python -m pytest tests/ -v`

Expected: all tests pass.

- [ ] **Step 4: Calculate the post-filter coverage without rewriting the JSONL file**

Run a read-only Python summary using `load_price_snapshots()` and report: valid deal count, valid listing count, and communities without a reliable price. The committed source snapshot remains unchanged; the filter takes effect at API-read time.

## Plan self-review

- Scope is limited to data quality gating; it does not introduce a third-party crawler or alter map layout.
- The quality policy has one owner (`load_price_snapshots`) and the API/frontend retain their current contract.
- Every new behavior has a failing regression before production code, including valid-path coverage.
