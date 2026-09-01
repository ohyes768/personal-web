# 宏观信号:南向净买额+北向成交总额接入

## Goal

沪深港通（HSGT）资金数据自 2024-08-16 起北向净买额停发，现有 `fund_flow` 数据线事实上已断：`data/fund_flow.csv` 不存在，每日调度 `/update/fund-flow` 仍在跑但写入的是死数据源（akshare `stock_market_fund_flow` 的北向列已全空）。本任务用东财原始 API（akshare 同源）重新接通这条线，在市场情绪 Tab 提供"跨境资金"维度：

- **北向成交总额**（外资活跃度指标，2014-11-17 至今全量有值）
- **南向净流入/买入/卖出**（方向指标，东财仍每日公布）

## Background（调研结论，2026-08-29 已验证）

### 数据源事实

| 指标 | 2024-08-16 前 | 2024-08-16 后 | 说明 |
|------|--------------|--------------|------|
| 北向净买额 | ✅ | ❌ 全 null | 交易所停发，源头上没有 |
| **北向成交总额 DEAL_AMT** | ✅ | ✅ 全量 | 东财 API 有，akshare 封装丢弃 |
| **南向买入/卖出/净流入** | ✅ | ✅ 全量 | 东财 API 有，akshare 封装丢弃 |

- 原始 API：`GET https://datacenter-web.eastmoney.com/api/data/v1/get`，`reportName=RPT_MUTUAL_DEAL_HISTORY`
- akshare `stock_hsgt_hist_em` 用同一 API 同一 reportName，但列映射漏掉 `DEAL_AMT`/`DEAL_NUM`；直调原始 API 不是新爬虫，与 akshare 同源同风险
- `MUTUAL_TYPE` 编码：001=沪股通，003=深股通，005=北向合计，006=南向合计
- 单位：原始值（百万元）÷ 100 = 亿元。验证：南向 006 `BUY_AMT=44732.81` ↔ akshare 显示 447.33 亿港元
- 勾稽验证：北向 005 `DEAL_AMT=278121.63` = 沪股通 123405.23 + 深股通 154716.4（2026-08-28）
- 历史覆盖：北向 005 共 2741 行（2014-11-17 → 2026-08-28）无缺口；单页 pageSize 上限 500，全量需翻页

### 现有代码链路（backend/macro）

- `src/services/fund_flow_service.py:51` `fetch_all_fund_flow()` — 用 `ak.stock_market_fund_flow`，只取北向/南向净流入，buy/sell 恒 None
- `src/services/data_service.py:648` `save_fund_flow()` — 固定 6 列（北向净流入/买入/卖出 + 南向净流入/买入/卖出）
- `src/api/routes.py:1532` `/fetch/fund-flow/history`、`:1620` `/update/fund-flow`
- `src/scheduler/scheduler.json` — `a_share_daily` 组每日 16:30 含 `/update/fund-flow`
- `src/config.py:103` `fund_flow_start_date = "2014-11-17"`

### 前端现状（apps/macro）

- 无独立资金流 Tab；`fund_flow` 数据消费方仅两处：
  - comparison 模块指标 `north_net`/`south_net`（`indicators.ts:30-31`，归一化对比）
  - `useFilteredEconomicData.ts:131` 切片透传
- 市场情绪 Tab（`MarketSentimentTab.tsx`）：单图 3 trace（成交额/换手率/融资余额，双 y 轴）；初始化 `/fetch/volume-turnover/history`，更新串行 volume→turnover→margin

## Requirements

### R1 后端数据源替换

- `fund_flow_service.py` 重写为直调东财 `RPT_MUTUAL_DEAL_HISTORY`（MUTUAL_TYPE=005 北向 + 006 南向），复用现有 tenacity 重试模式
- 返回结构：`{"north": df(北向成交额), "south": df(南向净流入, 南向买入, 南向卖出)}`
- 单位统一亿元（原始百万 ÷ 100）
- 全量回补分页拉取（pageSize=500 翻页）覆盖 2014-11-17 至今；增量窗口近 10 个自然日（对齐 baostock 自愈模式）

### R2 CSV 与查询层重建

- `data/fund_flow.csv` 重建为 4 列：`北向成交额, 南向净流入, 南向买入, 南向卖出`（亿元）
- `data_service.py` `save_fund_flow` / fund_flow 段读取映射 / comparison `INDICATOR_SECTIONS` 同步新列
- API `fund_flow` 字段改为：`north_deal_amount, south_net_flow, south_buy, south_sell`
- 旧列 `north_buy/north_sell/north_net_flow` 字段移除（源头已死，不保留）

### R3 端点与调度

- `/fetch/fund-flow/history`：全量回补（分页翻到 2014-11-17）
- `/update/fund-flow`：增量窗口近 10 日，幂等 keep=last
- 调度 `a_share_daily` 组保持 `/update/fund-flow` 不变，无需改 scheduler.json
- 响应模型 `FundFlow`（models.py）字段同步新结构

### R4 前端市场情绪 Tab 新增图

- 现有 3 trace 图不动；下方新增"沪深港通资金"图：
  - 北向成交额（左轴，亿元，正值）
  - 南向净流入（右轴，亿元，可正可负，0 线参考）
- 数据来源：`market-sentiment` Tab 响应新增 `fund_flow` 字段（后端 `TAB_SECTIONS`/`TAB_RESPONSE_FIELDS` 的 `market-sentiment` 加入 `fund_flow` 段）
- 初始化按钮（`initMarketSentimentHistory`）改为并行回补 volume-turnover + fund-flow 两端点；更新按钮串行链加第 4 步 `/update/fund-flow`

### R5 前端 comparison 指标修正

- 删除死指标 `north_net`；新增 `north_deal`（北向成交额）
- `south_net` 改读新列（标签不变"南向净流入"）
- normalize.ts / indicators.ts / types 同步

## Acceptance Criteria

- [ ] AC1 `POST /api/macro/fetch/fund-flow/history` 回补后 `data/fund_flow.csv` 存在，4 列，首行 2014-11-17，末行为最近交易日；2026-08-28 北向成交额 ≈ 2781.22 亿、南向净流入 ≈ 11.76 亿（勾稽数据）
- [ ] AC2 `GET /api/macro/data/market-sentiment` 响应含 `fund_flow.north_deal_amount` 等新字段，长度与 dates 对齐
- [ ] AC3 `POST /api/macro/update/fund-flow` 重跑同日无重复行（keep=last 幂等）
- [ ] AC4 市场情绪 Tab 渲染两张图：原 3 trace 图不回归；新"沪深港通资金"图北向成交额与南向净流入双轴显示，南向负值段在 0 线下方
- [ ] AC5 comparison 指标选择器无 `north_net`；选"北向成交额"+"南向净流入"能出归一化曲线（2024-08 之后有数据）
- [ ] AC6 后端 pytest 通过（含 fund_flow_service 新测试：分页、单位换算、勾稽、空数据不抛异常）
- [ ] AC7 前端 `pnpm build` 通过

## Out of Scope

- 不做"外资参与度 = 北向成交额 ÷ 两市成交额"派生指标（将来放 comparison 做归一化即可，前端自己能算）
- 不保留/不迁移 2014-2024 历史北向净流入列（已确认丢弃）
- 不改宏观信号 Tab（macro-signal 走外部 skill JSON，另线）
- 不新建独立资金流 Tab
- 不动南向 BUY/SELL 之外的港股通（沪/深港通单边）细分数据
