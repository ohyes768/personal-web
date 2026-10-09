"""A-share market source adapters (BaoStock and margin balance)."""

import pandas as pd

from src.models import (
    MarginData,
    MarginUpdateData,
    TurnoverData,
    TurnoverUpdateData,
    VolumeData,
    VolumeUpdateData,
)
from src.services.update_pipeline import UpdateContext, UpdatePlan, UpdateStages


def _market_stages(
    key: str, value_key: str, data_key: str, data_type: type, payload_type: type
):

    def build(data_service, source):

        async def fetch():
            return source.fetch_today()

        def validate(result):
            if result["status"] == "failed" or result[value_key] is None:
                raise Exception(
                    f"{key} 获取失败: {result.get('error', result.get('date'))}"
                )
            return result

        def save(result):
            if key == "margin":
                data_service.save_margin_data(
                    pd.DataFrame(
                        {
                            "date": [pd.Timestamp(result["date"])],
                            "margin_balance_yi": [result[value_key]],
                        }
                    )
                )
            else:
                getattr(data_service, f"save_{key}_data")(result[data_key])

        def build_payload(result):
            return payload_type(
                **{
                    key: data_type(
                        date=pd.Timestamp(result["date"]).date(),
                        value=float(result[value_key]),
                    )
                }
            )

        return UpdateStages(fetch, validate, save, build_payload)

    return build


def build_volume(context: UpdateContext) -> UpdatePlan:
    build = _market_stages(
        "volume", "total_amount_yi", "volume", VolumeData, VolumeUpdateData
    )
    return UpdatePlan(build(context.get_data_service(), context.get_baostock_service()))


def build_turnover(context: UpdateContext) -> UpdatePlan:
    build = _market_stages(
        "turnover", "turnover_rate", "turnover", TurnoverData, TurnoverUpdateData
    )
    return UpdatePlan(build(context.get_data_service(), context.get_baostock_service()))


def build_margin(context: UpdateContext) -> UpdatePlan:
    build = _market_stages("margin", "rzye", "margin", MarginData, MarginUpdateData)
    return UpdatePlan(build(context.get_data_service(), context.get_margin_service()))
