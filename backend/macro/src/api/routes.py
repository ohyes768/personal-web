"""API 路由模块"""
print("[INIT-20260303-0942] routes.py 模块已加载")
from fastapi import APIRouter, HTTPException, Query, Header, Response
from datetime import datetime, timedelta
import hmac
import pandas as pd
from typing import Optional

from pydantic import BaseModel

from src.models import (
    UpdateResponse,
    DataResponse,
    HealthResponse,
    MacroData,
    MacroDataWithRates,
    MacroDataWithRatesAndVIX,
    TreasuryData,
    USTreasuries,
    EUTreasuries,
    JPTreasuries,
    USTreasuriesUpdateData,
    EUTreasuriesUpdateData,
    JPTreasuriesUpdateData,
    ExchangeRateData,
    ExchangeRates,
    ExchangeRatesUpdateData,
    VIXData,
    VIXUpdateData,
    TGAData,
    TGAUpdateData,
    HIBORData,
    HIBORUpdateData,
    DR007Data,
    DR007UpdateData,
    VolumeData,
    VolumeUpdateData,
    TurnoverData,
    TurnoverUpdateData,
    MarginData,
    MarginUpdateData,
    FundFlowData,
    FundFlow,
    FundFlowUpdateData,
    FundFlowCumulativeData,
    FundFlowCumulativeResponse,
    FundFlowHistoryItem,
    FundFlowHistoryResponse,
    ChinaBondData,
    ChinaBondUpdateData,
    TedSpreadData,
    TedSpreadUpdateData,
    CommoditiesData,
    CommoditiesUpdateData,
    IndicesData,
    IndicesUpdateData,
    MacroSignalResponse,
    MacroMonthsResponse,
    DailySnapshotResponse,
)
from src.services.fred_service import get_fred_service
from src.services.ecb_service import get_ecb_service
from src.services.data_service import get_data_service
from src.services.vix_service import get_vix_service
from src.services.hibor_service import get_hibor_service
from src.services.dr007_service import get_dr007_service
from src.services.volume_service import get_volume_service
from src.services.turnover_service import get_turnover_service
from src.services.margin_service import get_margin_service
from src.services.fund_flow_service import get_fund_flow_service
from src.services.china_bond_service import get_china_bond_service
from src.services.commodity_service import get_commodity_service
from src.services.index_service import get_index_service
from src.services.macro_signal_service import get_macro_signal_service
from src.services.daily_snapshot_service import get_daily_snapshot_service
from src.utils.logger import setup_logger
from src.config import get_settings

logger = setup_logger("api_routes")
settings = get_settings()

router = APIRouter(prefix="/api", tags=["macro"])

# 并发控制锁
_update_lock = None
_is_updating = False


async def acquire_update_lock():
    """获取更新锁"""
    global _is_updating
    _is_updating = True


def release_update_lock():
    """释放更新锁"""
    global _is_updating
    _is_updating = False


def is_updating() -> bool:
    """检查是否正在更新"""
    return _is_updating


async def _fetch_us_treasuries(
    fred_service, start_date: pd.Timestamp, end_date: pd.Timestamp
) -> dict:
    """获取美国国债数据的内部函数

    Args:
        fred_service: FRED 服务实例
        start_date: 起始日期
        end_date: 结束日期

    Returns:
        美债数据字典
    """
    logger.info(f"获取美国国债数据范围: {start_date} 到 {end_date}")

    us_data = {}
    us_codes = {"us_3m", "us_2y", "us_10y"}

    for name in us_codes:
        code = settings.fred_codes[name]
        try:
            series = await fred_service.fetch_series(code, start_date, end_date)
            us_data[name] = series
        except Exception as e:
            logger.error(f"获取 {name} ({code}) 数据时出错: {e}")
            us_data[name] = pd.Series(dtype="float64")

    return us_data


async def _fetch_oecd_bonds(
    fred_service, start_date: pd.Timestamp, end_date: pd.Timestamp
) -> dict:
    """获取 OECD 债券数据的内部函数

    Args:
        fred_service: FRED 服务实例
        start_date: 起始日期
        end_date: 结束日期

    Returns:
        OECD 债券数据字典
    """
    logger.info(f"获取 OECD 债券数据范围: {start_date} 到 {end_date}")

    oecd_data = {}
    ecb_service = get_ecb_service()

    # FRED 数据代码
    fred_bond_codes = {"eu_3m", "eu_10y", "jp_10y"}

    # ECB 数据代码（德债 2年期、5年期）
    ecb_bond_codes = {"eu_2y_ecb"}

    # 从 FRED 获取数据
    for name in fred_bond_codes:
        if name not in settings.fred_codes:
            continue
        code = settings.fred_codes[name]
        try:
            series = await fred_service.fetch_series(code, start_date, end_date)
            oecd_data[name] = series
        except Exception as e:
            logger.error(f"获取 {name} ({code}) 数据时出错: {e}")
            oecd_data[name] = pd.Series(dtype="float64")

    # 从 ECB 获取数据
    for name in ecb_bond_codes:
        try:
            series = await ecb_service.fetch_series(name, start_date, end_date)
            oecd_data[name] = series
        except Exception as e:
            logger.error(f"获取 {name} (ECB) 数据时出错: {e}")
            oecd_data[name] = pd.Series(dtype="float64")

    return oecd_data




async def _fetch_exchange_rates(
    fred_service, start_date: pd.Timestamp, end_date: pd.Timestamp
) -> dict:
    """获取汇率数据的内部函数

    Args:
        fred_service: FRED 服务实例
        start_date: 起始日期
        end_date: 结束日期

    Returns:
        汇率数据字典
    """
    logger.info(f"获取汇率数据范围: {start_date} 到 {end_date}")

    exchange_data = await fred_service.fetch_exchange_rates(start_date, end_date)
    return exchange_data


def _compute_incremental_start(
    data_service, data_type: str, latest_end: pd.Timestamp
):
    """计算增量更新起点（关键修复：避免数据落后时出现 gap）

    旧逻辑用 `latest_end - 7 days` 作为起点：当数据落后超过 7 天时，
    `append_data` 拼接时会跳过中间日期，导致数据断裂（CSV last_date 之后有 gap）。

    新逻辑：用 CSV last_date + 1 作为起点，保证补齐所有缺失日期。

    Returns:
        start_date (pd.Timestamp) 或 None（数据已是最新，无需更新）
    """
    last_date = data_service.get_last_date(data_type)
    if last_date is None:
        # CSV 为空：全量获取（从历史起点）
        return pd.Timestamp(settings.historical_start_date)

    # 从 CSV 最后日期的次日开始（补齐中间缺失的日期）
    start = pd.Timestamp(last_date) + pd.Timedelta(days=1)

    # 兜底：如果 start > latest_end，说明数据已是最新，无须拉取
    # （FRED API 会拒绝 observation_start > observation_end 的请求）
    if start > latest_end:
        logger.info(f"{data_type} 数据已是最新（last_date={last_date.strftime('%Y-%m-%d')}），无需更新")
        return None

    return start


def _build_response_data(new_data: dict, end_date: pd.Timestamp) -> MacroData:
    """构建响应数据的内部函数（不包含汇率）

    Args:
        new_data: 新获取的数据字典
        end_date: 结束日期

    Returns:
        MacroData 响应对象
    """
    latest = {}
    for name, series in new_data.items():
        if not series.empty:
            last_idx = series.last_valid_index()
            if last_idx is not None:
                latest[name] = {"date": last_idx.strftime("%Y-%m-%d"), "value": float(series[last_idx])}

    us_m3 = latest.get("us_3m", TreasuryData(date=end_date.date(), value=None))
    us_y2 = latest.get("us_2y", TreasuryData(date=end_date.date(), value=None))
    us_y10 = latest.get("us_10y", TreasuryData(date=end_date.date(), value=None))
    eu_m3 = latest.get("eu_3m", TreasuryData(date=end_date.date(), value=None))
    eu_y2 = latest.get("eu_2y_ecb", TreasuryData(date=end_date.date(), value=None))
    eu_y10 = latest.get("eu_10y", TreasuryData(date=end_date.date(), value=None))
    jp_y10 = latest.get("jp_10y", TreasuryData(date=end_date.date(), value=None))

    return MacroData(
        us_treasuries=USTreasuries(m3=us_m3, y2=us_y2, y10=us_y10),
        eu_treasuries=EUTreasuries(m3=eu_m3, y2=eu_y2, y10=eu_y10),
        jp_treasuries=JPTreasuries(y10=jp_y10),
    )



def _build_response_data_with_rates(
    new_data: dict, exchange_data: dict, end_date: pd.Timestamp
) -> MacroDataWithRates:
    """构建包含汇率的响应数据的内部函数

    Args:
        new_data: 新获取的债券数据字典
        exchange_data: 新获取的汇率数据字典
        end_date: 结束日期

    Returns:
        MacroDataWithRates 响应对象
    """
    # 处理债券数据
    latest = {}
    for name, series in new_data.items():
        if not series.empty:
            last_idx = series.last_valid_index()
            if last_idx is not None:
                latest[name] = {"date": last_idx.strftime("%Y-%m-%d"), "value": float(series[last_idx])}

    # 处理汇率数据
    latest_rates = {}
    for name, series in exchange_data.items():
        if not series.empty:
            last_idx = series.last_valid_index()
            if last_idx is not None:
                latest_rates[name] = {"date": last_idx.strftime("%Y-%m-%d"), "value": float(series[last_idx])}

    us_m3 = latest.get("us_3m", TreasuryData(date=end_date.date(), value=None))
    us_y2 = latest.get("us_2y", TreasuryData(date=end_date.date(), value=None))
    us_y10 = latest.get("us_10y", TreasuryData(date=end_date.date(), value=None))
    eu_y10 = latest.get("eu_10y", TreasuryData(date=end_date.date(), value=None))
    jp_y10 = latest.get("jp_10y", TreasuryData(date=end_date.date(), value=None))

    dollar_index = latest_rates.get("dollar_index", ExchangeRateData(date=end_date.date(), value=None))
    usd_cny = latest_rates.get("usd_cny", ExchangeRateData(date=end_date.date(), value=None))
    usd_jpy = latest_rates.get("usd_jpy", ExchangeRateData(date=end_date.date(), value=None))
    usd_eur = latest_rates.get("usd_eur", ExchangeRateData(date=end_date.date(), value=None))

    return MacroDataWithRates(
        us_treasuries=USTreasuries(m3=us_m3, y2=us_y2, y10=us_y10),
        eu_treasuries=EUTreasuries(m3=eu_m3, y2=eu_y2, y10=eu_y10),
        jp_treasuries=JPTreasuries(y10=jp_y10),
        exchange_rates=ExchangeRates(
            dollar_index=dollar_index,
            usd_cny=usd_cny,
            usd_jpy=usd_jpy,
            usd_eur=usd_eur,
        ),
    )


@router.post("/fetch/us-treasuries/history", response_model=UpdateResponse)
async def fetch_us_treasuries_history():
    """获取美国国债历史数据接口 - 从 2000 年开始获取全部历史数据"""
    global _is_updating

    if _is_updating:
        return UpdateResponse(
            success=False,
            message="数据更新正在进行中，请稍后再试",
            error_code="UPDATE_IN_PROGRESS"
        )

    await acquire_update_lock()

    try:
        logger.info("开始获取美国国债历史数据...")
        fred_service = get_fred_service()
        data_service = get_data_service()

        latest_end = pd.Timestamp.now().normalize()
        us_start = pd.Timestamp(settings.historical_start_date)

        logger.info(f"获取美债历史数据，从 {us_start} 到 {latest_end}")

        new_data = await _fetch_us_treasuries(fred_service, us_start, latest_end)

        if not any(not series.empty for series in new_data.values()):
            raise Exception("未能获取到任何美债数据")

        data_service.save_fred_data(new_data)

        # 构建只包含美债的响应数据
        latest = {}
        for name, series in new_data.items():
            if not series.empty:
                last_idx = series.last_valid_index()
                if last_idx is not None:
                    latest[name] = {"date": last_idx.strftime("%Y-%m-%d"), "value": float(series[last_idx])}

        us_m3 = latest.get("us_3m", TreasuryData(date=latest_end.date(), value=None))
        us_y2 = latest.get("us_2y", TreasuryData(date=latest_end.date(), value=None))
        us_y10 = latest.get("us_10y", TreasuryData(date=latest_end.date(), value=None))

        response_data = USTreasuriesUpdateData(
            us_treasuries=USTreasuries(m3=us_m3, y2=us_y2, y10=us_y10)
        )

        logger.info("美国国债历史数据获取成功")
        return UpdateResponse(
            success=True,
            message="美国国债历史数据获取成功",
            data=response_data,
            updated_at=datetime.now().isoformat(),
        )

    except Exception as e:
        logger.error(f"获取美国国债历史数据失败: {str(e)}")
        return UpdateResponse(
            success=False,
            message=f"获取美国国债历史数据失败: {str(e)}",
            error_code="UPDATE_FAILED"
        )
    finally:
        release_update_lock()


@router.post("/update/us-treasuries", response_model=UpdateResponse)
async def update_us_treasuries():
    """更新美国国债数据接口 - 增量更新（从 CSV last_date+1 到今天，补齐中间缺失日期）"""
    global _is_updating

    if _is_updating:
        return UpdateResponse(
            success=False,
            message="数据更新正在进行中，请稍后再试",
            error_code="UPDATE_IN_PROGRESS"
        )

    await acquire_update_lock()

    try:
        logger.info("开始增量更新美国国债数据...")
        fred_service = get_fred_service()
        data_service = get_data_service()

        latest_end = pd.Timestamp.now().normalize()
        us_start = _compute_incremental_start(data_service, "us_treasuries", latest_end)

        if us_start is None:
            # 数据已是最新，直接返回 success（无需拉取/保存）
            logger.info("美债数据已是最新，跳过本次更新")
            response_data = USTreasuriesUpdateData(
                us_treasuries=USTreasuries(
                    m3=TreasuryData(date=latest_end.date(), value=None),
                    y2=TreasuryData(date=latest_end.date(), value=None),
                    y10=TreasuryData(date=latest_end.date(), value=None),
                )
            )
            return UpdateResponse(
                success=True,
                message="美债数据已是最新，无需更新",
                data=response_data,
                updated_at=datetime.now().isoformat(),
            )

        logger.info(f"增量更新美债数据，从 {us_start} 到 {latest_end}")

        new_data = await _fetch_us_treasuries(fred_service, us_start, latest_end)

        if not any(not series.empty for series in new_data.values()):
            raise Exception("未能获取到任何美债新数据")

        data_service.save_fred_data(new_data)

        # 构建只包含美债的响应数据
        latest = {}
        for name, series in new_data.items():
            if not series.empty:
                last_idx = series.last_valid_index()
                if last_idx is not None:
                    latest[name] = {"date": last_idx.strftime("%Y-%m-%d"), "value": float(series[last_idx])}

        us_m3 = latest.get("us_3m", TreasuryData(date=latest_end.date(), value=None))
        us_y2 = latest.get("us_2y", TreasuryData(date=latest_end.date(), value=None))
        us_y10 = latest.get("us_10y", TreasuryData(date=latest_end.date(), value=None))

        response_data = USTreasuriesUpdateData(
            us_treasuries=USTreasuries(m3=us_m3, y2=us_y2, y10=us_y10)
        )

        logger.info("美国国债数据增量更新成功")
        return UpdateResponse(
            success=True,
            message="美国国债数据增量更新成功",
            data=response_data,
            updated_at=datetime.now().isoformat(),
        )

    except Exception as e:
        logger.error(f"美国国债数据增量更新失败: {str(e)}")
        return UpdateResponse(
            success=False,
            message=f"美国国债数据增量更新失败: {str(e)}",
            error_code="UPDATE_FAILED"
        )
    finally:
        release_update_lock()


@router.post("/fetch/exchange-rates/history", response_model=UpdateResponse)
async def fetch_exchange_rates_history():
    """获取汇率历史数据接口 - 从 2000 年开始获取全部历史数据"""
    global _is_updating

    if _is_updating:
        return UpdateResponse(
            success=False,
            message="数据更新正在进行中，请稍后再试",
            error_code="UPDATE_IN_PROGRESS"
        )

    await acquire_update_lock()

    try:
        logger.info("开始获取汇率历史数据...")
        fred_service = get_fred_service()
        data_service = get_data_service()

        latest_end = pd.Timestamp.now().normalize()
        start_date = pd.Timestamp(settings.historical_start_date)

        logger.info(f"获取汇率历史数据，从 {start_date} 到 {latest_end}")

        exchange_data = await _fetch_exchange_rates(fred_service, start_date, latest_end)

        if not any(not series.empty for series in exchange_data.values()):
            raise Exception("未能获取到任何汇率数据")

        # 保存汇率数据
        data_service.save_fred_data(exchange_data, key="exchange_rates")

        # 构建只包含汇率的响应数据
        latest_rates = {}
        for name, series in exchange_data.items():
            if not series.empty:
                last_idx = series.last_valid_index()
                if last_idx is not None:
                    latest_rates[name] = {"date": last_idx.strftime("%Y-%m-%d"), "value": float(series[last_idx])}

        dollar_index = latest_rates.get("dollar_index", ExchangeRateData(date=latest_end.date(), value=None))
        usd_cny = latest_rates.get("usd_cny", ExchangeRateData(date=latest_end.date(), value=None))
        usd_jpy = latest_rates.get("usd_jpy", ExchangeRateData(date=latest_end.date(), value=None))
        usd_eur = latest_rates.get("usd_eur", ExchangeRateData(date=latest_end.date(), value=None))

        response_data = ExchangeRatesUpdateData(
            exchange_rates=ExchangeRates(
                dollar_index=dollar_index,
                usd_cny=usd_cny,
                usd_jpy=usd_jpy,
                usd_eur=usd_eur,
            )
        )

        logger.info("汇率历史数据获取成功")
        return UpdateResponse(
            success=True,
            message="汇率历史数据获取成功",
            data=response_data,
            updated_at=datetime.now().isoformat(),
        )

    except Exception as e:
        logger.error(f"获取汇率历史数据失败: {str(e)}")
        return UpdateResponse(
            success=False,
            message=f"获取汇率历史数据失败: {str(e)}",
            error_code="UPDATE_FAILED"
        )
    finally:
        release_update_lock()


@router.post("/update/exchange-rates", response_model=UpdateResponse)
async def update_exchange_rates():
    """更新汇率数据接口 - 增量更新（从 CSV last_date+1 到今天，补齐中间缺失日期）"""
    global _is_updating

    if _is_updating:
        return UpdateResponse(
            success=False,
            message="数据更新正在进行中，请稍后再试",
            error_code="UPDATE_IN_PROGRESS"
        )

    await acquire_update_lock()

    try:
        logger.info("开始增量更新汇率数据...")
        fred_service = get_fred_service()
        data_service = get_data_service()

        latest_end = pd.Timestamp.now().normalize()
        start_date = _compute_incremental_start(data_service, "exchange_rates", latest_end)

        if start_date is None:
            # 数据已是最新，直接返回 success
            logger.info("汇率数据已是最新，跳过本次更新")
            response_data = ExchangeRatesUpdateData(
                exchange_rates=ExchangeRates(
                    dollar_index=ExchangeRateData(date=latest_end.date(), value=None),
                    usd_cny=ExchangeRateData(date=latest_end.date(), value=None),
                    usd_jpy=ExchangeRateData(date=latest_end.date(), value=None),
                    usd_eur=ExchangeRateData(date=latest_end.date(), value=None),
                )
            )
            return UpdateResponse(
                success=True,
                message="汇率数据已是最新，无需更新",
                data=response_data,
                updated_at=datetime.now().isoformat(),
            )

        logger.info(f"增量更新汇率数据，从 {start_date} 到 {latest_end}")

        exchange_data = await _fetch_exchange_rates(fred_service, start_date, latest_end)

        if not any(not series.empty for series in exchange_data.values()):
            raise Exception("未能获取到任何汇率新数据")

        # 保存汇率数据
        data_service.save_fred_data(exchange_data, key="exchange_rates")

        # 构建只包含汇率的响应数据
        latest_rates = {}
        for name, series in exchange_data.items():
            if not series.empty:
                last_idx = series.last_valid_index()
                if last_idx is not None:
                    latest_rates[name] = {"date": last_idx.strftime("%Y-%m-%d"), "value": float(series[last_idx])}

        dollar_index = latest_rates.get("dollar_index", ExchangeRateData(date=latest_end.date(), value=None))
        usd_cny = latest_rates.get("usd_cny", ExchangeRateData(date=latest_end.date(), value=None))
        usd_jpy = latest_rates.get("usd_jpy", ExchangeRateData(date=latest_end.date(), value=None))
        usd_eur = latest_rates.get("usd_eur", ExchangeRateData(date=latest_end.date(), value=None))

        response_data = ExchangeRatesUpdateData(
            exchange_rates=ExchangeRates(
                dollar_index=dollar_index,
                usd_cny=usd_cny,
                usd_jpy=usd_jpy,
                usd_eur=usd_eur,
            )
        )

        logger.info("汇率数据增量更新成功")
        return UpdateResponse(
            success=True,
            message="汇率数据增量更新成功",
            data=response_data,
            updated_at=datetime.now().isoformat(),
        )

    except Exception as e:
        logger.error(f"汇率数据增量更新失败: {str(e)}")
        return UpdateResponse(
            success=False,
            message=f"汇率数据增量更新失败: {str(e)}",
            error_code="UPDATE_FAILED"
        )
    finally:
        release_update_lock()




@router.post("/fetch/eu-bonds/history", response_model=UpdateResponse)
async def fetch_eu_bonds_history():
    """获取欧洲（德国）国债历史数据接口 - 从 2000 年开始获取全部历史数据"""
    global _is_updating

    if _is_updating:
        return UpdateResponse(
            success=False,
            message="数据更新正在进行中，请稍后再试",
            error_code="UPDATE_IN_PROGRESS"
        )

    await acquire_update_lock()

    try:
        logger.info("开始获取欧洲国债历史数据...")
        fred_service = get_fred_service()
        data_service = get_data_service()

        latest_end = pd.Timestamp.now().normalize()
        start_date = pd.Timestamp(settings.historical_start_date)

        logger.info(f"获取欧债历史数据，从 {start_date} 到 {latest_end}")

        eu_data = await _fetch_oecd_bonds(fred_service, start_date, latest_end)
        eu_only = {k: v for k, v in eu_data.items() if k.startswith("eu_")}

        if not any(not series.empty for series in eu_only.values()):
            raise Exception("未能获取到任何欧债数据")

        data_service.save_fred_data(eu_only)

        latest = {}
        for name, series in eu_only.items():
            if not series.empty:
                last_idx = series.last_valid_index()
                if last_idx is not None:
                    latest[name] = {"date": last_idx.strftime("%Y-%m-%d"), "value": float(series[last_idx])}

        eu_m3 = latest.get("eu_3m", TreasuryData(date=latest_end.date(), value=None))
        eu_y2 = latest.get("eu_2y_ecb", TreasuryData(date=latest_end.date(), value=None))
        eu_y10 = latest.get("eu_10y", TreasuryData(date=latest_end.date(), value=None))

        response_data = EUTreasuriesUpdateData(
            eu_treasuries=EUTreasuries(m3=eu_m3, y2=eu_y2, y10=eu_y10)
        )

        logger.info("欧洲国债历史数据获取成功")
        return UpdateResponse(
            success=True,
            message="欧洲国债历史数据获取成功",
            data=response_data,
            updated_at=datetime.now().isoformat(),
        )

    except Exception as e:
        logger.error(f"获取欧洲国债历史数据失败: {str(e)}")
        return UpdateResponse(
            success=False,
            message=f"获取欧洲国债历史数据失败: {str(e)}",
            error_code="UPDATE_FAILED"
        )
    finally:
        release_update_lock()


@router.post("/update/eu-bonds", response_model=UpdateResponse)
async def update_eu_bonds():
    """更新欧洲国债数据接口 - 增量更新最近 365 天的数据"""
    global _is_updating

    if _is_updating:
        return UpdateResponse(
            success=False,
            message="数据更新正在进行中，请稍后再试",
            error_code="UPDATE_IN_PROGRESS"
        )

    await acquire_update_lock()

    try:
        logger.info("开始增量更新欧洲国债数据...")
        fred_service = get_fred_service()
        data_service = get_data_service()

        latest_end = pd.Timestamp.now().normalize()
        start_date = (latest_end - pd.Timedelta(days=365)).normalize()

        logger.info(f"增量更新欧债数据，从 {start_date} 到 {latest_end}")

        eu_data = await _fetch_oecd_bonds(fred_service, start_date, latest_end)
        eu_only = {k: v for k, v in eu_data.items() if k.startswith("eu_")}

        if not any(not series.empty for series in eu_only.values()):
            raise Exception("未能获取到任何欧债新数据")

        data_service.save_fred_data(eu_only)

        latest = {}
        for name, series in eu_only.items():
            if not series.empty:
                last_idx = series.last_valid_index()
                if last_idx is not None:
                    latest[name] = {"date": last_idx.strftime("%Y-%m-%d"), "value": float(series[last_idx])}

        eu_m3 = latest.get("eu_3m", TreasuryData(date=latest_end.date(), value=None))
        eu_y2 = latest.get("eu_2y_ecb", TreasuryData(date=latest_end.date(), value=None))
        eu_y10 = latest.get("eu_10y", TreasuryData(date=latest_end.date(), value=None))

        response_data = EUTreasuriesUpdateData(
            eu_treasuries=EUTreasuries(m3=eu_m3, y2=eu_y2, y10=eu_y10)
        )

        logger.info("欧洲国债数据增量更新成功")
        return UpdateResponse(
            success=True,
            message="欧洲国债数据增量更新成功",
            data=response_data,
            updated_at=datetime.now().isoformat(),
        )

    except Exception as e:
        logger.error(f"欧洲国债数据增量更新失败: {str(e)}")
        return UpdateResponse(
            success=False,
            message=f"欧洲国债数据增量更新失败: {str(e)}",
            error_code="UPDATE_FAILED"
        )
    finally:
        release_update_lock()


@router.post("/fetch/jp-bonds/history", response_model=UpdateResponse)
async def fetch_jp_bonds_history():
    """获取日本国债历史数据接口 - 从 2000 年开始获取全部历史数据"""
    global _is_updating

    if _is_updating:
        return UpdateResponse(
            success=False,
            message="数据更新正在进行中，请稍后再试",
            error_code="UPDATE_IN_PROGRESS"
        )

    await acquire_update_lock()

    try:
        logger.info("开始获取日本国债历史数据...")
        fred_service = get_fred_service()
        data_service = get_data_service()

        latest_end = pd.Timestamp.now().normalize()
        start_date = pd.Timestamp(settings.historical_start_date)

        logger.info(f"获取日债历史数据，从 {start_date} 到 {latest_end}")

        jp_data = await _fetch_oecd_bonds(fred_service, start_date, latest_end)
        jp_only = {k: v for k, v in jp_data.items() if k.startswith("jp_")}

        if not any(not series.empty for series in jp_only.values()):
            raise Exception("未能获取到任何日债数据")

        data_service.save_fred_data(jp_only)

        latest = {}
        for name, series in jp_only.items():
            if not series.empty:
                last_idx = series.last_valid_index()
                if last_idx is not None:
                    latest[name] = {"date": last_idx.strftime("%Y-%m-%d"), "value": float(series[last_idx])}

        jp_y10 = latest.get("jp_10y", TreasuryData(date=latest_end.date(), value=None))

        response_data = JPTreasuriesUpdateData(
            jp_treasuries=JPTreasuries(y10=jp_y10)
        )

        logger.info("日本国债历史数据获取成功")
        return UpdateResponse(
            success=True,
            message="日本国债历史数据获取成功",
            data=response_data,
            updated_at=datetime.now().isoformat(),
        )

    except Exception as e:
        logger.error(f"获取日本国债历史数据失败: {str(e)}")
        return UpdateResponse(
            success=False,
            message=f"获取日本国债历史数据失败: {str(e)}",
            error_code="UPDATE_FAILED"
        )
    finally:
        release_update_lock()


@router.post("/update/jp-bonds", response_model=UpdateResponse)
async def update_jp_bonds():
    """更新日本国债数据接口 - 增量更新最近 365 天的数据"""
    global _is_updating

    if _is_updating:
        return UpdateResponse(
            success=False,
            message="数据更新正在进行中，请稍后再试",
            error_code="UPDATE_IN_PROGRESS"
        )

    await acquire_update_lock()

    try:
        logger.info("开始增量更新日本国债数据...")
        fred_service = get_fred_service()
        data_service = get_data_service()

        latest_end = pd.Timestamp.now().normalize()
        start_date = (latest_end - pd.Timedelta(days=365)).normalize()

        logger.info(f"增量更新日债数据，从 {start_date} 到 {latest_end}")

        jp_data = await _fetch_oecd_bonds(fred_service, start_date, latest_end)
        jp_only = {k: v for k, v in jp_data.items() if k.startswith("jp_")}

        if not any(not series.empty for series in jp_only.values()):
            raise Exception("未能获取到任何日债新数据")

        data_service.save_fred_data(jp_only)

        latest = {}
        for name, series in jp_only.items():
            if not series.empty:
                last_idx = series.last_valid_index()
                if last_idx is not None:
                    latest[name] = {"date": last_idx.strftime("%Y-%m-%d"), "value": float(series[last_idx])}

        jp_y10 = latest.get("jp_10y", TreasuryData(date=latest_end.date(), value=None))

        response_data = JPTreasuriesUpdateData(
            jp_treasuries=JPTreasuries(y10=jp_y10)
        )

        logger.info("日本国债数据增量更新成功")
        return UpdateResponse(
            success=True,
            message="日本国债数据增量更新成功",
            data=response_data,
            updated_at=datetime.now().isoformat(),
        )

    except Exception as e:
        logger.error(f"日本国债数据增量更新失败: {str(e)}")
        return UpdateResponse(
            success=False,
            message=f"日本国债数据增量更新失败: {str(e)}",
            error_code="UPDATE_FAILED"
        )
    finally:
        release_update_lock()

@router.post("/update", response_model=UpdateResponse)
async def update_data():
    """更新数据接口 - n8n 调用此接口触发数据更新（美债 + OECD债券 + 汇率）"""
    global _is_updating

    # 检查是否正在更新
    if _is_updating:
        return UpdateResponse(
            success=False,
            message="数据更新正在进行中，请稍后再试",
            error_code="UPDATE_IN_PROGRESS"
        )

    await acquire_update_lock()

    try:
        logger.info("开始更新数据...")
        fred_service = get_fred_service()
        data_service = get_data_service()

        latest_end = pd.Timestamp.now().normalize()

        # 检查美债数据的最后日期
        us_start = _compute_incremental_start(data_service, "us_treasuries", latest_end)
        if us_start is None:
            logger.info(f"美债数据已是最新，无需更新（last_date={data_service.get_last_date('us_treasuries').strftime('%Y-%m-%d')}）")
        else:
            logger.info(f"美债增量更新，从 {us_start} 到 {latest_end}")

        # OECD 数据使用 365 天范围
        oecd_start = (latest_end - pd.Timedelta(days=365)).normalize()
        logger.info(f"获取 OECD 债券数据范围: {oecd_start} 到 {latest_end}")

        # 汇率数据也使用增量更新策略
        er_start = _compute_incremental_start(data_service, "exchange_rates", latest_end)
        if er_start is None:
            logger.info(f"汇率数据已是最新，无需更新（last_date={data_service.get_last_date('exchange_rates').strftime('%Y-%m-%d')}）")
        else:
            logger.info(f"汇率增量更新，从 {er_start} 到 {latest_end}")

        new_data = {}
        exchange_data = {}

        # 获取美国国债数据（3m, 2y, 10y）— 数据已是最新时跳过
        if us_start is not None:
            us_data = await _fetch_us_treasuries(fred_service, us_start, latest_end)
            new_data.update(us_data)

        # 获取 OECD 数据（德国、日本 10y）
        oecd_data = await _fetch_oecd_bonds(fred_service, oecd_start, latest_end)
        new_data.update(oecd_data)

        # 获取汇率数据 — 数据已是最新时跳过
        if er_start is not None:
            exchange_data = await _fetch_exchange_rates(fred_service, er_start, latest_end)

        if not new_data and not exchange_data:
            raise Exception("未能获取到任何新数据")

        # 保存债券数据
        if new_data:
            data_service.save_fred_data(new_data)

        # 保存汇率数据
        if exchange_data:
            data_service.save_fred_data(exchange_data, key="exchange_rates")

        # 构建包含汇率的响应数据
        response_data = _build_response_data_with_rates(new_data, exchange_data, latest_end)

        logger.info("数据更新成功")
        return UpdateResponse(
            success=True,
            message="数据更新成功",
            data=response_data,
            updated_at=datetime.now().isoformat(),
        )

    except Exception as e:
        logger.error(f"数据更新失败: {str(e)}")
        return UpdateResponse(
            success=False,
            message=f"数据更新失败: {str(e)}",
            error_code="UPDATE_FAILED"
        )
    finally:
        release_update_lock()


@router.get("/data", response_model=DataResponse)
def get_data(
    response: Response,
    start_date: Optional[str] = Query(None, description="起始日期 (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="结束日期 (YYYY-MM-DD)"),
):
    """查询数据接口 - 前端调用此接口获取展示数据

    改 def（非 async def）：FastAPI 自动丢线程池跑同步 handler，
    避免 pandas 读 12 个 CSV 阻塞事件循环（之前 async + 同步阻塞
    会让 /signal /months /health 全部排队）。
    数据日更，HTTP 缓存 5 分钟安全：浏览器/代理可命中磁盘缓存，
    免去 localStorage TTL 过期后每次重拉几 MB JSON。
    前端手动刷新（refreshKey>0）配 fetch cache:'reload' 绕过。
    """
    try:
        logger.info(f"查询数据: start_date={start_date}, end_date={end_date}")
        data_service = get_data_service()

        data = data_service.query_data(start_date, end_date)

        logger.info("数据查询成功")
        response.headers["Cache-Control"] = "public, max-age=300"
        return DataResponse(success=True, message="数据查询成功", data=data)

    except Exception as e:
        logger.error(f"数据查询失败: {str(e)}")
        return DataResponse(
            success=False,
            message=f"数据查询失败: {str(e)}",
            error_code="QUERY_FAILED"
        )


@router.get("/data/{tab}", response_model=DataResponse)
def get_data_by_tab(
    tab: str,
    start_date: Optional[str] = Query(None, description="起始日期 (YYYY-MM-DD)，缺省为 historical_start_date"),
    end_date: Optional[str] = Query(None, description="结束日期 (YYYY-MM-DD)，缺省为今日"),
    indicators: Optional[str] = Query(None, description="对比页必填，逗号分隔的指标 id"),
):
    """按 Tab 查询数据 — 只加载并返回该 Tab 相关字段（全历史，供前端本地切时间周期）

    改 def（非 async def）：与 GET /data 一样丢线程池，避免同步 pandas 堵事件循环。
    tab=comparison 必须带 indicators；其它 tab 带 indicators 返回 400。
    """
    from src.services.data_service import VALID_DATA_TABS

    if tab not in VALID_DATA_TABS:
        raise HTTPException(
            status_code=400,
            detail=f"无效的 tab: {tab}，可选: {', '.join(sorted(VALID_DATA_TABS))}",
        )

    # 直接函数调用(测试)时默认值是 Query 对象而非 None(HTTP 路径 FastAPI 已解析成真值)→ 归一化
    if not isinstance(indicators, str):
        indicators = None

    if tab == "comparison":
        ids = [x.strip() for x in (indicators or "").split(",") if x.strip()]
        if not ids:
            raise HTTPException(
                status_code=400,
                detail="comparison 必须提供 indicators 参数（逗号分隔的指标 id）",
            )
    elif indicators:
        raise HTTPException(
            status_code=400,
            detail="仅 comparison tab 接受 indicators 参数",
        )

    try:
        logger.info(
            f"按 Tab 查询数据: tab={tab}, start_date={start_date}, "
            f"end_date={end_date}, indicators={indicators}"
        )
        data_service = get_data_service()
        if tab == "comparison":
            data = data_service.query_data_by_indicators(ids, start_date, end_date)
        else:
            data = data_service.query_data_by_tab(tab, start_date, end_date)
        return DataResponse(success=True, message="数据查询成功", data=data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"按 Tab 查询数据失败: {str(e)}")
        return DataResponse(
            success=False,
            message=f"数据查询失败: {str(e)}",
            error_code="QUERY_FAILED",
        )


@router.get("/health", response_model=HealthResponse)
def health_check():
    """健康检查接口

    改 def：循环读 11 个 CSV，同 /data 性质，且是 docker healthcheck
    周期调用的端点，阻塞事件循环会拖累监控。FastAPI 线程池自动承载。
    """
    try:
        data_service = get_data_service()

        # 获取最后更新时间
        last_updates = {}
        for data_type in ["us_treasuries", "eu_bonds", "jp_bonds", "exchange_rates", "vix", "fund_flow", "china_bond", "ted_spread", "indices", "tga", "hibor", "dr007", "volume", "turnover", "margin"]:
            last_date = data_service.get_last_date(data_type)
            if last_date:
                last_updates[data_type] = last_date.strftime("%Y-%m-%d")

        # 获取最新的更新时间
        last_update = None
        if last_updates:
            last_update = max(last_updates.values())

        return HealthResponse(
            status="healthy",
            service="macro",
            version="1.0.0",
            last_update=last_update,
        )

    except Exception as e:
        logger.error(f"健康检查失败: {str(e)}")
        return HealthResponse(
            status="unhealthy",
            service="macro",
            version="1.0.0",
            last_update=None,
        )


@router.post("/fetch/vix/history", response_model=UpdateResponse)
async def fetch_vix_history():
    """获取VIX历史数据接口 - 从 2000 年开始获取全部历史数据"""
    global _is_updating

    if _is_updating:
        return UpdateResponse(
            success=False,
            message="数据更新正在进行中，请稍后再试",
            error_code="UPDATE_IN_PROGRESS"
        )

    await acquire_update_lock()

    try:
        logger.info("开始获取VIX历史数据...")
        fred_service = get_fred_service()
        vix_service = get_vix_service()
        data_service = get_data_service()

        latest_end = pd.Timestamp.now().normalize()
        start_date = pd.Timestamp(settings.historical_start_date)

        logger.info(f"获取VIX历史数据，从 {start_date} 到 {latest_end}")

        # 获取VIX数据
        vix_code = settings.fred_codes.get("vix", "VIXCLS")
        vix_series = await fred_service.fetch_series(vix_code, start_date, latest_end)

        if vix_series.empty:
            raise Exception("未能获取到任何VIX数据")

        # 处理VIX数据：时区转换、验证、标准化
        # 注：update_tga / update_hibor / update_fund_flow / update_ted_spread 省略此三步，
        # 因为其数据源（HKMA / FRED WTREGEN / akshare / 阿里云）已是干净格式；
        # 如未来加新源也需评估是否需要这三步
        vix_series = vix_service.convert_timezone(vix_series)
        vix_series = vix_service.validate_data(vix_series)
        vix_series = vix_service.normalize_data(vix_series)

        # 保存VIX数据
        vix_data = {"vix": vix_series}
        data_service.save_fred_data(vix_data, key="vix")

        # 构建响应数据
        last_idx = vix_series.last_valid_index()
        vix_latest = VIXData(
            date=last_idx.date() if last_idx is not None else latest_end.date(),
            value=float(vix_series[last_idx]) if last_idx is not None else None
        )

        response_data = VIXUpdateData(vix=vix_latest)

        logger.info("VIX历史数据获取成功")
        return UpdateResponse(
            success=True,
            message="VIX历史数据获取成功",
            data=response_data,
            updated_at=datetime.now().isoformat(),
        )

    except Exception as e:
        logger.error(f"获取VIX历史数据失败: {str(e)}")
        return UpdateResponse(
            success=False,
            message=f"获取VIX历史数据失败: {str(e)}",
            error_code="UPDATE_FAILED"
        )
    finally:
        release_update_lock()


@router.post("/update/vix", response_model=UpdateResponse)
async def update_vix():
    """更新VIX数据接口 - 增量更新最近 7 天的数据"""
    global _is_updating

    if _is_updating:
        return UpdateResponse(
            success=False,
            message="数据更新正在进行中，请稍后再试",
            error_code="UPDATE_IN_PROGRESS"
        )

    await acquire_update_lock()

    try:
        logger.info("开始增量更新VIX数据...")
        fred_service = get_fred_service()
        vix_service = get_vix_service()
        data_service = get_data_service()

        latest_end = pd.Timestamp.now().normalize()
        start_date = _compute_incremental_start(data_service, "vix", latest_end)

        if start_date is None or start_date > latest_end:
            # 数据已是最新（或 CSV 已含今天数据），跳过本次更新
            logger.info("VIX数据已是最新，无需更新")
            return UpdateResponse(
                success=True,
                message="VIX数据已是最新，无需更新",
                data=VIXUpdateData(vix=VIXData(date=latest_end.date(), value=None)),
                updated_at=datetime.now().isoformat(),
            )

        logger.info(f"增量更新VIX数据，从 {start_date} 到 {latest_end}")

        # 获取VIX数据
        vix_code = settings.fred_codes.get("vix", "VIXCLS")
        vix_series = await fred_service.fetch_series(vix_code, start_date, latest_end)

        if vix_series.empty:
            raise Exception("未能获取到任何VIX新数据")

        # 处理VIX数据：时区转换、验证、标准化
        vix_series = vix_service.convert_timezone(vix_series)
        vix_series = vix_service.validate_data(vix_series)
        vix_series = vix_service.normalize_data(vix_series)

        # 保存VIX数据
        vix_data = {"vix": vix_series}
        data_service.save_fred_data(vix_data, key="vix")

        # 构建响应数据
        last_idx = vix_series.last_valid_index()
        vix_latest = VIXData(
            date=last_idx.date() if last_idx is not None else latest_end.date(),
            value=float(vix_series[last_idx]) if last_idx is not None else None
        )

        response_data = VIXUpdateData(vix=vix_latest)

        logger.info("VIX数据增量更新成功")
        return UpdateResponse(
            success=True,
            message="VIX数据增量更新成功",
            data=response_data,
            updated_at=datetime.now().isoformat(),
        )

    except Exception as e:
        logger.error(f"VIX数据增量更新失败: {str(e)}")
        return UpdateResponse(
            success=False,
            message=f"VIX数据增量更新失败: {str(e)}",
            error_code="UPDATE_FAILED"
        )
    finally:
        release_update_lock()


@router.post("/fetch/tga/history", response_model=UpdateResponse)
async def fetch_tga_history():
    """获取 TGA 账户余额历史数据接口 - 从 2000 年开始获取全部历史数据

    数据源：FRED WTREGEN（原始单位：百万美元）
    """
    global _is_updating

    if _is_updating:
        return UpdateResponse(
            success=False,
            message="数据更新正在进行中，请稍后再试",
            error_code="UPDATE_IN_PROGRESS"
        )

    await acquire_update_lock()

    try:
        logger.info("开始获取TGA历史数据...")
        fred_service = get_fred_service()
        data_service = get_data_service()

        latest_end = pd.Timestamp.now().normalize()
        start_date = pd.Timestamp(settings.historical_start_date)

        logger.info(f"获取TGA历史数据，从 {start_date} 到 {latest_end}")

        tga_code = settings.fred_codes.get("tga", "WTREGEN")
        tga_series = await fred_service.fetch_series(tga_code, start_date, latest_end)

        if tga_series.empty:
            raise Exception("未能获取到任何TGA数据")

        tga_data = {"tga": tga_series}
        data_service.save_fred_data(tga_data, key="tga")

        last_idx = tga_series.last_valid_index()
        tga_latest = TGAData(
            date=last_idx.date() if last_idx is not None else latest_end.date(),
            value=float(tga_series[last_idx]) if last_idx is not None else None
        )

        response_data = TGAUpdateData(tga=tga_latest)

        logger.info("TGA历史数据获取成功")
        return UpdateResponse(
            success=True,
            message="TGA历史数据获取成功",
            data=response_data,
            updated_at=datetime.now().isoformat(),
        )

    except Exception as e:
        logger.error(f"获取TGA历史数据失败: {str(e)}")
        return UpdateResponse(
            success=False,
            message=f"获取TGA历史数据失败: {str(e)}",
            error_code="UPDATE_FAILED"
        )
    finally:
        release_update_lock()


@router.post("/update/tga", response_model=UpdateResponse)
async def update_tga():
    """增量更新 TGA 账户余额数据 - 最近 7 天"""
    global _is_updating

    if _is_updating:
        return UpdateResponse(
            success=False,
            message="数据更新正在进行中，请稍后再试",
            error_code="UPDATE_IN_PROGRESS"
        )

    await acquire_update_lock()

    try:
        logger.info("开始增量更新TGA数据...")
        fred_service = get_fred_service()
        data_service = get_data_service()

        latest_end = pd.Timestamp.now().normalize()
        start_date = _compute_incremental_start(data_service, "tga", latest_end)

        if start_date is None or start_date > latest_end:
            # 数据已是最新（或 CSV 已含今天数据），跳过本次更新
            logger.info("TGA数据已是最新，无需更新")
            return UpdateResponse(
                success=True,
                message="TGA数据已是最新，无需更新",
                data=TGAUpdateData(tga=TGAData(date=latest_end.date(), value=None)),
                updated_at=datetime.now().isoformat(),
            )

        logger.info(f"增量更新TGA数据，从 {start_date} 到 {latest_end}")

        tga_code = settings.fred_codes.get("tga", "WTREGEN")
        tga_series = await fred_service.fetch_series(tga_code, start_date, latest_end)

        if tga_series.empty:
            raise Exception("未能获取到任何TGA新数据")

        tga_data = {"tga": tga_series}
        data_service.save_fred_data(tga_data, key="tga")

        last_idx = tga_series.last_valid_index()
        tga_latest = TGAData(
            date=last_idx.date() if last_idx is not None else latest_end.date(),
            value=float(tga_series[last_idx]) if last_idx is not None else None
        )

        response_data = TGAUpdateData(tga=tga_latest)

        logger.info("TGA数据增量更新成功")
        return UpdateResponse(
            success=True,
            message="TGA数据增量更新成功",
            data=response_data,
            updated_at=datetime.now().isoformat(),
        )

    except Exception as e:
        logger.error(f"TGA数据增量更新失败: {str(e)}")
        return UpdateResponse(
            success=False,
            message=f"TGA数据增量更新失败: {str(e)}",
            error_code="UPDATE_FAILED"
        )
    finally:
        release_update_lock()


@router.post("/fetch/hibor/history", response_model=UpdateResponse)
async def fetch_hibor_history():
    """获取 HIBOR 隔夜拆息历史数据接口 - 从 2000 年开始获取全部历史数据

    数据源：HKMA 公开 API
    """
    global _is_updating

    if _is_updating:
        return UpdateResponse(
            success=False,
            message="数据更新正在进行中，请稍后再试",
            error_code="UPDATE_IN_PROGRESS"
        )

    await acquire_update_lock()

    try:
        logger.info("开始获取HIBOR历史数据...")
        hibor_service = get_hibor_service()
        data_service = get_data_service()

        latest_end = pd.Timestamp.now().normalize()
        start_date = pd.Timestamp(settings.historical_start_date)

        logger.info(f"获取HIBOR历史数据，从 {start_date} 到 {latest_end}")

        hibor_series = await hibor_service.fetch_series(start_date, latest_end)

        if hibor_series.empty:
            raise Exception("未能获取到任何HIBOR数据")

        hibor_data = {"hibor": hibor_series}
        data_service.save_fred_data(hibor_data, key="hibor")

        last_idx = hibor_series.last_valid_index()
        hibor_latest = HIBORData(
            date=last_idx.date() if last_idx is not None else latest_end.date(),
            value=float(hibor_series[last_idx]) if last_idx is not None else None
        )

        response_data = HIBORUpdateData(hibor=hibor_latest)

        logger.info("HIBOR历史数据获取成功")
        return UpdateResponse(
            success=True,
            message="HIBOR历史数据获取成功",
            data=response_data,
            updated_at=datetime.now().isoformat(),
        )

    except Exception as e:
        logger.error(f"获取HIBOR历史数据失败: {str(e)}")
        return UpdateResponse(
            success=False,
            message=f"获取HIBOR历史数据失败: {str(e)}",
            error_code="UPDATE_FAILED"
        )
    finally:
        release_update_lock()


@router.post("/update/hibor", response_model=UpdateResponse)
async def update_hibor():
    """增量更新 HIBOR 隔夜拆息数据 - 最近 7 天"""
    global _is_updating

    if _is_updating:
        return UpdateResponse(
            success=False,
            message="数据更新正在进行中，请稍后再试",
            error_code="UPDATE_IN_PROGRESS"
        )

    await acquire_update_lock()

    try:
        logger.info("开始增量更新HIBOR数据...")
        hibor_service = get_hibor_service()
        data_service = get_data_service()

        latest_end = pd.Timestamp.now().normalize()
        start_date = _compute_incremental_start(data_service, "hibor", latest_end)

        if start_date is None or start_date > latest_end:
            # 数据已是最新（或 CSV 已含今天数据），跳过本次更新
            logger.info("HIBOR数据已是最新，无需更新")
            return UpdateResponse(
                success=True,
                message="HIBOR数据已是最新，无需更新",
                data=HIBORUpdateData(hibor=HIBORData(date=latest_end.date(), value=None)),
                updated_at=datetime.now().isoformat(),
            )

        logger.info(f"增量更新HIBOR数据，从 {start_date} 到 {latest_end}")

        hibor_series = await hibor_service.fetch_series(start_date, latest_end)

        if hibor_series.empty:
            raise Exception("未能获取到任何HIBOR新数据")

        hibor_data = {"hibor": hibor_series}
        data_service.save_fred_data(hibor_data, key="hibor")

        last_idx = hibor_series.last_valid_index()
        hibor_latest = HIBORData(
            date=last_idx.date() if last_idx is not None else latest_end.date(),
            value=float(hibor_series[last_idx]) if last_idx is not None else None
        )

        response_data = HIBORUpdateData(hibor=hibor_latest)

        logger.info("HIBOR数据增量更新成功")
        return UpdateResponse(
            success=True,
            message="HIBOR数据增量更新成功",
            data=response_data,
            updated_at=datetime.now().isoformat(),
        )

    except Exception as e:
        logger.error(f"HIBOR数据增量更新失败: {str(e)}")
        return UpdateResponse(
            success=False,
            message=f"HIBOR数据增量更新失败: {str(e)}",
            error_code="UPDATE_FAILED"
        )
    finally:
        release_update_lock()


@router.post("/fetch/fund-flow/history", response_model=UpdateResponse)
async def fetch_fund_flow_history():
    """获取资金流向历史数据接口 - 从 2014-11-17 开始获取全部历史数据"""
    global _is_updating

    if _is_updating:
        return UpdateResponse(
            success=False,
            message="数据更新正在进行中，请稍后再试",
            error_code="UPDATE_IN_PROGRESS"
        )

    await acquire_update_lock()

    try:
        logger.info("开始获取资金流向历史数据...")
        fund_flow_service = get_fund_flow_service()
        data_service = get_data_service()

        latest_end = pd.Timestamp.now().normalize()
        start_date = settings.fund_flow_start_date

        logger.info(f"获取资金流向历史数据，从 {start_date} 到 {latest_end}")

        # 获取资金流向数据
        fund_flow_data = fund_flow_service.fetch_all_fund_flow(start_date, latest_end.strftime("%Y-%m-%d"))

        if not any(not df.empty for df in fund_flow_data.values()):
            raise Exception("未能获取到任何资金流向数据")

        # 保存资金流向数据
        data_service.save_fund_flow(fund_flow_data)

        # 构建响应数据
        latest_north = None
        latest_south = None

        if "north" in fund_flow_data and not fund_flow_data["north"].empty:
            last_idx = fund_flow_data["north"].last_valid_index()
            if last_idx is not None:
                row = fund_flow_data["north"].loc[last_idx]
                latest_north = FundFlowData(
                    date=last_idx.date(),
                    net_flow=float(row["net_flow"]) if pd.notna(row["net_flow"]) else None,
                    buy=float(row["buy"]) if pd.notna(row["buy"]) else None,
                    sell=float(row["sell"]) if pd.notna(row["sell"]) else None
                )

        if "south" in fund_flow_data and not fund_flow_data["south"].empty:
            last_idx = fund_flow_data["south"].last_valid_index()
            if last_idx is not None:
                row = fund_flow_data["south"].loc[last_idx]
                latest_south = FundFlowData(
                    date=last_idx.date(),
                    net_flow=float(row["net_flow"]) if pd.notna(row["net_flow"]) else None,
                    buy=float(row["buy"]) if pd.notna(row["buy"]) else None,
                    sell=float(row["sell"]) if pd.notna(row["sell"]) else None
                )

        # 如果没有数据，使用默认值
        if latest_north is None:
            latest_north = FundFlowData(date=latest_end.date())
        if latest_south is None:
            latest_south = FundFlowData(date=latest_end.date())

        response_data = FundFlowUpdateData(
            fund_flow=FundFlow(north=latest_north, south=latest_south)
        )

        logger.info("资金流向历史数据获取成功")
        return UpdateResponse(
            success=True,
            message="资金流向历史数据获取成功",
            data=response_data,
            updated_at=datetime.now().isoformat(),
        )

    except Exception as e:
        logger.error(f"获取资金流向历史数据失败: {str(e)}")
        return UpdateResponse(
            success=False,
            message=f"获取资金流向历史数据失败: {str(e)}",
            error_code="UPDATE_FAILED"
        )
    finally:
        release_update_lock()


@router.post("/update/fund-flow", response_model=UpdateResponse)
async def update_fund_flow():
    """更新资金流向数据接口 - 增量更新最近 7 天的数据"""
    global _is_updating

    if _is_updating:
        return UpdateResponse(
            success=False,
            message="数据更新正在进行中，请稍后再试",
            error_code="UPDATE_IN_PROGRESS"
        )

    await acquire_update_lock()

    try:
        logger.info("开始增量更新资金流向数据...")
        fund_flow_service = get_fund_flow_service()
        data_service = get_data_service()

        latest_end = pd.Timestamp.now().normalize()
        start_date = _compute_incremental_start(data_service, "fund_flow", latest_end)

        if start_date is None or start_date > latest_end:
            # 数据已是最新（或 CSV 已含今天数据），跳过本次更新
            logger.info("资金流向数据已是最新，无需更新")
            today = latest_end.date()
            return UpdateResponse(
                success=True,
                message="资金流向数据已是最新，无需更新",
                data=FundFlowUpdateData(
                    fund_flow=FundFlow(
                        north=FundFlowData(date=today),
                        south=FundFlowData(date=today),
                    )
                ),
                updated_at=datetime.now().isoformat(),
            )

        logger.info(f"增量更新资金流向数据，从 {start_date} 到 {latest_end}")

        # 获取资金流向数据
        fund_flow_data = fund_flow_service.fetch_all_fund_flow(start_date.strftime("%Y-%m-%d"), latest_end.strftime("%Y-%m-%d"))

        if not any(not df.empty for df in fund_flow_data.values()):
            raise Exception("未能获取到任何资金流向新数据")

        # 保存资金流向数据
        data_service.save_fund_flow(fund_flow_data)

        # 构建响应数据
        latest_north = None
        latest_south = None

        if "north" in fund_flow_data and not fund_flow_data["north"].empty:
            last_idx = fund_flow_data["north"].last_valid_index()
            if last_idx is not None:
                row = fund_flow_data["north"].loc[last_idx]
                latest_north = FundFlowData(
                    date=last_idx.date(),
                    net_flow=float(row["net_flow"]) if pd.notna(row["net_flow"]) else None,
                    buy=float(row["buy"]) if pd.notna(row["buy"]) else None,
                    sell=float(row["sell"]) if pd.notna(row["sell"]) else None
                )

        if "south" in fund_flow_data and not fund_flow_data["south"].empty:
            last_idx = fund_flow_data["south"].last_valid_index()
            if last_idx is not None:
                row = fund_flow_data["south"].loc[last_idx]
                latest_south = FundFlowData(
                    date=last_idx.date(),
                    net_flow=float(row["net_flow"]) if pd.notna(row["net_flow"]) else None,
                    buy=float(row["buy"]) if pd.notna(row["buy"]) else None,
                    sell=float(row["sell"]) if pd.notna(row["sell"]) else None
                )

        # 如果没有数据，使用默认值
        if latest_north is None:
            latest_north = FundFlowData(date=latest_end.date())
        if latest_south is None:
            latest_south = FundFlowData(date=latest_end.date())

        response_data = FundFlowUpdateData(
            fund_flow=FundFlow(north=latest_north, south=latest_south)
        )

        logger.info("资金流向数据增量更新成功")
        return UpdateResponse(
            success=True,
            message="资金流向数据增量更新成功",
            data=response_data,
            updated_at=datetime.now().isoformat(),
        )

    except Exception as e:
        logger.error(f"资金流向数据增量更新失败: {str(e)}")
        return UpdateResponse(
            success=False,
            message=f"资金流向数据增量更新失败: {str(e)}",
            error_code="UPDATE_FAILED"
        )
    finally:
        release_update_lock()


@router.get("/fund-flow/cumulative", response_model=FundFlowCumulativeResponse)
async def get_fund_flow_cumulative():
    """获取资金流向累计数据接口 - 北向/南向资金7日和30日累计净流入"""
    try:
        logger.info("获取资金流向累计数据...")
        fund_flow_service = get_fund_flow_service()

        cumulative_data = fund_flow_service.get_cumulative_flow_data()

        north_cum = FundFlowCumulativeData(
            date=cumulative_data["north_cumulative"]["date"],
            cum_7d=cumulative_data["north_cumulative"]["cum_7d"],
            cum_30d=cumulative_data["north_cumulative"]["cum_30d"]
        )
        south_cum = FundFlowCumulativeData(
            date=cumulative_data["south_cumulative"]["date"],
            cum_7d=cumulative_data["south_cumulative"]["cum_7d"],
            cum_30d=cumulative_data["south_cumulative"]["cum_30d"]
        )

        logger.info(
            f"北向资金累计: 7日={north_cum.cum_7d}亿元, 30日={north_cum.cum_30d}亿元; "
            f"南向资金累计: 7日={south_cum.cum_7d}亿元, 30日={south_cum.cum_30d}亿元"
        )

        return FundFlowCumulativeResponse(
            north_cumulative=north_cum,
            south_cumulative=south_cum
        )

    except Exception as e:
        logger.error(f"获取资金流向累计数据失败: {str(e)}")
        # 返回空数据而不是报错
        empty_cum = FundFlowCumulativeData(date=pd.Timestamp.now().date())
        return FundFlowCumulativeResponse(
            north_cumulative=empty_cum,
            south_cumulative=empty_cum
        )


@router.get("/fund-flow/history", response_model=FundFlowHistoryResponse)
async def get_fund_flow_history(
    start_date: Optional[str] = Query(None, description="起始日期 (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="结束日期 (YYYY-MM-DD)"),
):
    """获取资金流向历史数据接口 - 前端调用此接口获取图表展示数据"""
    try:
        logger.info(f"查询资金流向历史数据: start_date={start_date}, end_date={end_date}")
        data_service = get_data_service()

        # 加载资金流向数据
        fund_flow_data = data_service.load_data("fund_flow")

        if fund_flow_data.empty:
            logger.warning("资金流向数据为空")
            return FundFlowHistoryResponse(data=[])

        # 处理日期范围
        if end_date is None:
            end_date = pd.Timestamp.now().normalize()
        else:
            end_date = pd.Timestamp(end_date)

        if start_date is None:
            start_date = pd.Timestamp(settings.fund_flow_start_date)
        else:
            start_date = pd.Timestamp(start_date)

        # 筛选时间范围
        fund_flow_filtered = fund_flow_data[(fund_flow_data.index >= start_date) & (fund_flow_data.index <= end_date)]

        # 填充缺失值
        fund_flow_filtered = fund_flow_filtered.ffill()

        # 构建响应数据
        history_items = []
        col_mapping = {
            "北向净流入": "north_net",
            "北向买入": "north_buy",
            "北向卖出": "north_sell",
            "南向净流入": "south_net",
            "南向买入": "south_buy",
            "南向卖出": "south_sell"
        }

        for idx, row in fund_flow_filtered.iterrows():
            item = FundFlowHistoryItem(
                date=idx.strftime("%Y-%m-%d"),
                north_net=float(row["北向净流入"]) if pd.notna(row.get("北向净流入")) else None,
                north_buy=float(row["北向买入"]) if pd.notna(row.get("北向买入")) else None,
                north_sell=float(row["北向卖出"]) if pd.notna(row.get("北向卖出")) else None,
                south_net=float(row["南向净流入"]) if pd.notna(row.get("南向净流入")) else None,
                south_buy=float(row["南向买入"]) if pd.notna(row.get("南向买入")) else None,
                south_sell=float(row["南向卖出"]) if pd.notna(row.get("南向卖出")) else None,
            )
            history_items.append(item)

        logger.info(f"资金流向历史数据查询成功，共 {len(history_items)} 条记录")
        return FundFlowHistoryResponse(data=history_items)

    except Exception as e:
        logger.error(f"资金流向历史数据查询失败: {str(e)}")
        return FundFlowHistoryResponse(data=[])


@router.post("/fetch/china-bonds/history", response_model=UpdateResponse)
async def fetch_china_bonds_history():
    """获取中国国债历史数据接口 - 从配置的开始日期获取全部历史数据"""
    global _is_updating

    if _is_updating:
        return UpdateResponse(
            success=False,
            message="数据更新正在进行中，请稍后再试",
            error_code="UPDATE_IN_PROGRESS"
        )

    await acquire_update_lock()

    try:
        logger.info("开始获取中国国债历史数据...")
        china_bond_service = get_china_bond_service()
        data_service = get_data_service()

        latest_end = pd.Timestamp.now().normalize()
        start_date = settings.china_bond_start_date

        logger.info(f"获取中国国债历史数据，从 {start_date} 到 {latest_end}")

        # 获取中国国债收益率数据
        bond_df = china_bond_service.fetch_china_bond_yield(start_date, latest_end.strftime("%Y-%m-%d"))

        if bond_df.empty:
            raise Exception("未能获取到任何中国国债数据")

        # 保存中国国债数据（传短 key 让 _save_china_bond 自动加 "中国" 前缀）
        china_bond_data = {
            "10y": bond_df["中国国债收益率10年"],
            "10年-2年": bond_df["中国国债收益率10年-2年"],
        }
        data_service.save_china_bond_data(china_bond_data)

        # 构建响应数据
        col_10y = "中国国债收益率10年"
        last_idx = bond_df.index[-1]
        bond_10y_latest = ChinaBondData(
            date=last_idx.date(),
            value=float(bond_df[col_10y].iloc[-1]) if pd.notna(bond_df[col_10y].iloc[-1]) else None
        )

        response_data = ChinaBondUpdateData(china_bond_10y=bond_10y_latest)

        logger.info("中国国债历史数据获取成功")
        return UpdateResponse(
            success=True,
            message="中国国债历史数据获取成功",
            data=response_data,
            updated_at=datetime.now().isoformat(),
        )

    except Exception as e:
        logger.error(f"获取中国国债历史数据失败: {str(e)}")
        return UpdateResponse(
            success=False,
            message=f"获取中国国债历史数据失败: {str(e)}",
            error_code="UPDATE_FAILED"
        )
    finally:
        release_update_lock()


@router.post("/update/china-bonds", response_model=UpdateResponse)
async def update_china_bonds():
    """更新中国国债数据接口 - 增量更新最近 7 天的数据"""
    global _is_updating

    if _is_updating:
        return UpdateResponse(
            success=False,
            message="数据更新正在进行中，请稍后再试",
            error_code="UPDATE_IN_PROGRESS"
        )

    await acquire_update_lock()

    try:
        logger.info("开始增量更新中国国债数据...")
        china_bond_service = get_china_bond_service()
        data_service = get_data_service()

        latest_end = pd.Timestamp.now().normalize()
        # 复用现有 helper：跟 us_treasuries / exchange_rates 一致，避免数据落后超过 7 天时出 gap
        start_date = _compute_incremental_start(data_service, "china_bond", latest_end)

        if start_date is None or start_date >= latest_end:
            # 数据已是最新（或 last_date+1 == today 但 ak 接口今天还没发数据），跳过本次更新
            logger.info("中国国债数据已是最新，跳过本次更新")
            response_data = ChinaBondUpdateData(
                china_bond_10y=ChinaBondData(date=latest_end.date(), value=None)
            )
            return UpdateResponse(
                success=True,
                message="中国国债数据已是最新，无需更新",
                data=response_data,
                updated_at=datetime.now().isoformat(),
            )

        logger.info(f"增量更新中国国债数据，从 {start_date} 到 {latest_end}")

        # 获取中国国债收益率数据
        bond_df = china_bond_service.fetch_china_bond_yield(start_date.strftime("%Y-%m-%d"), latest_end.strftime("%Y-%m-%d"))

        if bond_df.empty:
            raise Exception("未能获取到任何中国国债新数据")

        # 保存中国国债数据（传短 key 让 _save_china_bond 自动加 "中国" 前缀）
        china_bond_data = {
            "10y": bond_df["中国国债收益率10年"],
            "10年-2年": bond_df["中国国债收益率10年-2年"],
        }
        data_service.save_china_bond_data(china_bond_data)

        # 构建响应数据
        col_10y = "中国国债收益率10年"
        last_idx = bond_df.index[-1]
        bond_10y_latest = ChinaBondData(
            date=last_idx.date(),
            value=float(bond_df[col_10y].iloc[-1]) if pd.notna(bond_df[col_10y].iloc[-1]) else None
        )

        response_data = ChinaBondUpdateData(china_bond_10y=bond_10y_latest)

        logger.info("中国国债数据增量更新成功")
        return UpdateResponse(
            success=True,
            message="中国国债数据增量更新成功",
            data=response_data,
            updated_at=datetime.now().isoformat(),
        )

    except Exception as e:
        logger.error(f"中国国债数据增量更新失败: {str(e)}")
        return UpdateResponse(
            success=False,
            message=f"中国国债数据增量更新失败: {str(e)}",
            error_code="UPDATE_FAILED"
        )
    finally:
        release_update_lock()


@router.post("/fetch/ted-spread/history", response_model=UpdateResponse)
async def fetch_ted_spread_history():
    """获取TED利差历史数据接口 - 从 20120101 开始获取全部历史数据"""
    global _is_updating

    if _is_updating:
        return UpdateResponse(
            success=False,
            message="数据更新正在进行中，请稍后再试",
            error_code="UPDATE_IN_PROGRESS"
        )

    await acquire_update_lock()

    try:
        logger.info("开始获取TED利差历史数据...")
        fred_service = get_fred_service()
        data_service = get_data_service()

        latest_end = pd.Timestamp.now().normalize()
        # TED利差数据从2012年开始（SOFR的历史数据从2018年，但FRED有从2012年的）
        start_date = pd.Timestamp("2012-01-01")

        logger.info(f"获取TED利差历史数据，从 {start_date} 到 {latest_end}")

        # 获取SOFR数据
        sofr_code = settings.fred_codes.get("sofr", "SOFR")
        sofr_series = await fred_service.fetch_series(sofr_code, start_date, latest_end)

        # 获取3个月美债数据
        us_3m_code = settings.fred_codes.get("us_3m", "DGS3MO")
        us_3m_series = await fred_service.fetch_series(us_3m_code, start_date, latest_end)

        if sofr_series.empty and us_3m_series.empty:
            raise Exception("未能获取到任何TED利差数据")

        # 保存TED利差数据
        data_service.save_ted_spread_data(sofr_series, us_3m_series)

        # 构建响应数据
        # 使用SOFR的最后有效日期作为参考
        sofr_last_idx = sofr_series.last_valid_index() if not sofr_series.empty else None
        us_3m_last_idx = us_3m_series.last_valid_index() if not us_3m_series.empty else None

        if sofr_last_idx is None and us_3m_last_idx is None:
            raise Exception("未能获取到任何有效TED利差数据")

        # 使用较新的日期
        last_idx = sofr_last_idx if sofr_last_idx else us_3m_last_idx
        sofr_val = float(sofr_series[last_idx]) if sofr_last_idx and pd.notna(sofr_series[sofr_last_idx]) else None
        us_3m_val = float(us_3m_series[last_idx]) if us_3m_last_idx and pd.notna(us_3m_series[us_3m_last_idx]) else None
        ted_val = (sofr_val - us_3m_val) if sofr_val is not None and us_3m_val is not None else None

        response_data = TedSpreadUpdateData(
            ted_spread=TedSpreadData(
                date=last_idx.date() if last_idx else latest_end.date(),
                sofr=sofr_val,
                us_3m=us_3m_val,
                ted_spread=ted_val
            )
        )

        logger.info("TED利差历史数据获取成功")
        return UpdateResponse(
            success=True,
            message="TED利差历史数据获取成功",
            data=response_data,
            updated_at=datetime.now().isoformat(),
        )

    except Exception as e:
        logger.error(f"获取TED利差历史数据失败: {str(e)}")
        return UpdateResponse(
            success=False,
            message=f"获取TED利差历史数据失败: {str(e)}",
            error_code="UPDATE_FAILED"
        )
    finally:
        release_update_lock()


@router.post("/update/ted-spread", response_model=UpdateResponse)
async def update_ted_spread():
    """更新TED利差数据接口 - 增量更新最近 7 天的数据"""
    global _is_updating

    if _is_updating:
        return UpdateResponse(
            success=False,
            message="数据更新正在进行中，请稍后再试",
            error_code="UPDATE_IN_PROGRESS"
        )

    await acquire_update_lock()

    try:
        logger.info("开始增量更新TED利差数据...")
        fred_service = get_fred_service()
        data_service = get_data_service()

        latest_end = pd.Timestamp.now().normalize()
        start_date = _compute_incremental_start(data_service, "ted_spread", latest_end)

        if start_date is None or start_date > latest_end:
            # 数据已是最新（或 CSV 已含今天数据），跳过本次更新
            logger.info("TED利差数据已是最新，无需更新")
            return UpdateResponse(
                success=True,
                message="TED利差数据已是最新，无需更新",
                data=TedSpreadUpdateData(
                    ted_spread=TedSpreadData(date=latest_end.date(), sofr=None, us_3m=None, ted_spread=None)
                ),
                updated_at=datetime.now().isoformat(),
            )

        logger.info(f"增量更新TED利差数据，从 {start_date} 到 {latest_end}")

        # 获取SOFR数据
        sofr_code = settings.fred_codes.get("sofr", "SOFR")
        sofr_series = await fred_service.fetch_series(sofr_code, start_date, latest_end)

        # 获取3个月美债数据
        us_3m_code = settings.fred_codes.get("us_3m", "DGS3MO")
        us_3m_series = await fred_service.fetch_series(us_3m_code, start_date, latest_end)

        if sofr_series.empty and us_3m_series.empty:
            raise Exception("未能获取到任何TED利差新数据")

        # 保存TED利差数据
        data_service.save_ted_spread_data(sofr_series, us_3m_series)

        # 构建响应数据
        sofr_last_idx = sofr_series.last_valid_index() if not sofr_series.empty else None
        us_3m_last_idx = us_3m_series.last_valid_index() if not us_3m_series.empty else None

        if sofr_last_idx is None and us_3m_last_idx is None:
            raise Exception("未能获取到任何有效TED利差数据")

        last_idx = sofr_last_idx if sofr_last_idx else us_3m_last_idx
        sofr_val = float(sofr_series[last_idx]) if sofr_last_idx and pd.notna(sofr_series[sofr_last_idx]) else None
        us_3m_val = float(us_3m_series[last_idx]) if us_3m_last_idx and pd.notna(us_3m_series[us_3m_last_idx]) else None
        ted_val = (sofr_val - us_3m_val) if sofr_val is not None and us_3m_val is not None else None

        response_data = TedSpreadUpdateData(
            ted_spread=TedSpreadData(
                date=last_idx.date() if last_idx else latest_end.date(),
                sofr=sofr_val,
                us_3m=us_3m_val,
                ted_spread=ted_val
            )
        )

        logger.info("TED利差数据增量更新成功")
        return UpdateResponse(
            success=True,
            message="TED利差数据增量更新成功",
            data=response_data,
            updated_at=datetime.now().isoformat(),
        )

    except Exception as e:
        logger.error(f"TED利差数据增量更新失败: {str(e)}")
        return UpdateResponse(
            success=False,
            message=f"TED利差数据增量更新失败: {str(e)}",
            error_code="UPDATE_FAILED"
        )
    finally:
        release_update_lock()


@router.post("/fetch/commodities/history", response_model=UpdateResponse)
async def fetch_commodities_history():
    """获取商品（黄金/白银/原油/铜）日 K 线 - comkm 历史接口拉 5 年全量

    comkm 是历史 K 线接口，4 个 symbol 单独翻页拉取。
    - 本接口：全量从 settings.commodity_history_years 年前到今天 → 写入 commodities.csv
      （首次部署 / 重建数据用）
    - 配合 /update/commodities 做日常增量
    """
    global _is_updating

    if _is_updating:
        return UpdateResponse(
            success=False,
            message="数据更新正在进行中，请稍后再试",
            error_code="UPDATE_IN_PROGRESS"
        )

    await acquire_update_lock()

    try:
        logger.info("开始获取商品历史 K 线（comkm 全量）...")
        commodity_service = get_commodity_service()
        data_service = get_data_service()

        latest_end = pd.Timestamp.now().normalize()
        start_date = (
            latest_end - pd.Timedelta(days=settings.commodity_history_years * 365)
        ).normalize()

        logger.info(
            f"获取商品历史，从 {start_date.strftime('%Y-%m-%d')} 到 {latest_end.strftime('%Y-%m-%d')}"
        )
        new_data = await commodity_service.fetch_all(start_date.date(), latest_end.date())

        if not new_data or all(s.empty for s in new_data.values()):
            raise Exception("未能获取到任何商品数据（阿里云 comkm 返回全空）")

        data_service.save_commodities(new_data)

        # 构造响应：取每个商品的最后一个有效值
        latest_per_commodity: dict = {}
        for name, series in new_data.items():
            if not series.empty:
                last_idx = series.last_valid_index()
                if last_idx is not None:
                    latest_per_commodity[name] = float(series[last_idx])

        response_data = CommoditiesUpdateData(
            commodities=CommoditiesData(
                date=latest_end.date(),
                gold=latest_per_commodity.get("gold"),
                silver=latest_per_commodity.get("silver"),
                oil=latest_per_commodity.get("oil"),
                copper=latest_per_commodity.get("copper"),
            )
        )

        logger.info("商品历史数据获取成功")
        return UpdateResponse(
            success=True,
            message="商品历史数据获取成功",
            data=response_data,
            updated_at=datetime.now().isoformat(),
        )

    except Exception as e:
        logger.error(f"获取商品历史数据失败: {str(e)}")
        return UpdateResponse(
            success=False,
            message=f"获取商品历史数据失败: {str(e)}",
            error_code="UPDATE_FAILED"
        )
    finally:
        release_update_lock()


@router.post("/update/commodities", response_model=UpdateResponse)
async def update_commodities():
    """增量更新商品日 K 线 - 从 CSV last_date+1 拉到今天

    配合 /fetch/commodities/history 做日常 daily 增量更新。
    """
    global _is_updating

    if _is_updating:
        return UpdateResponse(
            success=False,
            message="数据更新正在进行中，请稍后再试",
            error_code="UPDATE_IN_PROGRESS"
        )

    await acquire_update_lock()

    try:
        logger.info("开始增量更新商品 K 线...")
        commodity_service = get_commodity_service()
        data_service = get_data_service()

        latest_end = pd.Timestamp.now().normalize()
        start_date = _compute_incremental_start(data_service, "commodities", latest_end)

        if start_date is None:
            logger.info("商品数据已是最新")
            today = latest_end.date()
            return UpdateResponse(
                success=True,
                message="商品数据已是最新",
                data=CommoditiesUpdateData(
                    commodities=CommoditiesData(
                        date=today,
                        gold=None, silver=None, oil=None, copper=None,
                    )
                ),
                updated_at=datetime.now().isoformat(),
            )

        logger.info(
            f"增量更新商品，从 {start_date.strftime('%Y-%m-%d')} 到 {latest_end.strftime('%Y-%m-%d')}"
        )
        new_data = await commodity_service.fetch_all(start_date.date(), latest_end.date())

        if not new_data or all(s.empty for s in new_data.values()):
            raise Exception("未能获取到任何商品新数据")

        data_service.save_commodities(new_data)

        # 构造响应：取每个商品的最后一个有效值
        latest_per_commodity: dict = {}
        for name, series in new_data.items():
            if not series.empty:
                last_idx = series.last_valid_index()
                if last_idx is not None:
                    latest_per_commodity[name] = float(series[last_idx])

        response_data = CommoditiesUpdateData(
            commodities=CommoditiesData(
                date=latest_end.date(),
                gold=latest_per_commodity.get("gold"),
                silver=latest_per_commodity.get("silver"),
                oil=latest_per_commodity.get("oil"),
                copper=latest_per_commodity.get("copper"),
            )
        )

        logger.info("商品数据增量更新成功")
        return UpdateResponse(
            success=True,
            message="商品数据增量更新成功",
            data=response_data,
            updated_at=datetime.now().isoformat(),
        )

    except Exception as e:
        logger.error(f"商品数据增量更新失败: {str(e)}")
        return UpdateResponse(
            success=False,
            message=f"商品数据增量更新失败: {str(e)}",
            error_code="UPDATE_FAILED"
        )
    finally:
        release_update_lock()


@router.post("/fetch/indices/history", response_model=UpdateResponse)
async def fetch_indices_history():
    """获取全球股指（恒生/上证/标普500/纳指/道指）历史 K 线 - 5 年全量

    comkm 是历史 K 线接口，5 个 symbol 单独翻页拉取。
    - 本接口：全量从 5 年前到今天 → 写入 indices.csv（首次部署 / 重建数据用）
    - 配合 /update/indices 做日常增量
    """
    global _is_updating

    if _is_updating:
        return UpdateResponse(
            success=False,
            message="数据更新正在进行中，请稍后再试",
            error_code="UPDATE_IN_PROGRESS"
        )

    await acquire_update_lock()

    try:
        logger.info("开始获取股指历史 K 线（comkm 全量）...")
        index_service = get_index_service()
        data_service = get_data_service()

        latest_end = pd.Timestamp.now().normalize()
        # 5 年历史（够 5Y 时间范围用）
        start_date = (latest_end - pd.Timedelta(days=5 * 365)).normalize()

        logger.info(
            f"获取股指历史，从 {start_date.strftime('%Y-%m-%d')} 到 {latest_end.strftime('%Y-%m-%d')}"
        )
        new_data = await index_service.fetch_all(start_date.date(), latest_end.date())

        if not new_data or all(s.empty for s in new_data.values()):
            raise Exception("未能获取到任何股指数据（阿里云 comkm 返回全空）")

        data_service.save_indices(new_data)

        # 构造响应：取每个 symbol 的最后有效值
        latest_per_idx: dict = {}
        for name, series in new_data.items():
            if not series.empty:
                last_idx = series.last_valid_index()
                if last_idx is not None:
                    latest_per_idx[name] = float(series[last_idx])

        response_data = IndicesUpdateData(
            indices=IndicesData(
                date=latest_end.date(),
                HKHSI=latest_per_idx.get("HKHSI"),
                SH000001=latest_per_idx.get("SH000001"),
                SPX=latest_per_idx.get("SPX"),
                IXIC=latest_per_idx.get("IXIC"),
                DJI=latest_per_idx.get("DJI"),
            )
        )

        logger.info("股指历史数据获取成功")
        return UpdateResponse(
            success=True,
            message="股指历史数据获取成功",
            data=response_data,
            updated_at=datetime.now().isoformat(),
        )

    except Exception as e:
        logger.error(f"获取股指历史数据失败: {str(e)}")
        return UpdateResponse(
            success=False,
            message=f"获取股指历史数据失败: {str(e)}",
            error_code="UPDATE_FAILED"
        )
    finally:
        release_update_lock()


@router.post("/update/indices", response_model=UpdateResponse)
async def update_indices():
    """增量更新股指 K 线 - 从 CSV last_date+1 拉到今天

    配合 /fetch/indices/history 做日常 daily 增量更新。
    """
    global _is_updating

    if _is_updating:
        return UpdateResponse(
            success=False,
            message="数据更新正在进行中，请稍后再试",
            error_code="UPDATE_IN_PROGRESS"
        )

    await acquire_update_lock()

    try:
        logger.info("开始增量更新股指 K 线...")
        index_service = get_index_service()
        data_service = get_data_service()

        latest_end = pd.Timestamp.now().normalize()
        start_date = _compute_incremental_start(data_service, "indices", latest_end)

        if start_date is None:
            logger.info("股指数据已是最新")
            return UpdateResponse(
                success=True,
                message="股指数据已是最新",
                data=IndicesUpdateData(indices=IndicesData(date=latest_end.date())),
                updated_at=datetime.now().isoformat(),
            )

        logger.info(
            f"增量更新股指，从 {start_date.strftime('%Y-%m-%d')} 到 {latest_end.strftime('%Y-%m-%d')}"
        )
        new_data = await index_service.fetch_all(start_date.date(), latest_end.date())

        if not new_data or all(s.empty for s in new_data.values()):
            raise Exception("未能获取到任何股指新数据")

        data_service.save_indices(new_data)

        latest_per_idx: dict = {}
        for name, series in new_data.items():
            if not series.empty:
                last_idx = series.last_valid_index()
                if last_idx is not None:
                    latest_per_idx[name] = float(series[last_idx])

        response_data = IndicesUpdateData(
            indices=IndicesData(
                date=latest_end.date(),
                HKHSI=latest_per_idx.get("HKHSI"),
                SH000001=latest_per_idx.get("SH000001"),
                SPX=latest_per_idx.get("SPX"),
                IXIC=latest_per_idx.get("IXIC"),
                DJI=latest_per_idx.get("DJI"),
            )
        )

        logger.info("股指数据增量更新成功")
        return UpdateResponse(
            success=True,
            message="股指数据增量更新成功",
            data=response_data,
            updated_at=datetime.now().isoformat(),
        )

    except Exception as e:
        logger.error(f"股指数据增量更新失败: {str(e)}")
        return UpdateResponse(
            success=False,
            message=f"股指数据增量更新失败: {str(e)}",
            error_code="UPDATE_FAILED"
        )
    finally:
        release_update_lock()


# === 宏观信号 API ===

@router.get("/signal", response_model=MacroSignalResponse)
async def get_macro_signal(month: str = Query(..., description="月份 YYYY-MM")):
    """获取指定月份的宏观信号快照(6 维度)

    数据源:macro-fin-skill 各子 skill 的 macro_signal.json + risk_data.json
    缓存:5 分钟内存缓存
    """
    try:
        logger.info(f"查询宏观信号: month={month}")
        service = get_macro_signal_service()
        snapshot = service.get_snapshot(month)
        if snapshot is None:
            raise HTTPException(status_code=404, detail=f"No data for month {month}")
        return MacroSignalResponse(success=True, data=snapshot)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"查询宏观信号失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/months", response_model=MacroMonthsResponse)
async def get_macro_months():
    """获取当前可用的月份列表(降序)

    数据源:从各 skill JSON 的 data_date 推断可用月份
    """
    try:
        logger.info("查询可用月份列表")
        service = get_macro_signal_service()
        months = service.get_available_months()
        return MacroMonthsResponse(months=months)
    except Exception as e:
        logger.error(f"查询月份列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/daily-snapshot", response_model=DailySnapshotResponse)
def get_daily_snapshot(date: Optional[str] = Query(None, description="日期 YYYY-MM-DD;缺省按 15:00 规则取默认")):
    """获取日频快照(信号首页 · 日频模式:3 维度 7 指标)

    数据源:已落库的原始指标序列(dr007/汇率/TED/市场情绪),asof 取值。
    改 def（非 async def）：pandas 读 CSV 阻塞,FastAPI 丢线程池跑同步
    handler,避免阻塞事件循环(与 /data 路由同款理由)。
    """
    if date is not None:
        try:
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=400, detail=f"非法日期格式: {date},应为 YYYY-MM-DD")

    try:
        logger.info(f"查询日频快照: date={date or '(默认)'}")
        service = get_daily_snapshot_service()
        data = service.get_daily_snapshot(date)
        return DailySnapshotResponse(success=True, data=data)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"查询日频快照失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# === 宏观信号数据写入（agent 推送）===

class SkillUploadRequest(BaseModel):
    """agent 推送 macro-fin-skill JSON 的入参"""
    skill: str          # 子 skill 目录名（白名单）
    file: str           # macro_signal.json | risk_data.json（白名单）
    data: dict          # 该 skill 的原始 JSON 内容


def _verify_upload_token(token: str | None) -> None:
    """constant-time 校验推送 token；未配置或错误 → 401。"""
    expected = settings.macro_signal_upload_token
    if not expected:
        raise HTTPException(status_code=401, detail="upload token 未配置（MACRO_SIGNAL_UPLOAD_TOKEN）")
    if not token or not hmac.compare_digest(token, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")


@router.post("/signal/upload")
async def upload_skill_json(
    req: SkillUploadRequest,
    x_upload_token: str = Header(..., alias="X-Upload-Token"),
):
    """接收 macro-fin-skill agent 推送的 JSON，落盘到 MACRO_SIGNAL_DATA_DIR。

    鉴权：X-Upload-Token header（constant-time，未配置拒绝）。
    安全：skill/file 白名单防路径穿越。
    按月留存：旧文件覆盖前抢救归档 + 本次数据归档到 archive/<月>/，
    历史月可通过 GET /api/signal?month= 查询。
    对外路径：经 nginx 剥前缀为 /api/macro/signal/upload。
    """
    _verify_upload_token(x_upload_token)
    service = get_macro_signal_service()
    try:
        path, archived_month = service.save_skill_json(req.skill, req.file, req.data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    service.clear_cache()
    logger.info(f"agent 推送 skill={req.skill} file={req.file} archived_month={archived_month}")
    return {
        "success": True,
        "skill": req.skill,
        "file": req.file,
        "path": str(path),
        "bytes": path.stat().st_size,
        "archived_month": archived_month,
    }


@router.post("/fetch/dr007/history", response_model=UpdateResponse)
async def fetch_dr007_history():
    """获取 DR007（中国货币网7天质押式回购加权利率）历史数据接口

    数据源：中国货币网 prr-chrt.csv
    起始日期：settings.dr007_start_date（默认 2015-01-01）
    """
    global _is_updating

    if _is_updating:
        return UpdateResponse(
            success=False,
            message="数据更新正在进行中，请稍后再试",
            error_code="UPDATE_IN_PROGRESS"
        )

    await acquire_update_lock()

    try:
        logger.info("开始获取 DR007 历史数据...")
        dr007_service = get_dr007_service()
        data_service = get_data_service()

        latest_end = pd.Timestamp.now().normalize()
        start_date = pd.Timestamp(settings.dr007_start_date)

        logger.info(f"获取 DR007 历史数据，从 {start_date} 到 {latest_end}")

        dr007_df = await dr007_service.fetch_history(start_date, latest_end)

        if dr007_df.empty:
            raise Exception("未能获取到任何 DR007 数据")

        data_service.save_dr007_data(dr007_df)

        last_idx = dr007_df["date"].iloc[-1]
        last_val = dr007_df["dr007"].iloc[-1]
        dr007_latest = DR007Data(
            date=last_idx.date() if last_idx is not None else latest_end.date(),
            value=float(last_val) if last_val is not None else None,
        )

        response_data = DR007UpdateData(dr007=dr007_latest)

        logger.info("DR007 历史数据获取成功")
        return UpdateResponse(
            success=True,
            message="DR007 历史数据获取成功",
            data=response_data,
            updated_at=datetime.now().isoformat(),
        )

    except Exception as e:
        logger.error(f"获取 DR007 历史数据失败: {str(e)}")
        return UpdateResponse(
            success=False,
            message=f"获取 DR007 历史数据失败: {str(e)}",
            error_code="UPDATE_FAILED"
        )
    finally:
        release_update_lock()


@router.post("/update/dr007", response_model=UpdateResponse)
async def update_dr007():
    """增量更新 DR007 数据 - 拉取 CSV 最后一行的下一天到今天"""
    global _is_updating

    if _is_updating:
        return UpdateResponse(
            success=False,
            message="数据更新正在进行中，请稍后再试",
            error_code="UPDATE_IN_PROGRESS"
        )

    await acquire_update_lock()

    try:
        logger.info("开始增量更新 DR007 数据...")
        dr007_service = get_dr007_service()
        data_service = get_data_service()

        latest_end = pd.Timestamp.now().normalize()
        start_date = _compute_incremental_start(data_service, "dr007", latest_end)

        if start_date is None or start_date > latest_end:
            logger.info("DR007 数据已是最新，无需更新")
            return UpdateResponse(
                success=True,
                message="DR007 数据已是最新，无需更新",
                data=DR007UpdateData(dr007=DR007Data(date=latest_end.date(), value=None)),
                updated_at=datetime.now().isoformat(),
            )

        logger.info(f"增量更新 DR007 数据，从 {start_date} 到 {latest_end}")

        dr007_df = await dr007_service.fetch_latest(start_date, latest_end)

        if dr007_df.empty:
            # 货币网 CSV 在区间内无新数据（节假日 / 数据尚未发布）→ 视为已是最新，不抛错
            logger.info(f"DR007 区间 [{start_date}, {latest_end}] 无新数据，跳过")
            return UpdateResponse(
                success=True,
                message="DR007 数据已是最新，无需更新",
                data=DR007UpdateData(dr007=DR007Data(date=latest_end.date(), value=None)),
                updated_at=datetime.now().isoformat(),
            )

        data_service.save_dr007_data(dr007_df)

        last_idx = dr007_df["date"].iloc[-1]
        last_val = dr007_df["dr007"].iloc[-1]
        dr007_latest = DR007Data(
            date=last_idx.date() if last_idx is not None else latest_end.date(),
            value=float(last_val) if last_val is not None else None,
        )

        response_data = DR007UpdateData(dr007=dr007_latest)

        logger.info("DR007 数据增量更新成功")
        return UpdateResponse(
            success=True,
            message="DR007 数据增量更新成功",
            data=response_data,
            updated_at=datetime.now().isoformat(),
        )

    except Exception as e:
        logger.error(f"DR007 数据增量更新失败: {str(e)}")
        return UpdateResponse(
            success=False,
            message=f"DR007 数据增量更新失败: {str(e)}",
            error_code="UPDATE_FAILED"
        )
    finally:
        release_update_lock()


@router.post("/update/volume", response_model=UpdateResponse)
async def update_volume():
    """当日更新两市成交额（沪深交易所官方 API 当日点）

    适用调度：每个交易日盘后 16:30 触发。
    """
    global _is_updating

    if _is_updating:
        return UpdateResponse(
            success=False,
            message="数据更新正在进行中，请稍后再试",
            error_code="UPDATE_IN_PROGRESS",
        )

    await acquire_update_lock()

    try:
        logger.info("开始当日更新两市成交额...")
        volume_service = get_volume_service()
        data_service = get_data_service()

        result = await volume_service.fetch_today()

        if result["status"] == "failed":
            raise Exception(f"两市成交额获取失败: SSE={result.get('sse_amount_yi')} SZSE={result.get('szse_amount_yi')}")

        # 单值转 DataFrame（save_volume_data 要求 DataFrame 格式）
        df = pd.DataFrame({
            "date": [pd.Timestamp(result["date"])],
            "total_amount_yi": [result["total_amount_yi"]],
        })
        data_service.save_volume_data(df)

        volume_latest = VolumeData(
            date=pd.Timestamp(result["date"]).date(),
            value=float(result["total_amount_yi"]) if result["total_amount_yi"] is not None else None,
        )
        response_data = VolumeUpdateData(volume=volume_latest)

        logger.info(
            "两市成交额当日更新成功: date=%s, total=%.2f亿",
            result["date"], result["total_amount_yi"] or 0,
        )
        return UpdateResponse(
            success=True,
            message="两市成交额更新成功",
            data=response_data,
            updated_at=datetime.now().isoformat(),
        )

    except Exception as e:
        logger.error(f"两市成交额更新失败: {str(e)}")
        return UpdateResponse(
            success=False,
            message=f"两市成交额更新失败: {str(e)}",
            error_code="UPDATE_FAILED",
        )
    finally:
        release_update_lock()


@router.post("/update/turnover", response_model=UpdateResponse)
async def update_turnover():
    """当日更新两市换手率（沪深交易所官方 API 当日点）"""
    global _is_updating

    if _is_updating:
        return UpdateResponse(
            success=False,
            message="数据更新正在进行中，请稍后再试",
            error_code="UPDATE_IN_PROGRESS",
        )

    await acquire_update_lock()

    try:
        logger.info("开始当日更新两市换手率...")
        turnover_service = get_turnover_service()
        data_service = get_data_service()

        result = await turnover_service.fetch_today()

        if result["status"] == "failed":
            raise Exception(f"两市换手率获取失败: result={result}")

        df = pd.DataFrame({
            "date": [pd.Timestamp(result["date"])],
            "turnover_rate": [result["turnover_rate"]],
        })
        data_service.save_turnover_data(df)

        turnover_latest = TurnoverData(
            date=pd.Timestamp(result["date"]).date(),
            value=float(result["turnover_rate"]) if result["turnover_rate"] is not None else None,
        )
        response_data = TurnoverUpdateData(turnover=turnover_latest)

        logger.info(
            "两市换手率当日更新成功: date=%s, rate=%.4f%%",
            result["date"], result["turnover_rate"] or 0,
        )
        return UpdateResponse(
            success=True,
            message="两市换手率更新成功",
            data=response_data,
            updated_at=datetime.now().isoformat(),
        )

    except Exception as e:
        logger.error(f"两市换手率更新失败: {str(e)}")
        return UpdateResponse(
            success=False,
            message=f"两市换手率更新失败: {str(e)}",
            error_code="UPDATE_FAILED",
        )
    finally:
        release_update_lock()


@router.post("/update/margin", response_model=UpdateResponse)
async def update_margin():
    """当日更新融资余额（akshare 当日点，T-1 数据 09:45+ 可用）"""
    global _is_updating

    if _is_updating:
        return UpdateResponse(
            success=False,
            message="数据更新正在进行中，请稍后再试",
            error_code="UPDATE_IN_PROGRESS",
        )

    await acquire_update_lock()

    try:
        logger.info("开始当日更新融资余额...")
        margin_service = get_margin_service()
        data_service = get_data_service()

        result = margin_service.fetch_today()

        if result["status"] == "failed":
            raise Exception(f"融资余额获取失败: {result.get('error', 'unknown')}")

        df = pd.DataFrame({
            "date": [pd.Timestamp(result["date"])],
            "margin_balance_yi": [result["rzye"]],
        })
        data_service.save_margin_data(df)

        margin_latest = MarginData(
            date=pd.Timestamp(result["date"]).date(),
            value=float(result["rzye"]) if result["rzye"] is not None else None,
        )
        response_data = MarginUpdateData(margin=margin_latest)

        logger.info(
            "融资余额当日更新成功: date=%s, balance=%.2f亿",
            result["date"], result["rzye"] or 0,
        )
        return UpdateResponse(
            success=True,
            message="融资余额更新成功",
            data=response_data,
            updated_at=datetime.now().isoformat(),
        )

    except Exception as e:
        logger.error(f"融资余额更新失败: {str(e)}")
        return UpdateResponse(
            success=False,
            message=f"融资余额更新失败: {str(e)}",
            error_code="UPDATE_FAILED",
        )
    finally:
        release_update_lock()
