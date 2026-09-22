"""更新端点的显式注册表。"""
from collections.abc import Callable
from dataclasses import dataclass

import pandas as pd

from src.models import (
    ChinaBondUpdateData, CommoditiesUpdateData, DR001UpdateData, DR007UpdateData,
    EUTreasuriesUpdateData, ExchangeRatesUpdateData, FundFlowUpdateData,
    HIBORUpdateData, IndicesUpdateData, JPTreasuriesUpdateData, MacroDataWithRates,
    MarginUpdateData, TGAUpdateData, TedSpreadUpdateData, TurnoverUpdateData,
    MarginData, TurnoverData, USTreasuriesUpdateData, VIXUpdateData, VolumeData,
    VolumeUpdateData,
)
from src.services.update_pipeline import UpdateStages


@dataclass(frozen=True)
class UpdateSpec:
    key: str
    endpoint: str
    payload_type: type
    contract_test_file: str
    build_stages: Callable | None = None


def _market_stages(key: str, value_key: str, data_key: str, data_type: type, payload_type: type):
    def build(data_service, source):
        async def fetch():
            return source.fetch_today()

        def validate(result):
            if result["status"] == "failed" or result[value_key] is None:
                raise Exception(f"{key} 获取失败: {result.get('error', result.get('date'))}")
            return result

        def save(result):
            if key == "margin":
                data_service.save_margin_data(pd.DataFrame({
                    "date": [pd.Timestamp(result["date"])],
                    "margin_balance_yi": [result[value_key]],
                }))
            else:
                getattr(data_service, f"save_{key}_data")(result[data_key])

        def build_payload(result):
            return payload_type(**{key: data_type(
                date=pd.Timestamp(result["date"]).date(), value=float(result[value_key]),
            )})

        return UpdateStages(fetch, validate, save, build_payload)

    return build


_STAGE_BUILDERS = {
    "volume": _market_stages("volume", "total_amount_yi", "volume", VolumeData, VolumeUpdateData),
    "turnover": _market_stages("turnover", "turnover_rate", "turnover", TurnoverData, TurnoverUpdateData),
    "margin": _market_stages("margin", "rzye", "margin", MarginData, MarginUpdateData),
}


_ENTRIES = (
    ("us_treasuries", "/update/us-treasuries", USTreasuriesUpdateData, "test_update_contracts_fred.py"),
    ("exchange_rates", "/update/exchange-rates", ExchangeRatesUpdateData, "test_update_contracts_cross_source.py"),
    ("eu_bonds", "/update/eu-bonds", EUTreasuriesUpdateData, "test_update_contracts_final.py"),
    ("jp_bonds", "/update/jp-bonds", JPTreasuriesUpdateData, "test_update_contracts_final.py"),
    ("legacy", "/update", MacroDataWithRates, "test_update_contracts_final.py"),
    ("vix", "/update/vix", VIXUpdateData, "test_update_contracts_fred.py"),
    ("tga", "/update/tga", TGAUpdateData, "test_update_contracts_fred.py"),
    ("hibor", "/update/hibor", HIBORUpdateData, "test_update_contracts_cross_source.py"),
    ("fund_flow", "/update/fund-flow", FundFlowUpdateData, "test_update_contracts_cross_source.py"),
    ("china_bonds", "/update/china-bonds", ChinaBondUpdateData, "test_update_contracts_cross_source.py"),
    ("ted_spread", "/update/ted-spread", TedSpreadUpdateData, "test_update_contracts_fred.py"),
    ("commodities", "/update/commodities", CommoditiesUpdateData, "test_update_contracts_final.py"),
    ("indices", "/update/indices", IndicesUpdateData, "test_update_contracts_final.py"),
    ("dr007", "/update/dr007", DR007UpdateData, "test_update_contracts_a_share.py"),
    ("dr001", "/update/dr001", DR001UpdateData, "test_update_contracts_a_share.py"),
    ("volume", "/update/volume", VolumeUpdateData, "test_update_contracts_a_share.py"),
    ("turnover", "/update/turnover", TurnoverUpdateData, "test_update_contracts_a_share.py"),
    ("margin", "/update/margin", MarginUpdateData, "test_update_contracts_a_share.py"),
)

UPDATE_SPECS = {
    key: UpdateSpec(key, endpoint, payload_type, contract_test_file, _STAGE_BUILDERS.get(key))
    for key, endpoint, payload_type, contract_test_file in _ENTRIES
}
