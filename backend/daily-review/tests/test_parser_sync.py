"""NAS sync（会话 zstd / ledger 解析与游标）+ today/projects 聚合测试。"""
import json

import pytest
import zstandard

from src.parser.session import parse_session_file
from src.parser.taskboard import parse_git_commits, parse_ledger


def _make_session_zstd(path, events):
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = "\n".join(json.dumps(e, ensure_ascii=False) for e in events)
    cctx = zstandard.ZstdCompressor()
    path.write_bytes(cctx.compress(lines.encode("utf-8")))


def _sample_events(session_id="sess-abc"):
    return [
        {"type": "session", "id": session_id, "timestamp": "2026-11-27T08:00:00Z", "cwd": "/home/ohyes768/personal-web"},
        {"type": "session title", "title": "修复股息率后端"},
        {"type": "user message", "message": {"content": "帮我看看 m120 接口为什么超时"}},
        {"type": "assistant message", "message": {"content": "好的，我来看一下"}},
        {"type": "tool call", "tool": "read_file", "timestamp": "2026-11-27T08:05:00Z"},
        {"type": "tool result", "tool": "read_file"},
        {"type": "turn", "timestamp": "2026-11-27T08:10:00Z"},
    ]


class TestSessionParser:
    def test_parse_structured_only(self, tmp_path):
        f = tmp_path / "sessions" / "--home-ohyes768-personal-web--" / "uuid-1" / "session.v4.jsonl.zstd"
        _make_session_zstd(f, _sample_events())
        rec = parse_session_file(f)
        assert rec is not None
        assert rec["kind"] == "session"
        assert rec["project"] == "personal-web"
        assert rec["external_id"] == "uuid-1"
        assert rec["title"] == "修复股息率后端"
        assert rec["started_at"].startswith("2026-11-27")
        assert "m120" in rec["summary_text"]
        # 不保留原文：summary 里只有要点与计数，payload 无原始事件
        assert "events" not in rec["payload"]
        assert rec["payload"]["tool_counts"].get("read_file") == 2

    def test_corrupt_file_returns_none(self, tmp_path):
        f = tmp_path / "sessions" / "--b--" / "u" / "session.v4.jsonl.zstd"
        f.parent.mkdir(parents=True)
        f.write_bytes(b"not-zstd")
        assert parse_session_file(f) is None


class TestLedgerParser:
    def test_parse_ledger(self, tmp_path):
        f = tmp_path / "ledger-v2.json"
        f.write_text(json.dumps({"revision": 42, "tasks": [
            {"id": "t1", "title": "任务A", "status": "done"},
            {"id": "t2", "title": "任务B", "status": "todo"},
        ]}), encoding="utf-8")
        rec = parse_ledger(f, machine="nas")
        assert rec["kind"] == "task_board"
        assert rec["external_id"] == "ledger-v2:42"
        assert rec["payload"]["card_count"] == 2
        assert "任务A" in rec["summary_text"]

    def test_git_commits(self, tmp_path):
        # 真实 git 只读查询：本仓库自身
        repo = tmp_path / "repo"
        repo.mkdir()
        import subprocess

        subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@t"], check=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.name", "t"], check=True)
        (repo / "a.txt").write_text("x")
        subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
        subprocess.run(["git", "-C", str(repo), "commit", "-qm", "feat: first"], check=True)
        recs = parse_git_commits(repo, machine="nas")
        assert len(recs) == 1
        assert recs[0]["kind"] == "git_commit"
        assert recs[0]["title"] == "feat: first"


class TestSyncNas:
    def test_sync_parses_and_cursor_skips(self, client, env):
        dsh = env["dsh"]
        _make_session_zstd(
            dsh / "sessions" / "--home-ohyes768-personal-web--" / "u-1" / "session.v4.jsonl.zstd",
            _sample_events(),
        )
        (dsh / "task-board").mkdir(parents=True, exist_ok=True)
        (dsh / "task-board" / "ledger-v2.json").write_text(
            json.dumps({"revision": 7, "tasks": [{"title": "X", "status": "done"}]}), encoding="utf-8"
        )

        r1 = client.post("/api/review/ingest/sync-nas")
        assert r1.status_code == 200
        data = r1.json()
        assert data["sessions_parsed"] == 1
        assert data["ledger_parsed"] is True
        assert data["records_inserted"] == 2
        assert data["errors"] == []

        # 二次 sync：文件级游标生效，全部跳过
        r2 = client.post("/api/review/ingest/sync-nas")
        data2 = r2.json()
        assert data2["sessions_parsed"] == 0
        assert data2["sessions_skipped"] == 1
        assert data2["ledger_parsed"] is False
        assert data2["records_inserted"] == 0

        # ledger 变更后（mtime 变化）重新解析
        import os, time

        os.utime(dsh / "task-board" / "ledger-v2.json", (time.time() + 10, time.time() + 10))
        r3 = client.post("/api/review/ingest/sync-nas")
        assert r3.json()["ledger_parsed"] is True

    def test_sync_disabled_without_dsh_dir(self, client, monkeypatch):
        import src.api.routes as routes

        monkeypatch.setattr(routes, "get_dsh_dir", lambda: None)
        r = client.post("/api/review/ingest/sync-nas")
        assert r.status_code == 503


class TestAggregations:
    def _ingest(self, client, headers, **kw):
        rec = {
            "machine": "windows",
            "kind": "session",
            "project": "proj-a",
            "external_id": kw.pop("external_id"),
            "title": "T",
            "summary_text": "S",
            "started_at": kw.pop("started_at"),
            "ended_at": "",
            "payload": {},
            **kw,
        }
        return client.post("/api/review/ingest/records", json={"records": [rec]}, headers=headers)

    def test_today_merges_two_machines_sorted(self, client, auth_headers):
        self._ingest(client, auth_headers, external_id="a1", started_at="2026-11-27T10:00:00Z", machine="windows")
        self._ingest(client, auth_headers, external_id="a2", started_at="2026-11-27T09:00:00Z", machine="nas")
        self._ingest(client, auth_headers, external_id="a3", started_at="2026-11-26T09:00:00Z", machine="nas")
        items = client.get("/api/review/today", params={"date": "2026-11-27"}).json()["items"]
        assert [i["external_id"] for i in items] == ["a2", "a1"]
        assert {i["machine"] for i in items} == {"windows", "nas"}

    def test_projects_aggregate(self, client, auth_headers):
        self._ingest(client, auth_headers, external_id="p1", started_at="2026-11-27T10:00:00Z", project="alpha")
        self._ingest(client, auth_headers, external_id="p2", started_at="2026-11-26T10:00:00Z", project="alpha",
                     kind="git_commit")
        self._ingest(client, auth_headers, external_id="p3", started_at="2026-11-25T10:00:00Z", project="beta")
        data = client.get("/api/review/projects").json()["projects"]
        alpha = next(p for p in data if p["project"] == "alpha")
        assert alpha["session_count"] == 1
        assert alpha["commit_count"] == 1
        assert alpha["last_activity"].startswith("2026-11-27")
        assert len(alpha["recent_summaries"]) == 2


def test_parse_session_real_v4_format(tmp_path):
    """真实 v4 事件口径：type 为 user/message 等，时间 epoch 毫秒字符串，文本在 data.message.content。"""
    import json as _json

    import zstandard as _zstd

    events = [
        {"type": "session/title", "time": 1764200000000, "data": {"title": "真实格式会话"}},
        {"type": "user/message", "time": 1764200001000,
         "data": {"content": [{"type": "text", "text": "帮我修一个 bug"}], "role": "user"}},
        {"type": "tool/call", "time": 1764200002000, "data": {"name": "bash"}},
        {"type": "assistant/message", "time": 1764200003000,
         "data": {"content": [{"type": "text", "text": "已修复"}]}},
        {"type": "subagent/descriptor", "time": "1764200004000", "data": {}},
    ]
    session_dir = tmp_path / "sessions" / "--home-ohyes768-personal-web--" / "session-abc123"
    session_dir.mkdir(parents=True)
    raw = "\n".join(_json.dumps(e, ensure_ascii=False) for e in events).encode()
    f = session_dir / "session.v4.jsonl.zstd"
    f.write_bytes(_zstd.ZstdCompressor().compress(raw))

    rec = parse_session_file(f)
    assert rec is not None
    assert rec["project"] == "personal-web"
    assert rec["title"] == "真实格式会话"
    assert rec["started_at"].startswith("2025-11-")  # epoch ms 正确换算，不是 1970
    assert "帮我修一个 bug" in rec["summary_text"]
    assert rec["payload"]["tool_counts"] == {"bash": 1}
