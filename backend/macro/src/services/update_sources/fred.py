"""Fred update preparation and four-stage adapters."""

from datetime import datetime

import pandas as pd

from src.models import (
    TedSpreadData,
    TedSpreadUpdateData,
    TGAData,
    TGAUpdateData,
    TreasuryData,
    UpdateResponse,
    USTreasuries,
    USTreasuriesUpdateData,
    VIXData,
    VIXUpdateData,
)
from src.services.update_pipeline import (
    NoNewData,
    UpdateContext,
    UpdateNoOp,
    UpdatePlan,
    UpdateStages,
)


def build_us_treasuries(context: UpdateContext) -> UpdatePlan:
    context.logger.info("开始增量更新美国国债数据...")
    fred_service = context.get_fred_service()
    data_service = context.get_data_service()
    latest_end = pd.Timestamp.now().normalize()
    us_start = context.compute_incremental_start(
        data_service, "us_treasuries", latest_end
    )
    if us_start is None:
        context.logger.info("美债数据已是最新，跳过本次更新")
        response_data = USTreasuriesUpdateData(
            us_treasuries=USTreasuries(
                m3=TreasuryData(date=latest_end.date(), value=None),
                y2=TreasuryData(date=latest_end.date(), value=None),
                y10=TreasuryData(date=latest_end.date(), value=None),
            )
        )
        raise UpdateNoOp(
            UpdateResponse(
                success=True,
                message="美债数据已是最新，无需更新",
                data=response_data,
                updated_at=datetime.now().isoformat(),
            )
        )
    context.logger.info(f"增量更新美债数据，从 {us_start} 到 {latest_end}")

    async def fetch():
        return await context.fetch_us_treasuries(fred_service, us_start, latest_end)

    def validate(new_data):
        if not context.has_observations(new_data):
            if context.empty_increment_is_current(data_service, "us_treasuries"):
                raise NoNewData()
            raise Exception(
                context.empty_increment_fail_message(
                    data_service, "us_treasuries", "美债"
                )
            )
        return new_data

    def build_payload(new_data):
        latest = {}
        for name, series in new_data.items():
            if not series.empty:
                last_idx = series.last_valid_index()
                if last_idx is not None:
                    latest[name] = {
                        "date": last_idx.strftime("%Y-%m-%d"),
                        "value": float(series[last_idx]),
                    }
        return USTreasuriesUpdateData(
            us_treasuries=USTreasuries(
                m3=latest.get(
                    "us_3m", TreasuryData(date=latest_end.date(), value=None)
                ),
                y2=latest.get(
                    "us_2y", TreasuryData(date=latest_end.date(), value=None)
                ),
                y10=latest.get(
                    "us_10y", TreasuryData(date=latest_end.date(), value=None)
                ),
            )
        )

    def on_no_data():
        context.logger.info("美债增量区间无新观测，底库已有 last_date，视为已是最新")
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

    return UpdatePlan(
        UpdateStages(fetch, validate, data_service.save_fred_data, build_payload),
        on_no_data=on_no_data,
    )


def build_vix(context: UpdateContext) -> UpdatePlan:
    context.logger.info("开始增量更新VIX数据...")
    fred_service = context.get_fred_service()
    vix_service = context.get_vix_service()
    data_service = context.get_data_service()
    latest_end = pd.Timestamp.now().normalize()
    start_date = context.compute_incremental_start(data_service, "vix", latest_end)
    if start_date is None or start_date > latest_end:
        context.logger.info("VIX数据已是最新，无需更新")
        raise UpdateNoOp(
            UpdateResponse(
                success=True,
                message="VIX数据已是最新，无需更新",
                data=VIXUpdateData(vix=VIXData(date=latest_end.date(), value=None)),
                updated_at=datetime.now().isoformat(),
            )
        )
    context.logger.info(f"增量更新VIX数据，从 {start_date} 到 {latest_end}")
    vix_code = context.settings.fred_codes.get("vix", "VIXCLS")

    async def fetch():
        return await fred_service.fetch_series(vix_code, start_date, latest_end)

    def validate(vix_series):
        if not context.has_observations(vix_series):
            if context.empty_increment_is_current(data_service, "vix"):
                raise NoNewData()
            raise Exception(
                context.empty_increment_fail_message(data_service, "vix", "VIX")
            )
        vix_series = vix_service.convert_timezone(vix_series)
        vix_series = vix_service.validate_data(vix_series)
        return vix_service.normalize_data(vix_series)

    def save(vix_series):
        data_service.save_fred_data({"vix": vix_series}, key="vix")

    def build_payload(vix_series):
        last_idx = vix_series.last_valid_index()
        return VIXUpdateData(
            vix=VIXData(
                date=last_idx.date() if last_idx is not None else latest_end.date(),
                value=float(vix_series[last_idx]) if last_idx is not None else None,
            )
        )

    def on_no_data():
        context.logger.info("VIX增量区间无新观测，底库已有 last_date，视为已是最新")
        return UpdateResponse(
            success=True,
            message="VIX数据已是最新，无需更新",
            data=VIXUpdateData(vix=VIXData(date=latest_end.date(), value=None)),
            updated_at=datetime.now().isoformat(),
        )

    return UpdatePlan(
        UpdateStages(fetch, validate, save, build_payload), on_no_data=on_no_data
    )


def build_tga(context: UpdateContext) -> UpdatePlan:
    context.logger.info("开始增量更新TGA数据...")
    fred_service = context.get_fred_service()
    data_service = context.get_data_service()
    latest_end = pd.Timestamp.now().normalize()
    start_date = context.compute_incremental_start(data_service, "tga", latest_end)
    if start_date is None or start_date > latest_end:
        context.logger.info("TGA数据已是最新，无需更新")
        raise UpdateNoOp(
            UpdateResponse(
                success=True,
                message="TGA数据已是最新，无需更新",
                data=TGAUpdateData(tga=TGAData(date=latest_end.date(), value=None)),
                updated_at=datetime.now().isoformat(),
            )
        )
    context.logger.info(f"增量更新TGA数据，从 {start_date} 到 {latest_end}")
    tga_code = context.settings.fred_codes.get("tga", "WTREGEN")

    async def fetch():
        return await fred_service.fetch_series(tga_code, start_date, latest_end)

    def validate(tga_series):
        if not context.has_observations(tga_series):
            if context.empty_increment_is_current(data_service, "tga"):
                raise NoNewData()
            raise Exception(
                context.empty_increment_fail_message(data_service, "tga", "TGA")
            )
        return tga_series

    def save(tga_series):
        data_service.save_fred_data({"tga": tga_series}, key="tga")

    def build_payload(tga_series):
        last_idx = tga_series.last_valid_index()
        return TGAUpdateData(
            tga=TGAData(
                date=last_idx.date() if last_idx is not None else latest_end.date(),
                value=float(tga_series[last_idx]) if last_idx is not None else None,
            )
        )

    def on_no_data():
        context.logger.info("TGA增量区间无新观测，底库已有 last_date，视为已是最新")
        return UpdateResponse(
            success=True,
            message="TGA数据已是最新，无需更新",
            data=TGAUpdateData(tga=TGAData(date=latest_end.date(), value=None)),
            updated_at=datetime.now().isoformat(),
        )

    return UpdatePlan(
        UpdateStages(fetch, validate, save, build_payload), on_no_data=on_no_data
    )


def build_ted_spread(context: UpdateContext) -> UpdatePlan:
    context.logger.info("开始增量更新TED利差数据...")
    fred_service = context.get_fred_service()
    data_service = context.get_data_service()
    latest_end = pd.Timestamp.now().normalize()
    start_date = context.compute_incremental_start(
        data_service, "ted_spread", latest_end
    )
    if start_date is None or start_date > latest_end:
        context.logger.info("TED利差数据已是最新，无需更新")
        raise UpdateNoOp(
            UpdateResponse(
                success=True,
                message="TED利差数据已是最新，无需更新",
                data=TedSpreadUpdateData(
                    ted_spread=TedSpreadData(
                        date=latest_end.date(), sofr=None, us_3m=None, ted_spread=None
                    )
                ),
                updated_at=datetime.now().isoformat(),
            )
        )
    context.logger.info(f"增量更新TED利差数据，从 {start_date} 到 {latest_end}")
    sofr_code = context.settings.fred_codes.get("sofr", "SOFR")
    us_3m_code = context.settings.fred_codes.get("us_3m", "DGS3MO")

    async def fetch():
        return {
            "sofr": await fred_service.fetch_series(sofr_code, start_date, latest_end),
            "us_3m": await fred_service.fetch_series(
                us_3m_code, start_date, latest_end
            ),
        }

    def validate(ted_payload):
        if not context.has_observations(ted_payload):
            if context.empty_increment_is_current(data_service, "ted_spread"):
                raise NoNewData()
            raise Exception(
                context.empty_increment_fail_message(
                    data_service, "ted_spread", "TED利差"
                )
            )
        return ted_payload

    def save(ted_payload):
        data_service.save_ted_spread_data(ted_payload["sofr"], ted_payload["us_3m"])

    def build_payload(ted_payload):
        sofr_series = ted_payload["sofr"]
        us_3m_series = ted_payload["us_3m"]
        sofr_last_idx = (
            sofr_series.last_valid_index() if not sofr_series.empty else None
        )
        us_3m_last_idx = (
            us_3m_series.last_valid_index() if not us_3m_series.empty else None
        )
        if sofr_last_idx is None and us_3m_last_idx is None:
            raise Exception("未能获取到任何有效TED利差数据")
        last_idx = sofr_last_idx if sofr_last_idx else us_3m_last_idx
        sofr_val = (
            float(sofr_series[last_idx])
            if sofr_last_idx and pd.notna(sofr_series[sofr_last_idx])
            else None
        )
        us_3m_val = (
            float(us_3m_series[last_idx])
            if us_3m_last_idx and pd.notna(us_3m_series[us_3m_last_idx])
            else None
        )
        return TedSpreadUpdateData(
            ted_spread=TedSpreadData(
                date=last_idx.date() if last_idx else latest_end.date(),
                sofr=sofr_val,
                us_3m=us_3m_val,
                ted_spread=sofr_val - us_3m_val
                if sofr_val is not None and us_3m_val is not None
                else None,
            )
        )

    def on_no_data():
        context.logger.info("TED利差增量区间无新观测，底库已有 last_date，视为已是最新")
        return UpdateResponse(
            success=True,
            message="TED利差数据已是最新，无需更新",
            data=TedSpreadUpdateData(
                ted_spread=TedSpreadData(
                    date=latest_end.date(), sofr=None, us_3m=None, ted_spread=None
                )
            ),
            updated_at=datetime.now().isoformat(),
        )

    return UpdatePlan(
        UpdateStages(fetch, validate, save, build_payload), on_no_data=on_no_data
    )
