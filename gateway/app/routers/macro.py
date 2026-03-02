"""
宏观金融数据路由转发器
"""
from fastapi import APIRouter, Query, Request
from app.utils.http_client import proxy_request
from app.config import settings

router = APIRouter()


@router.post("/update")
async def update_macro_data(request: Request):
    """转发到 global-macro-fin 服务 - 更新债券利率数据（n8n 调用）"""
    target_url = f"{settings.MACRO_SERVICE_URL}/api/update"
    return await proxy_request("POST", target_url, headers=dict(request.headers))


@router.get("/data")
async def get_macro_data(
    request: Request,
    start_date: str = Query(None, description="起始日期 (YYYY-MM-DD)"),
    end_date: str = Query(None, description="结束日期 (YYYY-MM-DD)")
):
    """转发到 global-macro-fin 服务 - 获取债券利率数据"""
    target_url = f"{settings.MACRO_SERVICE_URL}/api/data"
    params = {}
    if start_date:
        params["start_date"] = start_date
    if end_date:
        params["end_date"] = end_date
    return await proxy_request("GET", target_url, params=params, headers=dict(request.headers))


@router.get("/health")
async def get_macro_health(request: Request):
    """转发到 global-macro-fin 服务 - 健康检查"""
    target_url = f"{settings.MACRO_SERVICE_URL}/api/health"
    return await proxy_request("GET", target_url, headers=dict(request.headers))
