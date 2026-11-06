"""scheduler 管理 API 路由（最终路径 /api/scheduler/*）

4 个管理 API，与 dividend-select /macro 的 scheduler routes 同形：
GET /jobs · PATCH /jobs/{id}（启停）· POST /jobs/{id}/run（立即执行）· GET /jobs/{id}/runs（历史）
"""

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api/scheduler", tags=["scheduler"])


class PatchJobBody(BaseModel):
    enabled: bool


def _get_scheduler(request: Request):
    """从 app.state 拿 scheduler 实例；未初始化返回 503。"""
    scheduler = getattr(request.app.state, "scheduler", None)
    if scheduler is None:
        raise HTTPException(status_code=503, detail="scheduler 未初始化")
    return scheduler


@router.get("/jobs")
async def list_jobs(request: Request):
    scheduler = _get_scheduler(request)
    return {"jobs": scheduler.list_jobs()}


@router.patch("/jobs/{job_id}")
async def patch_job(request: Request, job_id: str, body: PatchJobBody):
    scheduler = _get_scheduler(request)
    try:
        updated = scheduler.set_enabled(job_id, body.enabled)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"job not found: {job_id}")
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    return updated


@router.post("/jobs/{job_id}/run")
async def run_job_now(request: Request, job_id: str):
    scheduler = _get_scheduler(request)
    try:
        result = scheduler.trigger_now(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"job not found: {job_id}")
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    return result


@router.get("/jobs/{job_id}/runs")
async def list_runs(
    request: Request,
    job_id: str,
    limit: int = Query(default=20, ge=1, le=200),
):
    scheduler = _get_scheduler(request)
    try:
        runs = scheduler.get_job_runs(job_id, limit=limit)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"job not found: {job_id}")
    return {"job_id": job_id, "runs": runs, "total_returned": len(runs)}
