"""Executable source registry for every incremental update endpoint."""

from collections.abc import Callable
from dataclasses import dataclass

from src.models import (
    ChinaBondUpdateData,
    CommoditiesUpdateData,
    DR001UpdateData,
    DR007UpdateData,
    EUTreasuriesUpdateData,
    ExchangeRatesUpdateData,
    FundFlowUpdateData,
    HIBORUpdateData,
    IndicesUpdateData,
    JPTreasuriesUpdateData,
    MacroDataWithRates,
    MarginUpdateData,
    TedSpreadUpdateData,
    TGAUpdateData,
    TurnoverUpdateData,
    USTreasuriesUpdateData,
    VIXUpdateData,
    VolumeUpdateData,
)
from src.services.update_pipeline import UpdateContext, UpdatePlan
from src.services.update_sources.a_share import build_dr001, build_dr007
from src.services.update_sources.cross_source import (
    build_china_bonds,
    build_exchange_rates,
    build_fund_flow,
    build_hibor,
)
from src.services.update_sources.final import (
    build_commodities,
    build_eu_bonds,
    build_indices,
    build_jp_bonds,
    build_legacy,
)
from src.services.update_sources.fred import (
    build_ted_spread,
    build_tga,
    build_us_treasuries,
    build_vix,
)
from src.services.update_sources.market import (
    build_margin,
    build_turnover,
    build_volume,
)


@dataclass(frozen=True)
class UpdateSpec:
    key: str
    endpoint: str
    payload_type: type
    contract_test_file: str
    build_stages: Callable[[UpdateContext], UpdatePlan]
    success_message: str
    failure_message: str


_ENTRIES = (
    (
        "us_treasuries",
        "/update/us-treasuries",
        USTreasuriesUpdateData,
        "test_update_contracts_fred.py",
        build_us_treasuries,
        "美国国债数据增量更新成功",
        "美国国债数据增量更新失败",
    ),
    (
        "exchange_rates",
        "/update/exchange-rates",
        ExchangeRatesUpdateData,
        "test_update_contracts_cross_source.py",
        build_exchange_rates,
        "汇率数据增量更新成功",
        "汇率数据增量更新失败",
    ),
    (
        "eu_bonds",
        "/update/eu-bonds",
        EUTreasuriesUpdateData,
        "test_update_contracts_final.py",
        build_eu_bonds,
        "欧洲国债数据增量更新成功",
        "欧洲国债数据增量更新失败",
    ),
    (
        "jp_bonds",
        "/update/jp-bonds",
        JPTreasuriesUpdateData,
        "test_update_contracts_final.py",
        build_jp_bonds,
        "日本国债数据增量更新成功",
        "日本国债数据增量更新失败",
    ),
    (
        "legacy",
        "/update",
        MacroDataWithRates,
        "test_update_contracts_final.py",
        build_legacy,
        "数据更新成功",
        "数据更新失败",
    ),
    (
        "vix",
        "/update/vix",
        VIXUpdateData,
        "test_update_contracts_fred.py",
        build_vix,
        "VIX数据增量更新成功",
        "VIX数据增量更新失败",
    ),
    (
        "tga",
        "/update/tga",
        TGAUpdateData,
        "test_update_contracts_fred.py",
        build_tga,
        "TGA数据增量更新成功",
        "TGA数据增量更新失败",
    ),
    (
        "hibor",
        "/update/hibor",
        HIBORUpdateData,
        "test_update_contracts_cross_source.py",
        build_hibor,
        "HIBOR数据增量更新成功",
        "HIBOR数据增量更新失败",
    ),
    (
        "fund_flow",
        "/update/fund-flow",
        FundFlowUpdateData,
        "test_update_contracts_cross_source.py",
        build_fund_flow,
        "资金流向数据增量更新成功",
        "资金流向数据增量更新失败",
    ),
    (
        "china_bonds",
        "/update/china-bonds",
        ChinaBondUpdateData,
        "test_update_contracts_cross_source.py",
        build_china_bonds,
        "中国国债数据增量更新成功",
        "中国国债数据增量更新失败",
    ),
    (
        "ted_spread",
        "/update/ted-spread",
        TedSpreadUpdateData,
        "test_update_contracts_fred.py",
        build_ted_spread,
        "TED利差数据增量更新成功",
        "TED利差数据增量更新失败",
    ),
    (
        "commodities",
        "/update/commodities",
        CommoditiesUpdateData,
        "test_update_contracts_final.py",
        build_commodities,
        "商品数据增量更新成功",
        "商品数据增量更新失败",
    ),
    (
        "indices",
        "/update/indices",
        IndicesUpdateData,
        "test_update_contracts_final.py",
        build_indices,
        "股指数据增量更新成功",
        "股指数据增量更新失败",
    ),
    (
        "dr007",
        "/update/dr007",
        DR007UpdateData,
        "test_update_contracts_a_share.py",
        build_dr007,
        "DR007 数据增量更新成功",
        "DR007 数据增量更新失败",
    ),
    (
        "dr001",
        "/update/dr001",
        DR001UpdateData,
        "test_update_contracts_a_share.py",
        build_dr001,
        "DR001 数据增量更新成功",
        "DR001 数据增量更新失败",
    ),
    (
        "volume",
        "/update/volume",
        VolumeUpdateData,
        "test_update_contracts_a_share.py",
        build_volume,
        "两市成交额更新成功",
        "两市成交额更新失败",
    ),
    (
        "turnover",
        "/update/turnover",
        TurnoverUpdateData,
        "test_update_contracts_a_share.py",
        build_turnover,
        "两市换手率更新成功",
        "两市换手率更新失败",
    ),
    (
        "margin",
        "/update/margin",
        MarginUpdateData,
        "test_update_contracts_a_share.py",
        build_margin,
        "融资余额更新成功",
        "融资余额更新失败",
    ),
)

UPDATE_SPECS = {
    key: UpdateSpec(
        key, endpoint, payload_type, contract_test_file, builder, success, failure
    )
    for key, endpoint, payload_type, contract_test_file, builder, success, failure in _ENTRIES
}
