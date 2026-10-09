# 更新端点现状矩阵（批 1 契约依据）

> 盘点日期：2026-09-21。生产实现唯一来源：`backend/macro/src/api/routes.py`。
> 本矩阵只覆盖 18 条 `POST /api/update*` 路由；`/api/fetch/*/history` 是全量回补，另有自身测试，不计入本任务的 18 条更新端点。

| 路径 | fetcher / 输入 | 保存调用 | 成功 data 顶层字段 |
|---|---|---|---|
| `/update/us-treasuries` | `_fetch_us_treasuries` | `save_fred_data` | `us_treasuries` |
| `/update/exchange-rates` | `_fetch_exchange_rates` | `save_fred_data(..., key="exchange_rates")` | `exchange_rates` |
| `/update/eu-bonds` | `_fetch_oecd_bonds`（eu 子集） | `save_fred_data` | `eu_treasuries` |
| `/update/jp-bonds` | `_fetch_oecd_bonds`（jp 子集） | `save_fred_data` | `jp_treasuries` |
| `/update` | 美债、OECD、汇率三个 fetcher | `save_fred_data`（两次） | 宏观组合 payload |
| `/update/vix` | FRED `fetch_series` | `save_fred_data(..., key="vix")` | `vix` |
| `/update/tga` | FRED `fetch_series` | `save_fred_data(..., key="tga")` | `tga` |
| `/update/hibor` | HIBOR `fetch_series` | `save_fred_data(..., key="hibor")` | `hibor` |
| `/update/fund-flow` | `fetch_recent(days=10)` | `save_fund_flow` | `fund_flow` |
| `/update/china-bonds` | `fetch_china_bond_yield` | `save_china_bond_data` | `china_bond_10y` |
| `/update/ted-spread` | 两次 FRED `fetch_series` | `save_ted_spread_data` | `ted_spread` |
| `/update/commodities` | commodity `fetch_all` | `save_commodities` | `commodities` |
| `/update/indices` | index `fetch_all` | `save_indices` | `indices` |
| `/update/dr007` | DR007 `fetch_history` | `save_dr007_data` | `dr007` |
| `/update/dr001` | DR001 `fetch_latest` | `save_dr001_data` | `dr001` |
| `/update/volume` | BaoStock `fetch_today` | `save_volume_data` | `volume` |
| `/update/turnover` | BaoStock `fetch_today` | `save_turnover_data` | `turnover` |
| `/update/margin` | Margin `fetch_today` | `save_margin_data` | `margin` |

## 失败语义（共性）

- 全局更新锁被占用：HTTP 200，`success=false`，`error_code="UPDATE_IN_PROGRESS"`，不执行 fetch/save。
- fetcher 抛异常或返回当前端点定义的失败/空数据：HTTP 200，`success=false`，`error_code="UPDATE_FAILED"`，不得调用 save。
- 已有底库且增量窗口没有新观测的端点可返回 `success=true` / “已是最新”；这是幂等成功，不属于本批的 fetch 失败断言。

## 已有安全网

- `tests/test_dr001_update_response.py` 已覆盖 DR001 有效数据落库后能被 `UpdateResponse` 序列化。
- `tests/test_incremental_empty.py` 覆盖多数 FRED/阿里云端点的空窗口和锁语义；批 1 将补足所有成功 payload 与实际 save 调用，并补齐未覆盖端点的失败不落库断言。
