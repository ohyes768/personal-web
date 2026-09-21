# Macro Skill 聚合快照 API

> **Version:** 1.0
> **Last updated:** 2026-09-21
> **Audience:** 外部宏观分析 Skill、自动化任务和只读数据消费者

## Purpose

一次读取多个自然月的四张月度信号卡，以及同一分析时点的三张日频信号卡。接口只聚合与标准化数据，不生成投资建议、不触发数据更新，也不需要调用方解析网页或上游 JSON。

## Public access

```http
GET https://web.duomi77.cn:9443/api/macro/analysis/snapshot
```

接口无需鉴权。网关对外前缀是 `/api/macro`；后端服务直连时路径为 `/api/analysis/snapshot`。

## Request

```http
GET /api/macro/analysis/snapshot?months=2026-08,2026-09&date=2026-09-21
```

| Parameter | Type | Required | Description |
|---|---|---:|---|
| `months` | string | no | 逗号分隔的 `YYYY-MM`，最多 12 个；按传入顺序返回，重复值自动去重。省略时取最新可用月。 |
| `date` | string | no | `YYYY-MM-DD` 日频分析时点。省略时沿用服务端 15:00 规则。 |

示例：

```bash
curl 'https://web.duomi77.cn:9443/api/macro/analysis/snapshot?months=2026-08,2026-09&date=2026-09-21'
```

## Response

```jsonc
{
  "success": true,
  "data": {
    "schema_version": "1.0",
    "generated_at": "2026-09-21T10:30:00+08:00",
    "request": { "months": ["2026-08", "2026-09"], "date": "2026-09-21" },
    "monthly": { "periods": [
      { "month": "2026-08", "status": "ok", "cards": [] },
      { "month": "2026-09", "status": "ok", "cards": [] }
    ] },
    "daily": { "as_of": "2026-09-21", "cards": [] },
    "quality": {
      "status": "partial",
      "missing_keys": ["vix"],
      "stale_keys": [],
      "asof_fallback_keys": ["dr007"]
    }
  }
}
```

### Card and indicator fields

每张卡有 `id`、`title`、`frequency`、`status`、`indicators`；月度卡额外含已有上游结论 `conclusion` 与 `score`。

每个指标均有：`key`、`name`、`unit`、`value`、`data_date`、`status`。

- 月度指标还可有 `analyzed_at`、`next_release_at`、`next_release_note`。
- 日频指标还可有 `previous_value`、`change` 和 `is_asof_fallback`。
- `value: null` 时仍保留该指标，且 `status` 为 `missing`。
- 日频 `data_date` 早于 `daily.as_of` 时，`is_asof_fallback` 为 `true`。

## Seven-card catalog

| Card id | Title | Frequency | Indicator keys |
|---|---|---|---|
| `monetary_policy` | 货币政策 | monthly | `lpr_1y`, `lpr_5y`, `mlf_net_yi` |
| `money_supply` | 信用扩张 | monthly | `m2_yoy`, `m1_yoy`, `social_yoy`, `m2_m1_spread`, `spread_change_pp` |
| `entity_economy` | 经济运行 | monthly | `pmi_manufacturing`, `industrial_yoy`, `fai_yoy`, `retail_yoy` |
| `inflation` | 通胀环境 | monthly | `cpi_yoy`, `ppi_yoy` |
| `liquidity` | 流动性 | daily | `dr001`, `dr007`, `cn_10y`, `cn_10y_2y` |
| `external_pressure` | 外部压力 | daily | `dollar_index`, `usd_cny`, `ted_spread`, `hibor_overnight`, `north_today_yi`, `north_7d_avg_yi`, `north_7d_change_pct`, `cn_us_10y_spread`, `vix` |
| `market_sentiment` | 市场情绪 | daily | `volume`, `turnover`, `margin`, `south_net_yi` |

月度卡会保留上游同组返回的全部指标；表中列出第一版 Skill 应依赖的标准 key。

## Quality and error semantics

| Condition | HTTP | Response behavior |
|---|---:|---|
| 部分指标空值或日频回退 | 200 | 通过 `quality` 与指标 `status` 说明，Skill 应降低结论置信度。 |
| 月份没有快照 | 200 | 该 period 为 `{ "status": "unavailable", "cards": [] }`，其他月份照常返回。 |
| `months` / `date` 格式错误，或月份数不在 1-12 | 400 | `{ "detail": "..." }` |
| 内部读取异常 | 500 | `{ "detail": "..." }` |

## Recommended Skill usage

1. 请求一次最新快照，或传入两个至十二个目标月份。
2. 先读取 `quality.status`、`missing_keys` 与 `asof_fallback_keys`。
3. 基于同一响应中的月度 `periods` 比较环比，并以 `daily.cards` 补充最新市场状态。
4. 在生成结论时明确说明缺失或回退数据；不要将 API 数据解释为交易建议。

## Compatibility

- `schema_version` 当前为 `1.0`。新增字段为兼容性变更；Skill 应忽略未知字段。
- 既有 `/api/macro/signal`、`/months`、`/daily-snapshot` 保持不变；本接口只是它们的面向 Skill 投影。
