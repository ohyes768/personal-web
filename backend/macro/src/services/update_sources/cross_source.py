"""Cross Source update preparation and four-stage adapters."""

from datetime import datetime

import pandas as pd

from src.models import (
    ChinaBondData,
    ChinaBondUpdateData,
    ExchangeRateData,
    ExchangeRates,
    ExchangeRatesUpdateData,
    FundFlow,
    FundFlowData,
    FundFlowUpdateData,
    HIBORData,
    HIBORUpdateData,
    UpdateResponse,
)
from src.services.update_pipeline import (
    NoNewData,
    UpdateContext,
    UpdateNoOp,
    UpdatePlan,
    UpdateStages,
)


def build_exchange_rates(context: UpdateContext) -> UpdatePlan:
    context.logger.info("开始增量更新汇率数据...")
    fred_service = context.get_fred_service()
    data_service = context.get_data_service()
    if data_service.exchange_rates_need_aliyun_rebuild():
        raise Exception(context.exchange_rebuild_msg)
    latest_end = pd.Timestamp.now().normalize()
    start_date = context.compute_incremental_start(
        data_service, "exchange_rates", latest_end
    )
    if start_date is None:
        context.logger.info("汇率数据已是最新，跳过本次更新")
        response_data = ExchangeRatesUpdateData(
            exchange_rates=ExchangeRates(
                dollar_index=ExchangeRateData(date=latest_end.date(), value=None),
                usd_cny=ExchangeRateData(date=latest_end.date(), value=None),
                usd_jpy=ExchangeRateData(date=latest_end.date(), value=None),
                usd_eur=ExchangeRateData(date=latest_end.date(), value=None),
            )
        )
        raise UpdateNoOp(
            UpdateResponse(
                success=True,
                message="汇率数据已是最新，无需更新",
                data=response_data,
                updated_at=datetime.now().isoformat(),
            )
        )
    context.logger.info(f"增量更新汇率数据，从 {start_date} 到 {latest_end}")

    async def fetch():
        return await context.fetch_exchange_rates(fred_service, start_date, latest_end)

    def validate(exchange_data):
        if not context.has_observations(exchange_data):
            if context.empty_increment_is_current(data_service, "exchange_rates"):
                raise NoNewData()
            raise Exception(
                context.empty_increment_fail_message(
                    data_service, "exchange_rates", "汇率"
                )
            )
        return exchange_data

    def save(exchange_data):
        data_service.save_fred_data(exchange_data, key="exchange_rates")

    def build_payload(exchange_data):
        latest_rates = {}
        for name, series in exchange_data.items():
            if not series.empty:
                last_idx = series.last_valid_index()
                if last_idx is not None:
                    latest_rates[name] = {
                        "date": last_idx.strftime("%Y-%m-%d"),
                        "value": float(series[last_idx]),
                    }
        return ExchangeRatesUpdateData(
            exchange_rates=ExchangeRates(
                dollar_index=latest_rates.get(
                    "dollar_index", ExchangeRateData(date=latest_end.date(), value=None)
                ),
                usd_cny=latest_rates.get(
                    "usd_cny", ExchangeRateData(date=latest_end.date(), value=None)
                ),
                usd_jpy=latest_rates.get(
                    "usd_jpy", ExchangeRateData(date=latest_end.date(), value=None)
                ),
                usd_eur=latest_rates.get(
                    "usd_eur", ExchangeRateData(date=latest_end.date(), value=None)
                ),
            )
        )

    def on_no_data():
        context.logger.info("汇率增量区间无新观测，底库已有 last_date，视为已是最新")
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

    return UpdatePlan(
        UpdateStages(fetch, validate, save, build_payload), on_no_data=on_no_data
    )


def build_hibor(context: UpdateContext) -> UpdatePlan:
    context.logger.info("开始增量更新HIBOR数据...")
    hibor_service = context.get_hibor_service()
    data_service = context.get_data_service()
    latest_end = pd.Timestamp.now().normalize()
    start_date = context.compute_incremental_start(data_service, "hibor", latest_end)
    if start_date is None or start_date > latest_end:
        context.logger.info("HIBOR数据已是最新，无需更新")
        raise UpdateNoOp(
            UpdateResponse(
                success=True,
                message="HIBOR数据已是最新，无需更新",
                data=HIBORUpdateData(
                    hibor=HIBORData(date=latest_end.date(), value=None)
                ),
                updated_at=datetime.now().isoformat(),
            )
        )
    context.logger.info(f"增量更新HIBOR数据，从 {start_date} 到 {latest_end}")

    async def fetch():
        return await hibor_service.fetch_series(start_date, latest_end)

    def validate(hibor_series):
        if not context.has_observations(hibor_series):
            if context.empty_increment_is_current(data_service, "hibor"):
                raise NoNewData()
            raise Exception(
                context.empty_increment_fail_message(data_service, "hibor", "HIBOR")
            )
        return hibor_series

    def save(hibor_series):
        data_service.save_fred_data({"hibor": hibor_series}, key="hibor")

    def build_payload(hibor_series):
        last_idx = hibor_series.last_valid_index()
        return HIBORUpdateData(
            hibor=HIBORData(
                date=last_idx.date() if last_idx is not None else latest_end.date(),
                value=float(hibor_series[last_idx]) if last_idx is not None else None,
            )
        )

    def on_no_data():
        context.logger.info("HIBOR增量区间无新观测，底库已有 last_date，视为已是最新")
        return UpdateResponse(
            success=True,
            message="HIBOR数据已是最新，无需更新",
            data=HIBORUpdateData(hibor=HIBORData(date=latest_end.date(), value=None)),
            updated_at=datetime.now().isoformat(),
        )

    return UpdatePlan(
        UpdateStages(fetch, validate, save, build_payload), on_no_data=on_no_data
    )


def build_fund_flow(context: UpdateContext) -> UpdatePlan:
    context.logger.info("开始增量更新沪深港通资金数据...")
    fund_flow_service = context.get_fund_flow_service()
    data_service = context.get_data_service()
    latest_end = pd.Timestamp.now().normalize()

    async def fetch():
        return fund_flow_service.fetch_recent(days=10)

    def validate(fund_flow_data):
        if not any((not df.empty for df in fund_flow_data.values())):
            raise Exception("未能获取到任何资金流向新数据")
        return fund_flow_data

    def build_payload(fund_flow_data):
        latest_north = None
        latest_south = None
        if "north" in fund_flow_data and (not fund_flow_data["north"].empty):
            last_idx = fund_flow_data["north"].last_valid_index()
            if last_idx is not None:
                row = fund_flow_data["north"].loc[last_idx]
                latest_north = FundFlowData(
                    date=last_idx.date(),
                    deal_amount=float(row["北向成交额"])
                    if pd.notna(row["北向成交额"])
                    else None,
                )
        if "south" in fund_flow_data and (not fund_flow_data["south"].empty):
            last_idx = fund_flow_data["south"].last_valid_index()
            if last_idx is not None:
                row = fund_flow_data["south"].loc[last_idx]
                latest_south = FundFlowData(
                    date=last_idx.date(),
                    net_flow=float(row["南向净流入"])
                    if pd.notna(row["南向净流入"])
                    else None,
                    buy=float(row["南向买入"]) if pd.notna(row["南向买入"]) else None,
                    sell=float(row["南向卖出"]) if pd.notna(row["南向卖出"]) else None,
                )
        return FundFlowUpdateData(
            fund_flow=FundFlow(
                north=latest_north or FundFlowData(date=latest_end.date()),
                south=latest_south or FundFlowData(date=latest_end.date()),
            )
        )

    return UpdatePlan(
        UpdateStages(fetch, validate, data_service.save_fund_flow, build_payload)
    )


def build_china_bonds(context: UpdateContext) -> UpdatePlan:
    context.logger.info("开始增量更新中国国债数据...")
    china_bond_service = context.get_china_bond_service()
    data_service = context.get_data_service()
    latest_end = pd.Timestamp.now().normalize()
    start_date = context.compute_incremental_start(
        data_service, "china_bond", latest_end
    )
    if start_date is None or start_date >= latest_end:
        context.logger.info("中国国债数据已是最新，跳过本次更新")
        response_data = ChinaBondUpdateData(
            china_bond_10y=ChinaBondData(date=latest_end.date(), value=None)
        )
        raise UpdateNoOp(
            UpdateResponse(
                success=True,
                message="中国国债数据已是最新，无需更新",
                data=response_data,
                updated_at=datetime.now().isoformat(),
            )
        )
    context.logger.info(f"增量更新中国国债数据，从 {start_date} 到 {latest_end}")

    async def fetch():
        return china_bond_service.fetch_china_bond_yield(
            start_date.strftime("%Y-%m-%d"), latest_end.strftime("%Y-%m-%d")
        )

    def validate(bond_df):
        if not context.has_observations(bond_df):
            if context.empty_increment_is_current(data_service, "china_bond"):
                raise NoNewData()
            raise Exception(
                context.empty_increment_fail_message(
                    data_service, "china_bond", "中国国债"
                )
            )
        return bond_df

    def save(bond_df):
        data_service.save_china_bond_data(
            {
                "10y": bond_df["中国国债收益率10年"],
                "10年-2年": bond_df["中国国债收益率10年-2年"],
            }
        )

    def build_payload(bond_df):
        col_10y = "中国国债收益率10年"
        last_idx = bond_df.index[-1]
        return ChinaBondUpdateData(
            china_bond_10y=ChinaBondData(
                date=last_idx.date(),
                value=float(bond_df[col_10y].iloc[-1])
                if pd.notna(bond_df[col_10y].iloc[-1])
                else None,
            )
        )

    def on_no_data():
        context.logger.info(
            "中国国债增量区间无新观测，底库已有 last_date，视为已是最新"
        )
        response_data = ChinaBondUpdateData(
            china_bond_10y=ChinaBondData(date=latest_end.date(), value=None)
        )
        return UpdateResponse(
            success=True,
            message="中国国债数据已是最新，无需更新",
            data=response_data,
            updated_at=datetime.now().isoformat(),
        )

    return UpdatePlan(
        UpdateStages(fetch, validate, save, build_payload), on_no_data=on_no_data
    )
