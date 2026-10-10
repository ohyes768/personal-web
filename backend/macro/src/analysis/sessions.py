"""Bounded ephemeral sessions and idempotent, cancelable generation tasks."""
import asyncio
import json
import secrets
import time
from dataclasses import dataclass, field

from fastapi import HTTPException
from src.analysis.deepseek import SYSTEM, stream_answer
from src.analysis.registry import ChartDefinition
from src.config import get_settings


@dataclass
class Generation:
    id: str
    text: str = ""
    status: str = "running"
    events: list[dict] = field(default_factory=list)
    changed: asyncio.Event = field(default_factory=asyncio.Event)
    task: asyncio.Task | None = None
    usage: dict | None = None

    def cancel(self):
        if self.status != "running":
            return
        self.status = "cancelled"
        self.emit({"kind": "error", "message": "已停止生成，未完成内容不进入对话历史"})
        if self.task:
            self.task.cancel()

    def emit(self, event: dict):
        self.events.append(event)
        self.changed.set()


@dataclass
class Session:
    id: str
    owner: str
    evidence: dict
    strategy: str
    created: float = field(default_factory=time.monotonic)
    touched: float = field(default_factory=time.monotonic)
    history: list[dict] = field(default_factory=list)
    requests: dict[str, Generation] = field(default_factory=dict)

    def running(self):
        return any(g.status == "running" for g in self.requests.values())


class SessionStore:
    def __init__(self, stream=stream_answer):
        self.sessions: dict[str, Session] = {}
        self.stream = stream

    def cleanup(self):
        now = time.monotonic()
        for key, session in list(self.sessions.items()):
            if not session.running() and (now - session.touched > 1800 or now - session.created > 7200):
                del self.sessions[key]

    def create(self, owner: str, evidence: dict, definition: ChartDefinition):
        self.cleanup()
        if len(self.sessions) >= 100:
            raise HTTPException(429, "分析会话已满，请稍后重试")
        session = Session(secrets.token_urlsafe(24), owner, evidence, definition.strategy)
        self.sessions[session.id] = session
        return session

    def get(self, session_id: str, owner: str):
        session = self.sessions.get(session_id)
        if session is None:
            raise HTTPException(410, "会话已过期，请重新分析")
        if session.owner != owner:
            raise HTTPException(404, "会话不存在")
        now = time.monotonic()
        if now - session.created > 7200 or now - session.touched > 1800:
            for gen in session.requests.values():
                if gen.task and gen.status == "running":
                    gen.cancel()
            del self.sessions[session_id]
            raise HTTPException(410, "会话已过期，请重新分析")
        session.touched = now
        return session

    def start(self, session: Session, request_id: str, message: str):
        if request_id in session.requests:
            return session.requests[request_id]
        if not get_settings().deepseek_api_key:
            raise HTTPException(503, "DeepSeek密钥尚未配置，请联系站点管理员")
        if session.running():
            raise HTTPException(409, "当前回答正在生成")
        if len(session.history) >= 20 or len(session.requests) >= 30:
            raise HTTPException(429, "已达到本会话上限，请重新分析")
        if sum(s.running() for s in self.sessions.values()) >= 2:
            raise HTTPException(429, "分析服务繁忙，请稍后重试")
        messages = [
            {"role": "system", "content": SYSTEM + "\n图表策略：" + session.strategy},
            {"role": "system", "content": "以下是只读数据证据：" + json.dumps(session.evidence, ensure_ascii=False)},
            *session.history, {"role": "user", "content": message},
        ]
        if sum(len(m["content"]) for m in messages) > 32000:
            raise HTTPException(422, "本次对话太长，请重新分析")
        gen = Generation(request_id)
        session.requests[request_id] = gen
        gen.emit({"kind": "meta", "snapshot_id": session.evidence["snapshot_id"], "request_id": request_id})
        gen.task = asyncio.create_task(self._generate(session, gen, messages, message))
        return gen

    async def _generate(self, session, gen, messages, message):
        try:
            async with asyncio.timeout(get_settings().analysis_timeout_seconds):
                async for event in self.stream(messages):
                    if event["kind"] == "delta":
                        gen.text += event["text"]
                        if len(gen.text) > 16000:
                            raise ValueError("回答过长")
                        gen.emit(event)
                    elif event["kind"] == "usage":
                        gen.usage = event["usage"]
            if gen.status != "running":
                return
            if not gen.text.strip():
                raise ValueError("空回答")
            session.history.extend([{"role": "user", "content": message}, {"role": "assistant", "content": gen.text}])
            gen.status = "complete"
            gen.emit({"kind": "done", "message_id": gen.id, "usage": gen.usage})
        except asyncio.CancelledError:
            if gen.status == "running":
                gen.status = "cancelled"
                gen.emit({"kind": "error", "message": "已停止生成，未完成内容不进入对话历史"})
        except Exception:
            gen.status = "failed"
            # Never expose provider response bodies, credentials or internal URLs.
            gen.emit({"kind": "error", "message": "分析生成失败或超时，请稍后重试"})
        finally:
            session.touched = time.monotonic()
            gen.changed.set()

    def lock_owner(self, owner: str):
        for key, session in list(self.sessions.items()):
            if session.owner == owner:
                for gen in session.requests.values():
                    if gen.task and gen.status == "running":
                        gen.cancel()
                del self.sessions[key]


store = SessionStore()
