# 对比页补齐 DR007 与市场情绪四指标

## Goal

对比页可选指标与各图表 Tab 的日频曲线对齐：补上目前勾不到的 DR007、两市成交额、换手率、融资余额。选中后按现有对比读数路径出曲线，不改默认四指标，不加新 Tab。

## 背景

对比白名单 27 个 id（`apps/macro/src/lib/modules/comparison/types.ts` `IndicatorId`），与 `INDICATOR_SECTIONS`（`backend/macro/src/services/data_service.py:52`）对齐。下列 4 条已有 CSV、已在专用 Tab 出图，但对比勾不到：

| id | 中文 | 专用 Tab | CSV 段 / 响应字段 |
|----|------|----------|-------------------|
| `dr007` | DR007 | 利率利差 | `dr007` |
| `volume` | 两市成交额 | 市场情绪 | `volume` |
| `turnover` | 换手率 | 市场情绪 | `turnover` |
| `margin` | 融资余额 | 市场情绪 | `margin` |

`query_data_by_indicators` 已按 section 读这些 CSV（`_load` 含 `load_dr007` / `load_volume` / `load_turnover` / `load_margin`）。缺的是白名单与前端注册表。

## Requirements

### R1 对比白名单增加 4 个 id

- 前端 `IndicatorId`、`INDICATORS`、`extractSeries` 与后端 `INDICATOR_SECTIONS` 同步增加：`dr007`、`volume`、`turnover`、`margin`
- 非法 id 仍 400；空 `indicators` 仍 400
- `DEFAULT_INDICATORS` 仍为 `dxy, us_10y, vix, gold`

### R2 选择器分组

- `dr007` 归入现有 `rates`（利率利差）
- `volume` / `turnover` / `margin` 新增分组 `market_sentiment`（市场情绪），排在 `GROUP_ORDER` 末尾
- 单位与专用 Tab 一致：DR007 `%`、成交额 `亿元`、换手率 `%`、融资余额 `亿元`；不额外缩放（CSV 已是展示单位）
- 颜色对齐专用图：DR007 `#f97316`，成交额 `#f97316`，换手率 `#eab308`，融资余额 `#22c55e`

### R3 按需读数

勾选这 4 个之一时，`GET /api/macro/data/comparison?indicators=` 只拉对应 CSV 段，响应含该字段与 `dates`。前端 `extractSeries` 从 `data.dr007` / `data.volume` / `data.turnover` / `data.margin` 取值。已缓存 id 列表的子集不重拉（现有 ComparisonTab 行为，不改）。

## 约束

- 不改 `POST /update/*`、调度、宏观信号、市场情绪/利率图本身
- 不把南向买入/卖出、德债/日债、月度信号点值加入对比
- 不改 `MAX_INDICATORS`（仍 6）
- 不改 EconomicDataResponse 字段名

## 验收标准（Acceptance Criteria）

- [ ] **AC1** 对比选择器「利率利差」组出现 DR007；「市场情绪」组出现两市成交额、换手率、融资余额
- [ ] **AC2** 勾选 `dr007` 时请求 `indicators` 含 `dr007`，响应有 `dr007` 与 `dates`，图上能画出（CSV 有数的前提下）
- [ ] **AC3** 勾选 `volume` / `turnover` / `margin` 同 AC2，各字段独立
- [ ] **AC4** 默认进入对比仍只请求 `dxy,us_10y,vix,gold`，响应不含 `dr007`/`volume`/`turnover`/`margin`
- [ ] **AC5** `GET /data/comparison?indicators=not_a_real_id` 仍 400
- [ ] **AC6** 后端单测：上述 4 个 id 映射到对应 section；未知 id 仍报错

## 范围外

- 南向买入/卖出从 CSV/API 删除
- 德债/日债恢复
- 信号首页月度指标进对比
- TGA 千亿美元缩放（对比页既有问题，本任务不修）
