"""hermes_client 单元测试（mock requests，不真连）。"""
import pytest

from src.services import hermes_client
from src.services.hermes_client import (
    HermesApiError,
    HermesConfig,
    HermesRunFailed,
    HermesTimeout,
    poll_run,
    submit_run,
)

CFG = HermesConfig(
    base_url="http://nas:8642", api_key="secret", profile="ohyes768",
    poll_interval=0, timeout=5, max_concurrent=4,
)


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text or str(self._payload)

    def json(self):
        return self._payload


class TestConfig:
    def test_from_env_defaults(self, monkeypatch):
        monkeypatch.delenv("HERMES_BASE_URL", raising=False)
        monkeypatch.delenv("HERMES_API_KEY", raising=False)
        monkeypatch.setenv("HERMES_PROFILE", "ohyes768")
        cfg = HermesConfig.from_env()
        assert cfg.is_configured is False
        assert cfg.profile == "ohyes768"
        assert cfg.poll_interval == 30
        assert cfg.timeout == 1800
        assert cfg.max_concurrent == 4

    def test_from_env_configured(self, monkeypatch):
        monkeypatch.setenv("HERMES_BASE_URL", "http://nas:8642/")
        monkeypatch.setenv("HERMES_API_KEY", "k")
        cfg = HermesConfig.from_env()
        assert cfg.is_configured is True
        assert cfg.base_url == "http://nas:8642"  # 末尾斜杠被剥掉


class TestSubmit:
    def test_submit_ok(self, monkeypatch):
        captured = {}

        def fake_post(url, json=None, headers=None, timeout=None):
            captured.update(url=url, json=json, headers=headers)
            return FakeResponse(payload={"run_id": "run-1"})

        monkeypatch.setattr(hermes_client.requests, "post", fake_post)
        run_id = submit_run(CFG, "prompt-内容", "quality-600900-20261023")
        assert run_id == "run-1"
        assert captured["url"] == "http://nas:8642/p/ohyes768/v1/runs"
        assert captured["json"] == {"input": "prompt-内容"}
        assert captured["headers"]["Authorization"] == "Bearer secret"
        assert captured["headers"]["Idempotency-Key"] == "quality-600900-20261023"

    def test_submit_non_2xx_raises(self, monkeypatch):
        monkeypatch.setattr(hermes_client.requests, "post",
                            lambda *a, **k: FakeResponse(status_code=500, text="boom"))
        with pytest.raises(HermesApiError):
            submit_run(CFG, "p", "k")

    def test_submit_missing_run_id_raises(self, monkeypatch):
        monkeypatch.setattr(hermes_client.requests, "post",
                            lambda *a, **k: FakeResponse(payload={}))
        with pytest.raises(HermesApiError):
            submit_run(CFG, "p", "k")

    def test_submit_network_error_raises_api_error(self, monkeypatch):
        def boom(*a, **k):
            raise hermes_client.requests.exceptions.ConnectionError("nas 不可达")
        monkeypatch.setattr(hermes_client.requests, "post", boom)
        with pytest.raises(HermesApiError, match="提交请求异常"):
            submit_run(CFG, "p", "k")


class TestPoll:
    def test_poll_completed_returns_output(self, monkeypatch):
        monkeypatch.setattr(hermes_client.requests, "get",
                            lambda *a, **k: FakeResponse(payload={"status": "completed", "output": '{"stars": 4}'}))
        assert poll_run(CFG, "run-1") == '{"stars": 4}'

    def test_poll_completed_empty_output_raises(self, monkeypatch):
        monkeypatch.setattr(hermes_client.requests, "get",
                            lambda *a, **k: FakeResponse(payload={"status": "completed", "output": ""}))
        with pytest.raises(HermesRunFailed):
            poll_run(CFG, "run-1")

    @pytest.mark.parametrize("status", ["failed", "cancelled", "interrupted"])
    def test_poll_failed_terminal_raises(self, monkeypatch, status):
        monkeypatch.setattr(hermes_client.requests, "get",
                            lambda *a, **k: FakeResponse(payload={"status": status}))
        with pytest.raises(HermesRunFailed):
            poll_run(CFG, "run-1")

    def test_poll_timeout_raises(self, monkeypatch):
        # timeout=0：首轮未到终态即超时
        monkeypatch.setattr(hermes_client.requests, "get",
                            lambda *a, **k: FakeResponse(payload={"status": "running"}))
        with pytest.raises(HermesTimeout):
            poll_run(CFG, "run-1")

    def test_poll_network_error_raises_api_error(self, monkeypatch):
        def boom(*a, **k):
            raise hermes_client.requests.exceptions.Timeout("查询超时")
        monkeypatch.setattr(hermes_client.requests, "get", boom)
        with pytest.raises(HermesApiError, match="查询请求异常"):
            poll_run(CFG, "run-1")
