# DR001 Update Response Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a successful DR001 update return `success: true` so the scheduler records it as successful.

**Architecture:** Keep the existing endpoint, fetcher, and persistence flow untouched. Add a focused FastAPI endpoint test that supplies a valid DR001 result, then extend the shared `UpdateResponse.data` union to accept its already-defined response payload type.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, pytest.

---

### Task 1: Cover and fix DR001 update response serialization

**Files:**
- Create: `backend/macro/tests/test_dr001_update_response.py`
- Modify: `backend/macro/src/models.py:308-330`
- Verify: `backend/macro/tests/test_dr001_update_response.py`

- [x] **Step 1: Write the failing endpoint test**

```python
import os

os.environ.setdefault("FRED_API_KEY", "test-not-a-real-key")

import pandas as pd
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api import routes
from src.api.routes import router


class _DataService:
    def get_last_date(self, _data_type):
        return None

    def save_dr001_data(self, df):
        self.saved = df.copy()


class _DR001Service:
    async def fetch_latest(self, _start, _end):
        return pd.DataFrame({
            "date": [pd.Timestamp("2026-09-18")],
            "dr001": [1.4277],
        })


def test_update_dr001_returns_success_after_persisting_valid_data(monkeypatch):
    app = FastAPI()
    app.include_router(router)
    data_service = _DataService()
    monkeypatch.setattr(routes, "get_data_service", lambda: data_service)
    monkeypatch.setattr(routes, "get_dr001_service", lambda: _DR001Service())

    response = TestClient(app).post("/api/update/dr001")

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["data"]["dr001"]["value"] == 1.4277
    assert data_service.saved["dr001"].tolist() == [1.4277]
```

- [x] **Step 2: Run the focused test and confirm the expected RED failure**

Run: `cd backend/macro; ./.venv/Scripts/python.exe -m pytest tests/test_dr001_update_response.py -v`

Expected: FAIL because `UpdateResponse.data` rejects `DR001UpdateData` after `save_dr001_data` has run.

- [x] **Step 3: Add the omitted response payload type**

In `backend/macro/src/models.py`, add this union member immediately after `DR007UpdateData`:

```python
        | DR001UpdateData
```

- [x] **Step 4: Run the focused test and confirm GREEN**

Run: `cd backend/macro; ./.venv/Scripts/python.exe -m pytest tests/test_dr001_update_response.py -v`

Expected: PASS; the response is HTTP 200 with `success: true`, and the fake data service received the DR001 row.

- [x] **Step 5: Run the affected regression suite**

Run: `cd backend/macro; ./.venv/Scripts/python.exe -m pytest tests/test_dr001.py tests/test_scheduler_jobs.py tests/test_daily_snapshot.py -v`

Expected: all selected tests PASS.

- [ ] **Step 6: Verify the production-facing result after deployment**

Run: `curl -X POST 'https://web.duomi77.cn:9443/api/macro/update/dr001'`

Expected: `success: true` with a `data.dr001` payload; `GET /api/macro/daily-snapshot` continues to return the persisted DR001 value.
