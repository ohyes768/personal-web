# 调研结论：A 股日频历史数据源（2026-08-29 实测）

## 已验证可用

### BaoStock（本任务采用）
- `bs.query_history_k_data_plus(code, "date,close,volume,amount,turn", frequency="d", adjustflag="3")`
- `sh.000001` 上证指数：1990-12-19 至今，8714 行，turn 无空值
- `sz.399106` 深证综指：1991-04-04 至今，8641 行，turn 仅 18 行空值
- `amount` 单位元；`turn` 单位 %；需显式 `bs.login()` / `bs.logout()`
- 交叉验证 2026-08-28：沪 9703.65 亿 + 深 11313.50 亿 ≈ 21017 亿，量级正确
- 验证脚本：`backend/macro/demo_baostock.py`（任务收尾删除）

### 融资余额（范围外，供后续任务参考）
- `ak.macro_china_market_margin_sh()` / `_sz()` 直接返回 2010-03-31 至今全量历史
  （沪 3983 行 / 深 3785 行，单位**元**）
- 现有 `margin_service.fetch_today()` 只取最后一行；回补 = 同调用取全表
- 注意：`margin_service.py` 注释写"万元→亿元"，实际单位是元，÷1e8 结果恰好正确

## 已验证不可用 / 不采信

| 数据源 | 结论 |
|---|---|
| 官方交易所 API 历史日期 | SSE 仅返回近一两年；SZSE `txtQueryDate` 历史返回空 → 不能回补 |
| 新浪 `stock_zh_index_daily` | 只有 volume（股数），无成交额 |
| 腾讯 `stock_zh_index_daily_tx` | `amount` 列实为成交量（手），非金额 |
| 东财 `index_zh_a_hist`（akshare 封装） | 本机 ConnectionError（被断连）；requests 直连 push2his kline 可用但与 akshare 失败原因待查，不采用 |

## 口径差异记录（切换原因）

- 2026-08-28 沪市成交额：BaoStock 9703.65 亿 vs 现有 `volume_service` 官方口径
  19429.86 亿（≈2 倍，疑 PRODUCT_CODE 11/17 混入非股票品种或单位问题）
- 现有 `volume.csv` 仅 2 天数据（2026-08-25 起），口径切换几乎无成本；
  keep=last 合并写会自动覆盖
- 换手率口径：官方加权 1.3991% vs BaoStock 上证指数 1.0431%（2026-08-28），
  分母统计不同但同趋势同量级；统一采用 BaoStock
