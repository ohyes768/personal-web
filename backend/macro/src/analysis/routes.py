"""Password unlock and raw-evidence chart-analysis HTTP boundary."""
import asyncio
import hmac
import json
from datetime import date
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, model_validator

from src.analysis import auth
from src.analysis.registry import CHARTS
from src.analysis.sessions import store
from src.analysis.snapshot import build_snapshot
from src.config import get_settings
from src.services.data_service import get_data_service

@asynccontextmanager
async def lifespan(app):
    async def sweep():
        while True:
            await asyncio.sleep(60)
            store.cleanup()
    cleanup = asyncio.create_task(sweep())
    try:
        yield
    finally:
        cleanup.cancel()
        tasks = [gen.task for session in store.sessions.values() for gen in session.requests.values() if gen.task and gen.status == "running"]
        for task in tasks:
            task.cancel()
        await asyncio.gather(cleanup, *tasks, return_exceptions=True)


router = APIRouter(lifespan=lifespan, prefix="/api/analysis", tags=["chart-analysis"])


class UnlockBody(BaseModel):
    password: str = Field(min_length=1, max_length=200)


class SnapshotBody(BaseModel):
    chart_id: str = Field(max_length=200)
    start_date: date
    end_date: date

    @model_validator(mode="after")
    def valid_range(self):
        if self.start_date > self.end_date:
            raise ValueError("开始日期不得晚于结束日期")
        return self


class MessageBody(BaseModel):
    request_id: str = Field(min_length=8, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    message: str = Field(min_length=1, max_length=2000)


@router.get("/auth")
def auth_status(request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    settings = get_settings()
    unlocked = False
    if settings.analysis_password and settings.analysis_signing_secret:
        try:
            auth.owner(request)
            unlocked = True
        except HTTPException:
            pass
    return {"unlocked": unlocked, "configured": bool(settings.analysis_password and settings.analysis_signing_secret),
            "model_ready": bool(settings.deepseek_api_key)}


@router.post("/auth/unlock")
async def unlock(body: UnlockBody, request: Request, response: Response):
    auth.check_origin(request)
    auth.signing_key()
    auth.check_attempt("unlock:" + (request.client.host if request.client else "unknown"))
    if not hmac.compare_digest(body.password.encode(), get_settings().analysis_password.encode()):
        raise HTTPException(401, "密码不正确")
    response.set_cookie(auth.COOKIE, auth.issue_token(), max_age=auth.LIFETIME, httponly=True,
                        secure=get_settings().analysis_cookie_secure, samesite="strict", path="/")
    response.headers["Cache-Control"] = "no-store"
    return {"unlocked": True, "expires_in": auth.LIFETIME}


@router.post("/auth/lock")
async def lock(request: Request, response: Response, identity: str = Depends(auth.owner)):
    auth.check_origin(request)
    auth.revoke(identity)
    store.lock_owner(identity)
    response.delete_cookie(auth.COOKIE, path="/")
    return {"unlocked": False}


@router.get("/charts")
def charts():
    return {"charts": [{"id": c.id, "title": c.title, "description": c.description,
                         "series_ids": [s.id for s in c.series], "series": [{"id": s.id, "label": s.label, "unit": s.unit} for s in c.series], "version": c.version} for c in CHARTS.values()]}


@router.post("/sessions")
async def create_session(body: SnapshotBody, request: Request, identity: str = Depends(auth.owner)):
    auth.check_origin(request)
    auth.check_attempt("snapshot:" + identity)
    definition = CHARTS.get(body.chart_id)
    if definition is None:
        raise HTTPException(422, "该图表尚未接入分析")
    if not get_settings().deepseek_api_key:
        raise HTTPException(503, "DeepSeek密钥尚未配置")
    evidence = await asyncio.to_thread(build_snapshot, definition, body.start_date, body.end_date, get_data_service())
    session = store.create(identity, evidence, definition)
    return {"session_id": session.id, "snapshot": evidence, "expires_in": 1800, "schema_version": "1.0"}


@router.post("/sessions/{session_id}/messages")
async def messages(session_id: str, body: MessageBody, request: Request, identity: str = Depends(auth.owner)):
    auth.check_origin(request)
    session = store.get(session_id, identity)
    if body.request_id not in session.requests:
        auth.check_attempt("generate:" + identity)
    generation = store.start(session, body.request_id, body.message)

    async def events():
        cursor = 0
        try:
            while True:
                generation.changed.clear()
                while cursor < len(generation.events):
                    event = generation.events[cursor]
                    cursor += 1
                    yield "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"
                if generation.status != "running":
                    break
                try:
                    await asyncio.wait_for(generation.changed.wait(), timeout=10)
                except TimeoutError:
                    yield ": heartbeat\n\n"
        finally:
            if generation.status == "running" and generation.task:
                generation.cancel()

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


@router.get("/sessions/{session_id}/requests/{request_id}")
async def get_result(session_id: str, request_id: str, response: Response, identity: str = Depends(auth.owner)):
    generation = store.get(session_id, identity).requests.get(request_id)
    if generation is None:
        raise HTTPException(404, "请求不存在")
    response.headers["Cache-Control"] = "no-store"
    return {"status": generation.status, "text": generation.text, "usage": generation.usage}


@router.delete("/sessions/{session_id}/requests/{request_id}")
async def cancel(session_id: str, request_id: str, request: Request, identity: str = Depends(auth.owner)):
    auth.check_origin(request)
    generation = store.get(session_id, identity).requests.get(request_id)
    if generation is None:
        raise HTTPException(404, "请求不存在")
    if generation.status == "running" and generation.task:
        generation.cancel()
    return {"cancelled": generation.status == "cancelled"}
