"""
经济数据路由转发器
"""
from fastapi import APIRouter, Query, Request
from app.utils.http_client import proxy_request
from app.config import settings

router = APIRouter()


@router.get("/exchange-rates")
async def get_exchange_rates(
    request: Request,
    time_range: str = Query("1Y", description="时间范围: 1M, 3M, 6M, 1Y, 3Y, All")
):
    """转发到 FinancialDashboard 服务 - 获取汇率数据"""
    target_url = f"{settings.FINANCIAL_SERVICE_URL}/api/exchange-rates"
    params = {"time_range": time_range}
    return await proxy_request("GET", target_url, params=params, headers=dict(request.headers))


@router.get("/treasury-yields")
async def get_treasury_yields(
    request: Request,
    time_range: str = Query("1Y", description="时间范围")
):
    """转发到 FinancialDashboard 服务 - 获取美债收益率数据"""
    target_url = f"{settings.FINANCIAL_SERVICE_URL}/api/treasury-yields"
    params = {"time_range": time_range}
    return await proxy_request("GET", target_url, params=params, headers=dict(request.headers))


@router.get("/debt-gdp")
async def get_debt_gdp(
    request: Request,
    time_range: str = Query("1Y", description="时间范围")
):
    """转发到 FinancialDashboard 服务 - 获取债务GDP数据"""
    target_url = f"{settings.FINANCIAL_SERVICE_URL}/api/debt-gdp"
    params = {"time_range": time_range}
    return await proxy_request("GET", target_url, params=params, headers=dict(request.headers))


@router.get("/tga-hibor")
async def get_tga_hibor(
    request: Request,
    time_range: str = Query("1Y", description="时间范围")
):
    """转发到 FinancialDashboard 服务 - 获取TGA/HIBOR数据"""
    target_url = f"{settings.FINANCIAL_SERVICE_URL}/api/tga-hibor"
    params = {"time_range": time_range}
    return await proxy_request("GET", target_url, params=params, headers=dict(request.headers))
