"""A Share update preparation and four-stage adapters."""

from datetime import datetime

import pandas as pd

from src.models import (
    DR001Data,
    DR001UpdateData,
    DR007Data,
    DR007UpdateData,
    UpdateResponse,
)
from src.services.update_pipeline import (
    NoNewData,
    UpdateContext,
    UpdateNoOp,
    UpdatePlan,
    UpdateStages,
)


def build_dr007(context: UpdateContext) -> UpdatePlan:
    context.logger.info("开始增量更新 DR007 数据...")
    dr007_service = context.get_dr007_service()
    data_service = context.get_data_service()
    latest_end = pd.Timestamp.now().normalize()
    start_date = context.compute_incremental_start(data_service, "dr007", latest_end)
    if start_date is None or start_date > latest_end:
        context.logger.info("DR007 数据已是最新，无需更新")
        raise UpdateNoOp(
            UpdateResponse(
                success=True,
                message="DR007 数据已是最新，无需更新",
                data=DR007UpdateData(
                    dr007=DR007Data(date=latest_end.date(), value=None)
                ),
                updated_at=datetime.now().isoformat(),
            )
        )
    context.logger.info(f"增量更新 DR007 数据，从 {start_date} 到 {latest_end}")

    async def fetch():
        return await dr007_service.fetch_latest(start_date, latest_end)

    def validate(dr007_df):
        if dr007_df.empty:
            raise NoNewData()
        return dr007_df

    def build_payload(dr007_df):
        last_idx = dr007_df["date"].iloc[-1]
        last_val = dr007_df["dr007"].iloc[-1]
        return DR007UpdateData(
            dr007=DR007Data(
                date=last_idx.date() if last_idx is not None else latest_end.date(),
                value=float(last_val) if last_val is not None else None,
            )
        )

    def on_no_data():
        context.logger.info(f"DR007 区间 [{start_date}, {latest_end}] 无新数据，跳过")
        return UpdateResponse(
            success=True,
            message="DR007 数据已是最新，无需更新",
            data=DR007UpdateData(dr007=DR007Data(date=latest_end.date(), value=None)),
            updated_at=datetime.now().isoformat(),
        )

    return UpdatePlan(
        UpdateStages(fetch, validate, data_service.save_dr007_data, build_payload),
        on_no_data=on_no_data,
    )


def build_dr001(context: UpdateContext) -> UpdatePlan:
    context.logger.info("开始增量更新 DR001 数据...")
    dr001_service = context.get_dr001_service()
    data_service = context.get_data_service()
    latest_end = pd.Timestamp.now().normalize()
    start_date = context.compute_incremental_start(data_service, "dr001", latest_end)
    if start_date is None or start_date > latest_end:
        context.logger.info("DR001 数据已是最新，无需更新")
        raise UpdateNoOp(
            UpdateResponse(
                success=True,
                message="DR001 数据已是最新，无需更新",
                data=DR001UpdateData(
                    dr001=DR001Data(date=latest_end.date(), value=None)
                ),
                updated_at=datetime.now().isoformat(),
            )
        )
    context.logger.info(f"增量更新 DR001 数据，从 {start_date} 到 {latest_end}")

    async def fetch():
        return await dr001_service.fetch_latest(start_date, latest_end)

    def validate(dr001_df):
        if dr001_df.empty:
            raise NoNewData()
        return dr001_df

    def build_payload(dr001_df):
        last_idx = dr001_df["date"].iloc[-1]
        last_val = dr001_df["dr001"].iloc[-1]
        return DR001UpdateData(
            dr001=DR001Data(
                date=last_idx.date() if last_idx is not None else latest_end.date(),
                value=float(last_val) if last_val is not None else None,
            )
        )

    def on_no_data():
        context.logger.info(f"DR001 区间 [{start_date}, {latest_end}] 无新数据，跳过")
        return UpdateResponse(
            success=True,
            message="DR001 数据已是最新，无需更新",
            data=DR001UpdateData(dr001=DR001Data(date=latest_end.date(), value=None)),
            updated_at=datetime.now().isoformat(),
        )

    return UpdatePlan(
        UpdateStages(fetch, validate, data_service.save_dr001_data, build_payload),
        on_no_data=on_no_data,
    )
