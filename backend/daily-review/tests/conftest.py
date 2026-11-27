"""pytest 共享 fixture：临时 DB / NAS 挂载目录，禁用真实 NAS。"""
import os
import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

os.environ.setdefault("DAILY_REVIEW_INGEST_TOKEN", "test-token")


@pytest.fixture()
def env(tmp_path, monkeypatch):
    """每个测试独立的 DB 与 DSH 挂载目录。"""
    monkeypatch.setenv("DAILY_REVIEW_DB", str(tmp_path / "data" / "daily-review.sqlite3"))
    monkeypatch.setenv("DAILY_REVIEW_DSH_DIR", str(tmp_path / "dsh"))
    monkeypatch.setenv("DAILY_REVIEW_INGEST_TOKEN", "test-token")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    from src import db

    if hasattr(db._local, "conn"):
        db._local.conn.close()
        del db._local.conn

    db.init_db()
    yield {"tmp": tmp_path, "dsh": tmp_path / "dsh"}


@pytest.fixture()
def client(env):
    from fastapi.testclient import TestClient

    from src.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture()
def auth_headers():
    return {"X-Ingest-Token": "test-token"}
