"""
抖音视频路由转发器
"""
from fastapi import APIRouter, Query, Request
from app.utils.http_client import proxy_request
from app.config import settings

router = APIRouter()


@router.get("/videos")
async def get_videos(
    request: Request,
    page: int = Query(1, description="页码"),
    page_size: int = Query(20, description="每页数量"),
    status: str = Query(None, description="状态筛选"),
    is_read: bool = Query(None, description="已读状态筛选")
):
    """转发到 douyin-processor 服务 - 获取已处理视频列表"""
    target_url = f"{settings.DOUYIN_PROCESSOR_URL}/api/videos"
    params = {"page": page, "page_size": page_size}
    if status:
        params["status"] = status
    if is_read is not None:
        params["is_read"] = is_read
    return await proxy_request("GET", target_url, params=params, headers=dict(request.headers))


@router.get("/videos/{video_id}")
async def get_video_detail(request: Request, video_id: str):
    """转发到 douyin-processor 服务 - 获取视频详情"""
    target_url = f"{settings.DOUYIN_PROCESSOR_URL}/api/videos/{video_id}"
    return await proxy_request("GET", target_url, headers=dict(request.headers))


@router.get("/search")
async def search_videos(
    request: Request,
    keyword: str = Query(..., description="搜索关键词"),
    page: int = Query(1, description="页码"),
    page_size: int = Query(20, description="每页数量")
):
    """转发到 douying-collect 服务 - 搜索视频"""
    target_url = f"{settings.DOUYIN_SERVICE_URL}/api/douyin/search"
    params = {"keyword": keyword, "page": page, "page_size": page_size}
    return await proxy_request("GET", target_url, params=params, headers=dict(request.headers))


@router.post("/collect")
async def start_collection(request: Request):
    """转发到 douying-collect 服务 - 触发数据采集"""
    target_url = f"{settings.DOUYIN_SERVICE_URL}/api/douyin/collect"
    return await proxy_request("POST", target_url, headers=dict(request.headers))


@router.get("/collect/status")
async def get_collection_status(request: Request):
    """转发到 douying-collect 服务 - 获取采集状态"""
    target_url = f"{settings.DOUYIN_SERVICE_URL}/api/douyin/collect/status"
    return await proxy_request("GET", target_url, headers=dict(request.headers))


@router.post("/process")
async def process_videos(request: Request):
    """转发到 douyin-processor 服务 - 触发视频处理（同步，等待完成）"""
    target_url = f"{settings.DOUYIN_PROCESSOR_URL}/api/process"
    return await proxy_request("POST", target_url, headers=dict(request.headers))


@router.get("/stats")
async def get_stats(request: Request):
    """转发到 douyin-processor 服务 - 获取统计信息"""
    target_url = f"{settings.DOUYIN_PROCESSOR_URL}/api/stats"
    return await proxy_request("GET", target_url, headers=dict(request.headers))


@router.get("/videos/{video_id}/result")
async def get_video_result(request: Request, video_id: str):
    """转发到 douyin-processor 服务 - 获取处理结果"""
    target_url = f"{settings.DOUYIN_SERVICE_URL}/api/videos/{video_id}/result"
    return await proxy_request("GET", target_url, headers=dict(request.headers))


@router.post("/videos/{video_id}/read")
async def mark_video_read(request: Request, video_id: str):
    """转发到 douyin-processor 服务 - 标记视频已读/未读"""
    target_url = f"{settings.DOUYIN_PROCESSOR_URL}/api/videos/{video_id}/read"
    return await proxy_request("POST", target_url, headers=dict(request.headers), content=await request.body())


@router.delete("/videos/{video_id}")
async def delete_video(request: Request, video_id: str):
    """转发到 douyin-processor 服务 - 删除视频"""
    target_url = f"{settings.DOUYIN_PROCESSOR_URL}/api/videos/{video_id}"
    return await proxy_request("DELETE", target_url, headers=dict(request.headers))
