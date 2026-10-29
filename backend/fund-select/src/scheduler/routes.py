"""Weekly scheduler management API, consistent with macro's route shape."""
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

router = APIRouter(prefix="/scheduler", tags=["scheduler"])


class PatchJobBody(BaseModel):
    enabled: bool


def _manager(request: Request):
    manager = getattr(request.app.state, "scheduler", None)
    if manager is None:
        raise HTTPException(503, "定时任务尚未初始化")
    return manager


@router.get("/jobs")
async def list_jobs(request: Request):
    return {"jobs": _manager(request).list_jobs()}


@router.patch("/jobs/{job_id}")
async def patch_job(request: Request, job_id: str, body: PatchJobBody):
    try:
        return _manager(request).set_enabled(job_id, body.enabled)
    except KeyError:
        raise HTTPException(404, "任务不存在")
    except OSError:
        raise HTTPException(503, "保存启停设置失败，请重试")


@router.post("/jobs/{job_id}/run")
async def run_now(request: Request, job_id: str):
    try:
        return await _manager(request).trigger_now(job_id)
    except KeyError:
        raise HTTPException(404, "任务不存在")
    except ValueError as exc:
        raise HTTPException(409, str(exc))


@router.get("/jobs/{job_id}/runs")
async def get_runs(request: Request, job_id: str, limit: int = Query(20, ge=1, le=200)):
    try:
        runs = _manager(request).get_job_runs(job_id, limit)
        return {"job_id": job_id, "runs": runs}
    except KeyError:
        raise HTTPException(404, "任务不存在")
