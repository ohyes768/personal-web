"""DR001 更新端点的响应契约回归测试。"""
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
    """有效 DR001 落库后，端点必须返回成功的可序列化响应。"""
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
