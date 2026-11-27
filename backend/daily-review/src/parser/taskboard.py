"""
task-board ledger-v2.json 与 git commit 解析（与 Windows 采集器共用口径）。

安全：ledger 可能被运行中的 Host 随时写 → 一次 open 整读；git 只读查询。
"""
from __future__ import annotations

import json
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path


def parse_ledger(path: Path, machine: str) -> dict | None:
    """整读 ledger-v2.json，产出一条 task_board 结构化记录；损坏返回 None。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None

    # 宽容提取任务卡片列表（不同版本键名可能是 tasks/cards/items）
    cards: list[dict] = []
    for key in ("tasks", "cards", "items"):
        v = data.get(key)
        if isinstance(v, list):
            cards = [c for c in v if isinstance(c, dict)]
            break

    status_counts: dict[str, int] = {}
    for c in cards:
        st = str(c.get("status") or c.get("column") or "unknown").lower()
        status_counts[st] = status_counts.get(st, 0) + 1

    board_rev = str(data.get("revision") or data.get("rev") or "")
    external_id = f"ledger-v2:{board_rev}" if board_rev else f"ledger-v2:{int(path.stat().st_mtime)}"
    titles = [str(c.get("title") or c.get("subject") or "")[:80] for c in cards[:10]]
    summary_text = "\n".join(
        [f"任务板共 {len(cards)} 张卡片，状态分布：{json.dumps(status_counts, ensure_ascii=False)}"]
        + [f"- {t}" for t in titles if t]
    )
    mtime_iso = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    return {
        "id": str(uuid.uuid4()),
        "kind": "task_board",
        "project": "task-board",
        "external_id": external_id,
        "session_id": "",
        "title": f"任务板快照 rev={board_rev or 'n/a'}",
        "summary_text": summary_text,
        "started_at": mtime_iso,
        "ended_at": mtime_iso,
        "payload": {"card_count": len(cards), "status_counts": status_counts, "revision": board_rev},
        "machine": machine,
    }


GIT_LOG_FORMAT = "%H%x1f%an%x1f%aI%x1f%s%x1e"


def parse_git_commits(repo_path: Path, machine: str, since: str = "", max_count: int = 200) -> list[dict]:
    """只读查询某仓库的 git commit，产出 git_commit 记录列表。"""
    cmd = ["git", "-C", str(repo_path), "log", f"--max-count={max_count}", "--pretty=format:" + GIT_LOG_FORMAT]
    if since:
        cmd.insert(4, f"--since={since}")
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=True).stdout
    except (OSError, subprocess.SubprocessError):
        return []

    records: list[dict] = []
    project = repo_path.name
    for chunk in out.split("\x1e"):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts = chunk.split("\x1f")
        if len(parts) < 4:
            continue
        sha, author, committed_at, subject = parts[0], parts[1], parts[2], parts[3]
        records.append(
            {
                "id": str(uuid.uuid4()),
                "kind": "git_commit",
                "project": project,
                "external_id": sha,
                "session_id": "",
                "title": subject[:120],
                "summary_text": f"{subject}（author: {author}）",
                "started_at": committed_at,
                "ended_at": committed_at,
                "payload": {"sha": sha, "author": author, "repo": str(repo_path)},
                "machine": machine,
            }
        )
    return records
