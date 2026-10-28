"""小区轮廓生成工作流接口:公开无鉴权(所有能打开地图的人都可生成、应用、撤销)。

与旧的 /boundaries/import 分离:旧接口仍是本服务唯一带 token 的写入口,行为不变;
本组接口只接受小区 ID / 候选 ID / 版本号 / 操作 ID,浏览器不提交任何几何。
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.services import boundary_workflow
from src.services.boundary_workflow import WorkflowError

router = APIRouter(tags=["map"])


class EstimateRequest(BaseModel):
    regenerate: bool = False
    refresh_buildings: bool = False


class RevisionRequest(BaseModel):
    expected_revision: str = ""


class ApplyRequest(RevisionRequest):
    operation_id: str


class RevertRequest(RevisionRequest):
    apply_operation_id: str
    operation_id: str


def _raise(error: WorkflowError) -> None:
    raise HTTPException(status_code=error.status_code, detail={"code": error.code, "message": error.message})


@router.get("/communities/{community_id}/boundary-workflow")
async def get_boundary_workflow(community_id: str):
    try:
        return {"success": True, "data": boundary_workflow.community_state(community_id)}
    except WorkflowError as error:
        _raise(error)


@router.post("/communities/{community_id}/boundary-estimates")
async def create_boundary_estimate(community_id: str, payload: EstimateRequest | None = None):
    body = payload or EstimateRequest()
    try:
        status, data = boundary_workflow.create_estimate(
            community_id, regenerate=body.regenerate, refresh_buildings=body.refresh_buildings)
        # 新任务 202(异步),复用已有任务/候选 200
        return JSONResponse(status_code=status, content={"success": True, "data": data})
    except WorkflowError as error:
        _raise(error)


@router.get("/boundary-estimates/{job_id}")
async def get_boundary_estimate(job_id: str):
    try:
        return {"success": True, "data": boundary_workflow.job_state(job_id)}
    except WorkflowError as error:
        _raise(error)


@router.get("/boundary-candidates/{candidate_id}")
async def get_boundary_candidate(candidate_id: str):
    try:
        return {"success": True, "data": boundary_workflow.candidate_state(candidate_id)}
    except WorkflowError as error:
        _raise(error)


@router.post("/boundary-candidates/{candidate_id}/reject")
async def reject_boundary_candidate(candidate_id: str, payload: RevisionRequest):
    try:
        return {"success": True, "data": boundary_workflow.reject_candidate(
            candidate_id, payload.expected_revision)}
    except WorkflowError as error:
        _raise(error)


@router.post("/boundary-candidates/{candidate_id}/apply")
async def apply_boundary_candidate(candidate_id: str, payload: ApplyRequest):
    try:
        return {"success": True, "data": boundary_workflow.apply_candidate(
            candidate_id, payload.expected_revision, payload.operation_id)}
    except WorkflowError as error:
        _raise(error)


@router.post("/communities/{community_id}/boundary-reverts")
async def revert_boundary(community_id: str, payload: RevertRequest):
    try:
        return {"success": True, "data": boundary_workflow.revert_community(
            community_id, payload.expected_revision, payload.apply_operation_id, payload.operation_id)}
    except WorkflowError as error:
        _raise(error)
