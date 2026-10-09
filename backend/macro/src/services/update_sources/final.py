"""Final update preparation and four-stage adapters."""

from datetime import datetime

import pandas as pd

from src.models import (
    CommoditiesData,
    CommoditiesUpdateData,
    EUTreasuries,
    EUTreasuriesUpdateData,
    IndicesData,
    IndicesUpdateData,
    JPTreasuries,
    JPTreasuriesUpdateData,
    TreasuryData,
    UpdateResponse,
)
from src.services.update_pipeline import (
    NoNewData,
    UpdateContext,
    UpdateNoOp,
    UpdatePlan,
    UpdateStages,
)


def build_eu_bonds(context: UpdateContext) -> UpdatePlan:
    context.logger.info("开始增量更新欧洲国债数据...")
    fred_service = context.get_fred_service()
    data_service = context.get_data_service()
    latest_end = pd.Timestamp.now().normalize()
    start_date = (latest_end - pd.Timedelta(days=365)).normalize()
    context.logger.info(f"增量更新欧债数据，从 {start_date} 到 {latest_end}")

    async def fetch():
        return {
            key: series
            for key, series in (
                await context.fetch_oecd_bonds(fred_service, start_date, latest_end)
            ).items()
            if key.startswith("eu_")
        }

    def validate(eu_only):
        if not any((not series.empty for series in eu_only.values())):
            raise Exception("未能获取到任何欧债新数据")
        return eu_only

    def build_payload(eu_only):
        latest = {}
        for name, series in eu_only.items():
            if not series.empty:
                last_idx = series.last_valid_index()
                if last_idx is not None:
                    latest[name] = {
                        "date": last_idx.strftime("%Y-%m-%d"),
                        "value": float(series[last_idx]),
                    }
        return EUTreasuriesUpdateData(
            eu_treasuries=EUTreasuries(
                m3=latest.get(
                    "eu_3m", TreasuryData(date=latest_end.date(), value=None)
                ),
                y2=latest.get(
                    "eu_2y_ecb", TreasuryData(date=latest_end.date(), value=None)
                ),
                y10=latest.get(
                    "eu_10y", TreasuryData(date=latest_end.date(), value=None)
                ),
            )
        )

    return UpdatePlan(
        UpdateStages(fetch, validate, data_service.save_fred_data, build_payload)
    )


def build_jp_bonds(context: UpdateContext) -> UpdatePlan:
    context.logger.info("开始增量更新日本国债数据...")
    fred_service = context.get_fred_service()
    data_service = context.get_data_service()
    latest_end = pd.Timestamp.now().normalize()
    start_date = (latest_end - pd.Timedelta(days=365)).normalize()
    context.logger.info(f"增量更新日债数据，从 {start_date} 到 {latest_end}")

    async def fetch():
        return {
            key: series
            for key, series in (
                await context.fetch_oecd_bonds(fred_service, start_date, latest_end)
            ).items()
            if key.startswith("jp_")
        }

    def validate(jp_only):
        if not any((not series.empty for series in jp_only.values())):
            raise Exception("未能获取到任何日债新数据")
        return jp_only

    def build_payload(jp_only):
        latest = {}
        for name, series in jp_only.items():
            if not series.empty:
                last_idx = series.last_valid_index()
                if last_idx is not None:
                    latest[name] = {
                        "date": last_idx.strftime("%Y-%m-%d"),
                        "value": float(series[last_idx]),
                    }
        return JPTreasuriesUpdateData(
            jp_treasuries=JPTreasuries(
                y10=latest.get(
                    "jp_10y", TreasuryData(date=latest_end.date(), value=None)
                )
            )
        )

    return UpdatePlan(
        UpdateStages(fetch, validate, data_service.save_fred_data, build_payload)
    )


def build_legacy(context: UpdateContext) -> UpdatePlan:
    context.logger.info("开始更新数据...")
    fred_service = context.get_fred_service()
    data_service = context.get_data_service()
    latest_end = pd.Timestamp.now().normalize()
    us_start = context.compute_incremental_start(
        data_service, "us_treasuries", latest_end
    )
    if us_start is None:
        context.logger.info(
            f"美债数据已是最新，无需更新（last_date={data_service.get_last_date('us_treasuries').strftime('%Y-%m-%d')}）"
        )
    else:
        context.logger.info(f"美债增量更新，从 {us_start} 到 {latest_end}")
    oecd_start = (latest_end - pd.Timedelta(days=365)).normalize()
    context.logger.info(f"获取 OECD 债券数据范围: {oecd_start} 到 {latest_end}")
    er_start = context.compute_incremental_start(
        data_service, "exchange_rates", latest_end
    )
    if er_start is None:
        context.logger.info(
            f"汇率数据已是最新，无需更新（last_date={data_service.get_last_date('exchange_rates').strftime('%Y-%m-%d')}）"
        )
    else:
        context.logger.info(f"汇率增量更新，从 {er_start} 到 {latest_end}")

    async def fetch():
        new_data = {}
        exchange_data = {}
        if us_start is not None:
            new_data.update(
                await context.fetch_us_treasuries(fred_service, us_start, latest_end)
            )
        new_data.update(
            await context.fetch_oecd_bonds(fred_service, oecd_start, latest_end)
        )
        if er_start is not None:
            if data_service.exchange_rates_need_aliyun_rebuild():
                raise Exception(context.exchange_rebuild_msg)
            exchange_data = await context.fetch_exchange_rates(
                fred_service, er_start, latest_end
            )
        return (new_data, exchange_data)

    def validate(update_data):
        new_data, exchange_data = update_data
        if not new_data and (not exchange_data):
            raise Exception("未能获取到任何新数据")
        return update_data

    def save(update_data):
        new_data, exchange_data = update_data
        if new_data:
            data_service.save_fred_data(new_data)
        if exchange_data:
            data_service.save_fred_data(exchange_data, key="exchange_rates")

    def build_payload(update_data):
        new_data, exchange_data = update_data
        return context.build_response_data_with_rates(
            new_data, exchange_data, latest_end
        )

    return UpdatePlan(UpdateStages(fetch, validate, save, build_payload))


def build_commodities(context: UpdateContext) -> UpdatePlan:
    context.logger.info("开始增量更新商品 K 线...")
    commodity_service = context.get_commodity_service()
    data_service = context.get_data_service()
    latest_end = pd.Timestamp.now().normalize()
    start_date = context.compute_incremental_start(
        data_service, "commodities", latest_end
    )
    if start_date is None:
        context.logger.info("商品数据已是最新")
        today = latest_end.date()
        raise UpdateNoOp(
            UpdateResponse(
                success=True,
                message="商品数据已是最新",
                data=CommoditiesUpdateData(
                    commodities=CommoditiesData(
                        date=today, gold=None, silver=None, oil=None, copper=None
                    )
                ),
                updated_at=datetime.now().isoformat(),
            )
        )
    context.logger.info(
        f"增量更新商品，从 {start_date.strftime('%Y-%m-%d')} 到 {latest_end.strftime('%Y-%m-%d')}"
    )

    async def fetch():
        return await commodity_service.fetch_all(start_date.date(), latest_end.date())

    def validate(new_data):
        if not context.has_observations(new_data):
            if context.empty_increment_is_current(data_service, "commodities"):
                raise NoNewData()
            raise Exception(
                context.empty_increment_fail_message(
                    data_service, "commodities", "商品"
                )
            )
        return new_data

    def build_payload(new_data):
        latest_per_commodity = {}
        for name, series in new_data.items():
            if not series.empty:
                last_idx = series.last_valid_index()
                if last_idx is not None:
                    latest_per_commodity[name] = float(series[last_idx])
        return CommoditiesUpdateData(
            commodities=CommoditiesData(
                date=latest_end.date(),
                gold=latest_per_commodity.get("gold"),
                silver=latest_per_commodity.get("silver"),
                oil=latest_per_commodity.get("oil"),
                copper=latest_per_commodity.get("copper"),
            )
        )

    def on_no_data():
        context.logger.info("商品增量区间无新观测，底库已有 last_date，视为已是最新")
        return UpdateResponse(
            success=True,
            message="商品数据已是最新",
            data=CommoditiesUpdateData(
                commodities=CommoditiesData(
                    date=latest_end.date(),
                    gold=None,
                    silver=None,
                    oil=None,
                    copper=None,
                )
            ),
            updated_at=datetime.now().isoformat(),
        )

    return UpdatePlan(
        UpdateStages(fetch, validate, data_service.save_commodities, build_payload),
        on_no_data=on_no_data,
    )


def build_indices(context: UpdateContext) -> UpdatePlan:
    context.logger.info("开始增量更新股指 K 线...")
    index_service = context.get_index_service()
    data_service = context.get_data_service()
    latest_end = pd.Timestamp.now().normalize()
    start_date = context.compute_incremental_start(data_service, "indices", latest_end)
    if start_date is None:
        context.logger.info("股指数据已是最新")
        raise UpdateNoOp(
            UpdateResponse(
                success=True,
                message="股指数据已是最新",
                data=IndicesUpdateData(indices=IndicesData(date=latest_end.date())),
                updated_at=datetime.now().isoformat(),
            )
        )
    context.logger.info(
        f"增量更新股指，从 {start_date.strftime('%Y-%m-%d')} 到 {latest_end.strftime('%Y-%m-%d')}"
    )

    async def fetch():
        return await index_service.fetch_all(start_date.date(), latest_end.date())

    def validate(new_data):
        if not context.has_observations(new_data):
            if context.empty_increment_is_current(data_service, "indices"):
                raise NoNewData()
            raise Exception(
                context.empty_increment_fail_message(data_service, "indices", "股指")
            )
        return new_data

    def build_payload(new_data):
        latest_per_idx = {}
        for name, series in new_data.items():
            if not series.empty:
                last_idx = series.last_valid_index()
                if last_idx is not None:
                    latest_per_idx[name] = float(series[last_idx])
        return IndicesUpdateData(
            indices=IndicesData(
                date=latest_end.date(),
                HKHSI=latest_per_idx.get("HKHSI"),
                SH000001=latest_per_idx.get("SH000001"),
                SPX=latest_per_idx.get("SPX"),
                IXIC=latest_per_idx.get("IXIC"),
                DJI=latest_per_idx.get("DJI"),
            )
        )

    def on_no_data():
        context.logger.info("股指增量区间无新观测，底库已有 last_date，视为已是最新")
        return UpdateResponse(
            success=True,
            message="股指数据已是最新",
            data=IndicesUpdateData(indices=IndicesData(date=latest_end.date())),
            updated_at=datetime.now().isoformat(),
        )

    return UpdatePlan(
        UpdateStages(fetch, validate, data_service.save_indices, build_payload),
        on_no_data=on_no_data,
    )
