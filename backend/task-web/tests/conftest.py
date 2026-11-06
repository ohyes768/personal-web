"""pytest 共享 fixture：临时 DB / 日志目录 / tasks.yaml，禁用真实调度线程。"""
import os
import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

os.environ.setdefault("TASK_WEB_ADMIN_PASSWORD", "test-pass")
os.environ.setdefault("TASK_WEB_TIMEZONE", "Asia/Shanghai")


@pytest.fixture()
def env(tmp_path, monkeypatch):
    """每个测试独立的 DB / 日志目录 / tasks.yaml。"""
    db_path = tmp_path / "data" / "taskweb.sqlite3"
    log_dir = tmp_path / "data" / "logs"
    tasks_yaml = tmp_path / "tasks.yaml"
    monkeypatch.setenv("TASK_WEB_DB_PATH", str(db_path))
    monkeypatch.setenv("TASK_WEB_LOG_DIR", str(log_dir))
    monkeypatch.setenv("TASK_WEB_TASKS_YAML", str(tasks_yaml))
    monkeypatch.setenv("TASK_WEB_ADMIN_PASSWORD", "test-pass")

    # 清掉线程本地连接缓存（旧测试的 DB 文件已删）
    from src import db

    if hasattr(db._local, "conn"):
        db._local.conn.close()
        del db._local.conn

    db.init_db()
    yield {"tmp": tmp_path, "tasks_yaml": tasks_yaml}


@pytest.fixture()
def client(env):
    """不启动 APScheduler 线程的 TestClient（lifespan 会被 TestClient 触发，
    因此手动构建 app 前先替换 scheduler 为 no-op）。"""
    from fastapi.testclient import TestClient

    from src import registry
    from src.api import routes
    from src.main import app, scheduler

    # 写入演示任务并登记
    registry_yaml = """tasks:
  - id: demo-success
    name: 演示-成功任务
    command: echo ok
    cwd: ""
    cron: "0 9 * * *"
    timeout: 30
  - id: demo-failure
    name: 演示-失败任务
    command: exit 3
    cwd: ""
    cron: "0 9 * * *"
    timeout: 30
"""
    Path(env["tasks_yaml"]).write_text(registry_yaml, encoding="utf-8")
    registry.sync_registry()

    routes.scheduler = scheduler
    with TestClient(app) as c:
        yield c
