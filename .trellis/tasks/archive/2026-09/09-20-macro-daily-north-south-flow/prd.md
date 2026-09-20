# 宏观信号日频首页补充北向/南向资金与中债利率指标

## Goal

宏观信号首页「日频」模式补充资金流向与国内利率指标：外部压力组增加北向 3 指标，市场情绪组增加南向净流入，流动性（monetary_policy）组增加中债 10Y 与 10Y-2Y 期限利差。资金流向数据在 fund_flow.csv 已每日更新、前后端 label/发布规则表已登记北向 key，属于补全半成品；中债利率数据在 china_bond.csv 已有。

## Background

- 北向净买额自 2024-08-16 起交易所停发，只有成交总额（fund_flow.csv 列「北向成交额」）每日公布 → 北向只能上成交额口径指标
- exchange-rate-skill（外部压力评分）已使用北向 7 日窗口指标；前端 `INDICATOR_LABELS` 与后端 `release_rules.py` 均已登记北向 3 个中文 key
- 南向净流入（列「南向净流入」）无评分体系引用，经用户确认归入市场情绪组（交易活跃度外溢信号）

## Requirements

### 1. 后端日频快照（backend/macro/src/services/daily_snapshot_service.py）

`_DAILY_INDICATORS` 扩充：

- `exchange_rate` 组新增 3 项，数据源 `load_data:fund_flow`，列「北向成交额」：
  - 北向当日成交额：asof 取 ≤ 所选日期最近值（亿元）
  - 北向7日日均成交额：含当日的最近 7 个交易日窗口均值（asof）
  - 北向7日环比：当前 7 日日均 vs 前一窗口（第 8~14 交易日）日均的变化百分比
- `risk_appetite` 组新增 1 项：南向净流入，数据源 `load_data:fund_flow`，列「南向净流入」（asof，亿港元）

约束：

- key 命名沿用日频快照英文 snake_case 风格（建议 `north_today_yi` / `north_7d_avg_yi` / `north_7d_change_pct` / `south_net_yi`）
- 沿用现有 `_extract` asof 语义：所选日期无数据时回退最近可得值，返回 `prev_value`/`data_date`
- 7 日窗口计算基于 fund_flow 序列自身的交易日（窗口不足 7 日时返回 null 而非报错）
- 遵守 spec `.trellis/spec/guides/macro-daily-snapshot.md`：§4 不走 `query_data_by_tab`，用原始 load 方法；§6 dates 列表口径不变（仍以 volume 序列为交易日基准，fund_flow 交易日与 A 股一致，无需调整）

### 2. 前端日频卡片（apps/macro/src/app/modules/economic/components/macro-signal/constants.ts）

- `DAILY_GROUPS.exchange_rate.indicators` 追加北向 3 个 key（追加到现有 4 项之后）
- `DAILY_GROUPS.risk_appetite.indicators` 追加 `south_net_yi`
- `INDICATOR_LABELS` 补充 4 个英文 key 的中文 label（北向 3 个中文 key 已存在，需补英文 key 映射对齐后端输出；南向需新增）
- `INDICATOR_LINK_MAP` 补 4 个 key → `market-sentiment`（该 Tab 已含 fund_flow 曲线 HsgtFundFlowChart，与 volume/turnover/margin 同款跳转）

### 3. 流动性组补充中债利率（2026-09-20 追加需求）

- 后端 `_DAILY_INDICATORS.monetary_policy` 追加 2 项，数据源 `load_data:china_bond`：
  - key `cn_10y`：中债 10Y 到期收益率，列「中国10y」，单点 asof（亿元口径不适用，纯 % 利率）
  - key `cn_10y_2y`：中国 10Y-2Y 期限利差，列「中国10年-2年」，单点 asof
- 前端同步三处：`DAILY_GROUPS.monetary_policy.indicators` 追加 2 key；`INDICATOR_LABELS` 补 `cn_10y: { label: '中债10Y', unit: '%', digits: 2 }`、`cn_10y_2y: { label: '10Y-2Y 利差', unit: '%', digits: 2 }`；`INDICATOR_LINK_MAP` 补 2 key → `rates`（该 Tab 含 china_bond 曲线）
- 该组日频标题「流动性」、不渲染档位刻度的现状不变；指标数 13 → 15

## Acceptance Criteria

- [ ] `GET /api/macro/daily-snapshot` 的 `groups.exchange_rate` 含 3 个北向指标、`groups.risk_appetite` 含南向净流入、`groups.monetary_policy` 含 `cn_10y`/`cn_10y_2y`，value/prev_value/data_date 字段完整
- [ ] asof 语义生效：指定历史日期时返回该日期前最近可得值
- [ ] fund_flow.csv / china_bond.csv 缺失或列缺失时对应指标 value 为 null，接口不报错（沿用空 Series 路径）
- [ ] 前端日频首页：货币政策（流动性）卡片 4 个指标、外部压力卡片 7 个指标、市场情绪卡片 4 个指标，label/单位/小数位正确
- [ ] 后端 pytest 现有测试全绿，新增覆盖北向 3 指标计算（7 日窗口、环比）、南向提取、中债 2 指标提取与缺失容错
- [ ] 前端 `pnpm build` 通过

## Out of Scope

- 月度模式不改动（外部压力/市场情绪月度卡片维持设计上的排除）
- 不动 exchange-rate-skill / risk-appetite-skill 评分逻辑
- 北向净买额已停发，不做净流入口径
