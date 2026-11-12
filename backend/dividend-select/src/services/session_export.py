"""Hermes run 会话记录导出：session 元数据 + 逐条消息 → 可读 markdown。

数据源是 Hermes 网关自带接口（session_id 与 run_id 同值，无需改 skill / Hermes）：
- GET /api/sessions/{id}          → 元数据（消息数/工具调用数/token 统计/起止）
- GET /api/sessions/{id}/messages → 完整逐条消息（role/content/tool_name/timestamp）

供 quality / valuation 两条链路的下载端点共用。
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from src.services.hermes_client import HermesConfig, HermesApiError, get_session, get_session_messages
from src.utils.logger import setup_logger

logger = setup_logger(__name__)

_TZ = ZoneInfo("Asia/Shanghai")
# 单条消息正文超过这个长度截断（会话记录用于排查节奏，不是全文归档）
_MAX_CONTENT_CHARS = 4000


def _fmt_ts(timestamp: float | None) -> str:
    if not timestamp:
        return "?"
    return datetime.fromtimestamp(timestamp, _TZ).strftime("%m-%d %H:%M:%S")


def _fmt_delta(current: float | None, previous: float | None) -> str:
    if not current or not previous:
        return ""
    delta = current - previous
    if delta < 0:
        return ""
    return f" (+{delta:.1f}s)" if delta >= 0.1 else ""


def _content_text(content) -> str:
    """messages.content 可能是 str / list[content part] / None，统一抽成文本。"""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("content") or ""))
            else:
                parts.append(str(item))
        return "\n".join(p for p in parts if p)
    return str(content)


def _truncate(text: str) -> str:
    if len(text) <= _MAX_CONTENT_CHARS:
        return text
    return f"{text[:_MAX_CONTENT_CHARS]}\n…（截断，全文 {len(text)} 字符）"


def build_session_markdown(cfg: HermesConfig, run_id: str,
                           get_session_fn=get_session, get_session_messages_fn=get_session_messages) -> str:
    """拉取 run 会话并组装 markdown；Hermes 侧 404 / 网络错误原样抛 HermesApiError。"""
    session = get_session_fn(cfg, run_id)
    meta = session.get("session") if isinstance(session.get("session"), dict) else session
    messages = get_session_messages_fn(cfg, run_id)

    lines: list[str] = [f"# Hermes run 会话记录：{run_id}", ""]
    lines.append("## 会话摘要")
    lines.append("")
    for label, key in (
        ("模型", "model"), ("消息数", "message_count"), ("工具调用数", "tool_call_count"),
        ("API 调用数", "api_call_count"), ("输入 tokens", "input_tokens"),
        ("输出 tokens", "output_tokens"), ("缓存读 tokens", "cache_read_tokens"),
        ("缓存写 tokens", "cache_write_tokens"),
    ):
        value = meta.get(key)
        if value is not None:
            lines.append(f"- {label}：{value}")
    started = meta.get("started_at")
    ended = meta.get("ended_at")
    if started:
        span = f" ~ {_fmt_ts(ended)}" if ended else "（进行中）"
        lines.append(f"- 时间：{_fmt_ts(started)}{span}")
    lines.append("")
    lines.append(f"## 消息记录（{len(messages)} 条）")
    lines.append("")

    previous_ts: float | None = None
    for index, message in enumerate(messages, start=1):
        if not isinstance(message, dict):
            continue
        role = str(message.get("role") or "?")
        tool_name = message.get("tool_name")
        timestamp = message.get("timestamp")
        header = f"### #{index} {_fmt_ts(timestamp)}{_fmt_delta(timestamp, previous_ts)} · {role}"
        if tool_name:
            header += f" · tool: {tool_name}"
        lines.append(header)
        lines.append("")
        text = _content_text(message.get("content"))
        if text:
            if role == "assistant" and not tool_name:
                lines.append(text)
            else:
                lines.append("```")
                lines.append(_truncate(text))
                lines.append("```")
        else:
            lines.append("（无文本内容）")
        lines.append("")
        if timestamp:
            previous_ts = timestamp
    return "\n".join(lines).rstrip() + "\n"
