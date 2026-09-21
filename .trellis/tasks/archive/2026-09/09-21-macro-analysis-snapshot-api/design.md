# 技术设计：宏观 Skill 聚合快照 API

## Boundary

在 `backend/macro` 查询层新增纯编排服务。它调用既有 `MacroSignalService` 和 `DailySnapshotService`，不读取网页，也不直接解析 CSV 或 skill 原始 JSON。路由只负责参数校验与 HTTP 响应；指标映射、卡片裁剪和质量状态在服务内完成。

## Contract

`GET /api/macro/analysis/snapshot?months=2026-08,2026-09&date=2026-09-21`

- `months`：逗号分隔，最多 12 个；缺省时取 `MacroSignalService.get_available_months()` 的第一个。
- `date`：可选，沿用 `DailySnapshotService` 的默认日期规则。
- 200 可表示部分数据可用；仅意外服务错误返回 500。

顶层包括 `schema_version`、`generated_at`、`request`、`monthly.periods`、`daily` 和 `quality`。月度 period 仅投影四组；每组一张卡。日频三组映射为 `liquidity`、`external_pressure`、`market_sentiment`。统一 indicator 字段，并保留月度评分信息。

## Data flow

```
MacroSignalService --(monthly snapshot x N)--> AnalysisSnapshotService --> response model --> route
DailySnapshotService --(daily snapshot x 1)---------------------/
```

月度 `data_date`、`analyzed_at`、`next_release_at` 原样透传。日频 `change=value-prev_value`，仅在前值存在时计算；`data_date != daily.as_of` 标记回退。值为空为 `missing`；月度不存在为 `unavailable`。第一版不自行判定指标滞后，`stale_keys` 保留为空，避免未经确认的阈值影响结论。

## Compatibility

新路径位于现有 `/api` router，nginx 已暴露为 `/api/macro/...`，无需网关配置。新增模型不修改既有响应模型。移除新路由和服务即可回滚，底层接口与前端不受影响。
