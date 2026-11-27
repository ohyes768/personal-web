"""
DSH session.v4.jsonl.zstd 解析器（与 Windows 采集器共用口径）。

- zstandard stream_reader 流式读（zstd 帧无内容大小头），逐行 json。
- 事件类型：session / user message / assistant message / tool call|result /
  turn|step / subagent descriptor / session title。
- 只输出结构化摘要记录（项目、标题、时间段、要点文本），不保留任何原文。
- 只读：本模块绝不写挂载目录。
"""
from __future__ import annotations

import io
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import zstandard

# 摘要要点上限：每会话最多保留的用户消息要点数与单条截断长度
MAX_POINTS = 8
POINT_MAX_CHARS = 120

# 用户消息里常被注入系统内容（system-reminder、workspace 指令、工具回显），
# 不是用户的真实诉求，进入要点前整体丢弃该条。
_NOISE_MARKS = (
    "<system-reminder>", "<available_skills>", "<hindsight_", "[open-model state",
    "current runtime context", "snapshot supersedes", "workspace instructions",
    "agent teams is available", "browser time zone", "time sampled",
    "progress_update", "state anchor", "dsh file policy", "rule: follow goal",
    "files:", "instructions from:", "trellis", "current working directory",
    "approval prompts", "team lead and all", "elapsed since the preceding",
    "see the browser console", "<tool", "<available-skills>",
)




def _is_noise_line(line: str) -> bool:
    low = line.lower()
    return any(m in low for m in _NOISE_MARKS)


def _sanitize(body: str) -> str:
    """只保留真实诉求：注入的系统块跟在用户文本后面，遇到第一条噪音行即截断；
    截断前的行再过一遍噪音标记兜底。"""
    kept: list[str] = []
    for ln in body.splitlines():
        t = ln.strip()
        if not t:
            continue
        if _is_noise_line(t):
            break
        kept.append(t)
    return " ".join(kept).strip()


def _bucket_to_project(bucket: str) -> str:
    """会话桶名 `--home-ohyes768-personal-web--` → 项目名 personal-web。

    项目名本身可能含连字符，因此不能简单按 `-` 切；约定桶以绝对路径编码，
    去掉首尾 `--` 后若以 `home-<user>-` 开头则去掉前两段，剩余整体即项目名。
    """
    name = bucket.strip("-")
    parts = name.split("-")
    if len(parts) > 2 and parts[0] == "home":
        return "-".join(parts[2:])
    return name


def _event_type(obj: dict) -> str:
    return str(obj.get("type") or obj.get("event") or "").lower()


def _extract_text(obj: dict) -> str:
    """宽容提取事件里的文本（不同 Host 版本字段略有差异）。

    真实 v4 事件文本在 `data.content`（内容块列表）；旧口径兼容
    `message.content` 与 `data.message.content`。
    """
    for holder in (obj.get("data"), obj):
        if not isinstance(holder, dict):
            continue
        content = holder.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return " ".join(
                b.get("text", "") for b in content if isinstance(b, dict) and b.get("text")
            )
        msg = holder.get("message")
        if isinstance(msg, dict):
            content = msg.get("content")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                return " ".join(
                    b.get("text", "") for b in content if isinstance(b, dict) and b.get("text")
                )
    for holder in (obj, obj.get("data")):
        if not isinstance(holder, dict):
            continue
        for key in ("title", "text", "content", "name"):
            v = holder.get(key)
            if isinstance(v, str) and v.strip():
                return v
    return ""


def _extract_ts(obj: dict) -> str:
    for key in ("timestamp", "ts", "time", "createdAt", "created_at"):
        v = obj.get(key)
        if isinstance(v, (int, float)) or (isinstance(v, str) and v.strip().isdigit()):
            # 真实格式为 epoch 毫秒（13 位数字/字符串），秒级数值也兼容
            n = float(v)
            if n > 1e12:
                n /= 1000.0
            return datetime.fromtimestamp(n, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        if isinstance(v, str) and v:
            return v
    return ""


def parse_session_file(path: Path) -> dict | None:
    """解析单个 session.v4.jsonl.zstd，返回结构化记录 dict；损坏/空文件返回 None。"""
    bucket = path.parent.parent.name  # sessions/<bucket>/<uuid>/session.v4.jsonl.zstd
    session_id = path.parent.name

    title = ""
    started_at = ""
    ended_at = ""
    user_points: list[str] = []
    tool_counts: dict[str, int] = {}
    assistant_chars = 0
    tool_event_count = 0
    subagent_count = 0

    try:
        with open(path, "rb") as raw:
            with zstandard.ZstdDecompressor().stream_reader(raw) as reader:
                text = io.TextIOWrapper(reader, encoding="utf-8", errors="replace")
                for line in text:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except ValueError:
                        continue
                    if not isinstance(obj, dict):
                        continue
                    et = _event_type(obj)
                    ts = _extract_ts(obj)
                    if ts:
                        if not started_at:
                            started_at = ts
                        ended_at = ts

                    if "title" in et:
                        t = _extract_text(obj) or str(obj.get("title") or "")
                        if t:
                            title = t
                    elif "user" in et and "message" in et:
                        body = _extract_text(obj).strip()
                        body = _sanitize(body)
                        if body and len(user_points) < MAX_POINTS:
                            user_points.append(body[:POINT_MAX_CHARS])
                    elif "assistant" in et and "message" in et:
                        assistant_chars += len(_extract_text(obj))
                    elif "tool" in et:
                        tool_event_count += 1
                        data = obj.get("data") if isinstance(obj.get("data"), dict) else {}
                        tool_name = str(
                            data.get("name")
                            or obj.get("tool")
                            or obj.get("tool_name")
                            or obj.get("name")
                            or "unknown"
                        )
                        tool_counts[tool_name] = tool_counts.get(tool_name, 0) + 1
                    elif "subagent" in et:
                        subagent_count += 1
    except (OSError, zstandard.ZstdError):
        return None

    if not started_at:
        # 无任何带时间戳事件时退回文件 mtime
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        started_at = ended_at = mtime.strftime("%Y-%m-%dT%H:%M:%SZ")

    points = [f"- {p}" for p in user_points] or ["-（会话内无用户消息要点）"]
    summary_text = "\n".join(
        [
            f"做了什么要点（来自用户消息，共 {len(user_points)} 条）：",
            *points,
            f"assistant 输出约 {assistant_chars} 字；tool 事件 {tool_event_count} 次；subagent 事件 {subagent_count} 次。",
        ]
    )
    payload = {
        "bucket": bucket,
        "tool_counts": tool_counts,
        "assistant_chars": assistant_chars,
        "tool_event_count": tool_event_count,
        "subagent_event_count": subagent_count,
        "user_point_count": len(user_points),
    }
    return {
        "id": str(uuid.uuid4()),
        "kind": "session",
        "project": _bucket_to_project(bucket),
        "external_id": session_id,
        "session_id": session_id,
        "title": title or f"会话 {session_id[:8]}",
        "summary_text": summary_text,
        "started_at": started_at,
        "ended_at": ended_at,
        "payload": payload,
    }
def _bucket_to_project(bucket: str) -> str:
    """会话桶名 `--home-ohyes768-personal-web--` → 项目名 personal-web。

    项目名本身可能含连字符，因此不能简单按 `-` 切；约定桶以绝对路径编码，
    去掉首尾 `--` 后若以 `home-<user>-` 开头则去掉前两段，剩余整体即项目名。
    """
    name = bucket.strip("-")
    parts = name.split("-")
    if len(parts) > 2 and parts[0] == "home":
        return "-".join(parts[2:])
    return name


def _event_type(obj: dict) -> str:
    return str(obj.get("type") or obj.get("event") or "").lower()


def _extract_text(obj: dict) -> str:
    """宽容提取事件里的文本（不同 Host 版本字段略有差异）。

    真实 v4 事件文本在 `data.content`（内容块列表）；旧口径兼容
    `message.content` 与 `data.message.content`。
    """
    for holder in (obj.get("data"), obj):
        if not isinstance(holder, dict):
            continue
        content = holder.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return " ".join(
                b.get("text", "") for b in content if isinstance(b, dict) and b.get("text")
            )
        msg = holder.get("message")
        if isinstance(msg, dict):
            content = msg.get("content")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                return " ".join(
                    b.get("text", "") for b in content if isinstance(b, dict) and b.get("text")
                )
    for holder in (obj, obj.get("data")):
        if not isinstance(holder, dict):
            continue
        for key in ("title", "text", "content", "name"):
            v = holder.get(key)
            if isinstance(v, str) and v.strip():
                return v
    return ""


def _extract_ts(obj: dict) -> str:
    for key in ("timestamp", "ts", "time", "createdAt", "created_at"):
        v = obj.get(key)
        if isinstance(v, (int, float)) or (isinstance(v, str) and v.strip().isdigit()):
            # 真实格式为 epoch 毫秒（13 位数字/字符串），秒级数值也兼容
            n = float(v)
            if n > 1e12:
                n /= 1000.0
            return datetime.fromtimestamp(n, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        if isinstance(v, str) and v:
            return v
    return ""


def parse_session_file(path: Path) -> dict | None:
    """解析单个 session.v4.jsonl.zstd，返回结构化记录 dict；损坏/空文件返回 None。"""
    bucket = path.parent.parent.name  # sessions/<bucket>/<uuid>/session.v4.jsonl.zstd
    session_id = path.parent.name

    title = ""
    started_at = ""
    ended_at = ""
    user_points: list[str] = []
    tool_counts: dict[str, int] = {}
    assistant_chars = 0
    tool_event_count = 0
    subagent_count = 0

    try:
        with open(path, "rb") as raw:
            with zstandard.ZstdDecompressor().stream_reader(raw) as reader:
                text = io.TextIOWrapper(reader, encoding="utf-8", errors="replace")
                for line in text:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except ValueError:
                        continue
                    if not isinstance(obj, dict):
                        continue
                    et = _event_type(obj)
                    ts = _extract_ts(obj)
                    if ts:
                        if not started_at:
                            started_at = ts
                        ended_at = ts

                    if "title" in et:
                        t = _extract_text(obj) or str(obj.get("title") or "")
                        if t:
                            title = t
                    elif "user" in et and "message" in et:
                        body = _extract_text(obj).strip()
                        body = _sanitize(body)
                        if body and len(user_points) < MAX_POINTS:
                            user_points.append(body[:POINT_MAX_CHARS])
                    elif "assistant" in et and "message" in et:
                        assistant_chars += len(_extract_text(obj))
                    elif "tool" in et:
                        tool_event_count += 1
                        data = obj.get("data") if isinstance(obj.get("data"), dict) else {}
                        tool_name = str(
                            data.get("name")
                            or obj.get("tool")
                            or obj.get("tool_name")
                            or obj.get("name")
                            or "unknown"
                        )
                        tool_counts[tool_name] = tool_counts.get(tool_name, 0) + 1
                    elif "subagent" in et:
                        subagent_count += 1
    except (OSError, zstandard.ZstdError):
        return None

    if not started_at:
        # 无任何带时间戳事件时退回文件 mtime
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        started_at = ended_at = mtime.strftime("%Y-%m-%dT%H:%M:%SZ")

    points = [f"- {p}" for p in user_points] or ["-（会话内无用户消息要点）"]
    summary_text = "\n".join(
        [
            f"做了什么要点（来自用户消息，共 {len(user_points)} 条）：",
            *points,
            f"assistant 输出约 {assistant_chars} 字；tool 事件 {tool_event_count} 次；subagent 事件 {subagent_count} 次。",
        ]
    )
    payload = {
        "bucket": bucket,
        "tool_counts": tool_counts,
        "assistant_chars": assistant_chars,
        "tool_event_count": tool_event_count,
        "subagent_event_count": subagent_count,
        "user_point_count": len(user_points),
    }
    return {
        "id": str(uuid.uuid4()),
        "kind": "session",
        "project": _bucket_to_project(bucket),
        "external_id": session_id,
        "session_id": session_id,
        "title": title or f"会话 {session_id[:8]}",
        "summary_text": summary_text,
        "started_at": started_at,
        "ended_at": ended_at,
        "payload": payload,
    }
