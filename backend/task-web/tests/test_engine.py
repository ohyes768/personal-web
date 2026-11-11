"""docker 引擎测试：fake client 验证容器参数、超时杀容器、退出码映射、env 解析。"""
from __future__ import annotations

import json
import time

import pytest

from src import executor


class FakeContainer:
    """最小容器模拟：logs 产出 demux 流，wait 返回退出码，kill 可触发退出。"""

    def __init__(self, exit_code=0, chunks=None, hang=False):
        self.exit_code = exit_code
        self.chunks = chunks or [(b"hello\n", None)]
        self.hang = hang
        self.killed = False
        self.removed = False

    def logs(self, stream=True, follow=True, demux=True):
        assert stream and follow and demux
        if self.hang:
            for _ in range(600):  # 模拟挂死：响应 kill，避免测试真等
                if self.killed:
                    return
                time.sleep(0.1)
            return
        yield from self.chunks

    def attach(self, logs=True, stream=True, demux=True):
        """SDK 真实接口：logs 流式分路走 attach（demux 在此，不在 logs）。"""
        assert stream and demux and logs
        if self.hang:
            for _ in range(600):
                if self.killed:
                    return
                time.sleep(0.1)
            return
        yield from self.chunks

    def wait(self, timeout=60):
        if self.hang:
            for _ in range(100):
                if self.killed:
                    return {"StatusCode": 137}
                time.sleep(0.1)
        return {"StatusCode": self.exit_code}

    def kill(self):
        self.killed = True

    def remove(self, force=True):
        self.removed = True


class FakeClient:
    def __init__(self, container):
        self.container = container
        self.last_kwargs = None
        self.containers = self  # SDK 风格：client.containers.run(...) 是属性链

    def run(self, image, command, **kwargs):
        self.last_kwargs = {"image": image, "command": command, **kwargs}
        return self.container


@pytest.fixture()
def fake_db_run(env):
    def _make(task_id="demo", engine="docker"):
        run_id = executor.db.new_run_id(task_id)
        executor.db.insert_run({
            "run_id": run_id, "task_id": task_id, "scheduled_at": None,
            "started_at": None, "finished_at": None, "duration_ms": None,
            "trigger": "manual", "status": "waiting", "exit_code": None,
            "log_path": None, "missed_schedule_at": None,
        })
        return run_id

    return _make


def test_parse_env_file(env, tmp_path):
    f = tmp_path / "biz.env"
    f.write_text("# 注释\nDING_TOKEN=abc123\nEMPTY=\nQUOTED=\"x y\"\nBADLINE\n", encoding="utf-8")
    result = executor.parse_env_file(str(f))
    assert result == {"DING_TOKEN": "abc123", "EMPTY": "", "QUOTED": "x y"}


def test_parse_env_file_missing(env):
    assert executor.parse_env_file(None) == {}
    assert executor.parse_env_file("/no/such/file") == {}


def test_task_env_merges_yaml_and_file(env, tmp_path):
    f = tmp_path / "biz.env"
    f.write_text("FROM_FILE=1\nSHARED=file\n", encoding="utf-8")
    task = {"env": json.dumps({"PUSH_MODE": "1", "SHARED": "yaml"}),
            "env_file": str(f)}
    merged = executor._task_env(task)
    assert merged["PUSH_MODE"] == "1"
    assert merged["FROM_FILE"] == "1"
    assert merged["SHARED"] == "yaml"  # yaml 显式 env 覆盖 env_file（2026-11-06 反转：显式声明优先）


def test_task_env_timeout_follows_task_timeout(env, tmp_path):
    """回归（2026-11-11）：HERMES_TIMEOUT 必须跟随任务 timeout，不能被 env_file 写死的旧值压过。

    此前 gw-8643.env 里 `HERMES_TIMEOUT=1800` 会覆盖一切，导致 yaml 登记 timeout=3600
    的任务实际 30 分钟就 exit 3（200 分钟级任务还会撞上）。这里固定"任务 timeout 胜出"。
    """
    f = tmp_path / "gw.env"
    f.write_text("HERMES_TIMEOUT=1800\n", encoding="utf-8")
    merged = executor._task_env({"env_file": str(f), "timeout_seconds": 3600})
    assert merged["HERMES_TIMEOUT"] == "3570"  # 3600 - 30s 余量，让脚本先于看门狗到点


def test_task_env_timeout_left_alone_without_task_timeout(env, tmp_path):
    """无任务 timeout 时不注入，env_file 的既有值保持原样（不误伤非 AI 任务）。"""
    f = tmp_path / "gw.env"
    f.write_text("HERMES_TIMEOUT=1800\n", encoding="utf-8")
    merged = executor._task_env({"env_file": str(f)})
    assert merged["HERMES_TIMEOUT"] == "1800"


def test_task_env_timeout_floor(env):
    """极短 timeout 不产生 <=0 的轮询预算（下限 60s）。"""
    merged = executor._task_env({"timeout_seconds": 30})
    assert merged["HERMES_TIMEOUT"] == "60"


def test_task_volumes_parse(env):
    task = {"volumes": json.dumps(["/h/a:/c/a", "/h/b:/c/b:ro"])}
    assert executor._task_volumes(task) == {
        "/h/a": {"bind": "/c/a", "mode": "rw"},
        "/h/b": {"bind": "/c/b", "mode": "ro"},
    }
    assert executor._task_volumes({}) == {}
    with pytest.raises(ValueError):
        executor._task_volumes({"volumes": json.dumps(["/onlyone"])})


def test_registry_parse_volumes(env):
    from src import registry

    assert registry._parse_volumes(None) is None
    assert registry._parse_volumes(["/h:/c:ro"]) == ["/h:/c:ro"]
    with pytest.raises(ValueError):
        registry._parse_volumes(["/h:/c:bad"])
    with pytest.raises(ValueError):
        registry._parse_volumes("not-a-list")


def test_docker_run_passes_volumes_network_user(env, fake_db_run, monkeypatch):
    fc = FakeClient(FakeContainer(exit_code=0))
    monkeypatch.setattr(executor, "_get_docker_client", lambda: fc)
    task = {"id": "demo", "command": "python x.py", "engine": "docker",
            "image": "stock-info:latest", "cwd": "/app", "env": None,
            "env_file": None, "timeout_seconds": 30,
            "volumes": json.dumps(["/host/data:/app/data", "/host/conf:/app/conf:ro"]),
            "network": "nginx_nginx-bridge", "run_user": "1000:1000"}
    run_id = fake_db_run()
    status = executor.execute_docker_run(run_id, task, 30)
    assert status == "success"
    assert fc.last_kwargs["volumes"] == {
        "/host/data": {"bind": "/app/data", "mode": "rw"},
        "/host/conf": {"bind": "/app/conf", "mode": "ro"},
    }
    assert fc.last_kwargs["network"] == "nginx_nginx-bridge"
    assert fc.last_kwargs["user"] == "1000:1000"


def test_docker_run_success(env, fake_db_run, monkeypatch):
    fc = FakeClient(FakeContainer(exit_code=0, chunks=[(b"ok\n", b"warn\n")]))
    monkeypatch.setattr(executor, "_get_docker_client", lambda: fc)
    task = {"id": "demo", "command": "python x.py", "engine": "docker",
            "image": "stock-info:latest", "cwd": "/app",
            "env": json.dumps({"A": "1"}), "env_file": None,
            "timeout_seconds": 30}
    run_id = fake_db_run()
    status = executor.execute_docker_run(run_id, task, 30)
    assert status == "success"
    run = executor.db.get_run(run_id)
    assert run["exit_code"] == 0
    assert fc.last_kwargs["image"] == "stock-info:latest"
    assert fc.last_kwargs["command"] == "python x.py"
    assert fc.last_kwargs["working_dir"] == "/app"
    assert fc.last_kwargs["environment"]["A"] == "1"
    assert fc.last_kwargs["detach"] is True
    # 日志分流
    out = executor.get_log_dir() / f"{run_id}.out"
    err = executor.get_log_dir() / f"{run_id}.err"
    assert out.read_bytes() == b"ok\n"
    assert err.read_bytes() == b"warn\n"
    assert fc.container.removed


def test_docker_run_failure_exit_code(env, fake_db_run, monkeypatch):
    fc = FakeClient(FakeContainer(exit_code=3))
    monkeypatch.setattr(executor, "_get_docker_client", lambda: fc)
    task = {"id": "demo", "command": "python x.py", "engine": "docker",
            "image": "stock-info:latest", "timeout_seconds": 30}
    run_id = fake_db_run()
    status = executor.execute_docker_run(run_id, task, 30)
    assert status == "failed"
    assert executor.db.get_run(run_id)["exit_code"] == 3


def test_docker_run_timeout_kills(env, fake_db_run, monkeypatch):
    """挂死的容器被看门狗杀掉，状态=timeout，容器被清理。"""
    fc = FakeClient(FakeContainer(exit_code=0, hang=True))
    monkeypatch.setattr(executor, "_get_docker_client", lambda: fc)
    task = {"id": "demo", "command": "sleep 600", "engine": "docker",
            "image": "stock-info:latest", "timeout_seconds": 2}
    run_id = fake_db_run()
    status = executor.execute_docker_run(run_id, task, 2)
    assert status == "timeout"
    assert fc.container.killed
    assert fc.container.removed


def test_docker_run_missing_image_raises(env, fake_db_run):
    task = {"id": "demo", "command": "x", "engine": "docker"}
    run_id = fake_db_run()
    with pytest.raises(ValueError, match="image"):
        executor.execute_docker_run(run_id, task, 30)


def test_start_run_dispatches_docker(env, fake_db_run, monkeypatch):
    """start_run 按 engine 分派：docker 任务进 docker 线程（用 fake client 兜住）。"""
    fc = FakeClient(FakeContainer(exit_code=0, chunks=[]))
    monkeypatch.setattr(executor, "_get_docker_client", lambda: fc)
    task = {"id": "demo", "name": "d", "command": "python x.py", "engine": "docker",
            "image": "stock-info:latest", "cwd": "", "default_timeout": 30,
            "timeout_seconds": 30}
    run_id = executor.start_run(task, trigger="manual")
    for _ in range(50):
        if executor.db.get_run(run_id)["status"] not in ("waiting", "running"):
            break
        time.sleep(0.1)
    run = executor.db.get_run(run_id)
    assert run["status"] == "success"
    assert run["exit_code"] == 0
