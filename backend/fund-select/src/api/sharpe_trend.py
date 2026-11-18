"""夏普走势只读 API（GET /api/funds/sharpe-trend/{code}）

⚠ 注册顺序：本 router 必须在通用详情 router（src/api/routes.py 的
/{code} 路由）之前 include（src/main.py）——FastAPI 按注册顺序匹配，
后注册会让 /api/funds/sharpe-trend/000628 被 /{code} 吞掉当基金代码查
（404「基金不存在: sharpe-trend」）。

现算（不落库、不进调度），口径见 src/services/sharpe_trend_service.py：
- 纯净值口径，不 join fund_benchmark（避免历史窗口被基准起始日截断）
- range 只裁返回点集，不改每点的 3 年滚动窗口
- 错误语义与「正常空态」分开：网络失败 502 / 不存在 404 / 历史不足 200+diagnostics
"""
from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.models import (
    SharpeTrendPointDTO,
    SharpeTrendResponse,
    SharpeTrendStatsDTO,
)
from src.db.session import get_db
from src.services.sharpe_trend_service import (
    FundNotFoundError,
    NavFetchError,
    TrendResult,
    build_trend,
)

router = APIRouter(tags=["sharpe-trend"])


def _to_response(result: TrendResult) -> SharpeTrendResponse:
    """service 结果 → DTO（显式逐字段构造，不依赖 dict 自动展开漏字段）"""
    return SharpeTrendResponse(
        code=result.code,
        name=result.name,
        range=result.range,
        rf_basis=result.rf_basis,
        algorithm_version=result.algorithm_version,
        threshold=result.threshold,
        points=[
            SharpeTrendPointDTO(
                date=p.date, sharpe=p.sharpe, sample_days=p.sample_days,
            )
            for p in result.points
        ],
        stats=SharpeTrendStatsDTO(
            threshold=result.stats.threshold,
            current=result.stats.current,
            max=result.stats.max,
            min=result.stats.min,
            mean=result.stats.mean,
            above_count=result.stats.above_count,
            valid_count=result.stats.valid_count,
            above_ratio=result.stats.above_ratio,
            consecutive_above=result.stats.consecutive_above,
            longest_below=result.stats.longest_below,
            trend_12w=result.stats.trend_12w,
        ),
        diagnostics=result.diagnostics,
    )


@router.get("/sharpe-trend/{code}", response_model=SharpeTrendResponse)
async def sharpe_trend(
    code: str,
    range: str = Query("all", pattern="^(all|3y|1y)$",
                       description="展示区间（只裁返回点集，不改滚动窗口）"),
    db=Depends(get_db),
):
    """单基金周频滚动 3 年夏普曲线 + 稳定性 KPI。"""
    try:
        result = build_trend(db, code, range)
    except NavFetchError as e:
        # 外部请求失败：与「确实无历史」分开，前端可重试
        raise HTTPException(status_code=502, detail=f"净值拉取失败: {e}") from e
    except FundNotFoundError:
        raise HTTPException(
            status_code=404, detail=f"基金不存在或无法获取净值: {code}",
        )
    return _to_response(result)
