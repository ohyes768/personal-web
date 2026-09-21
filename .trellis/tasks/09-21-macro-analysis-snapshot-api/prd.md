# 宏观 Skill 聚合快照 API

## Goal

为外部宏观分析 Skill 提供一个无需解析网页、一次请求即可取得多个自然月月度信号与一份日频快照的公开只读 API。

## Confirmed facts

- `GET /api/macro/signal?month=YYYY-MM` 返回单月的六维月度快照，页面仅显示其中四个宏观月频组。
- `GET /api/macro/daily-snapshot?date=YYYY-MM-DD` 返回三组、17 个日频指标，已实现 as-of 回退。
- API 只暴露数据；不生成投资建议、不刷新或写入数据。
- 用户确认一次请求应支持 `2026-08`、`2026-09` 等多个自然月，Skill 自行作比较。

## Requirements

1. 新增 `GET /api/macro/analysis/snapshot`，可选 `months=YYYY-MM,YYYY-MM` 与 `date=YYYY-MM-DD`。
2. `months` 缺省时返回最新月；提供时按传入顺序返回，最多 12 个，重复月份去重。
3. 返回四张月度卡（货币政策、信用扩张、经济运行、通胀环境）及三张日频卡（流动性、外部压力、市场情绪）。
4. 指标统一输出稳定 key、中文名称、单位、数值、数据日期和状态；日频额外输出前值、变化和 as-of 回退标志。
5. 无月度快照的 period 保留为 `unavailable`，不影响其他 period 或日频数据。
6. 返回 `schema_version`、生成时间和质量汇总（missing、stale、asof fallback）。
7. 产出公开 API 文档，涵盖访问路径、参数、七卡指标清单、响应、状态码与 Skill 调用示例。

## Acceptance criteria

- [ ] 双月请求以一次 HTTP 200 返回按参数顺序排列的两个 `monthly.periods` 和三张 `daily.cards`。
- [ ] 默认请求仅返回最新月；非法月/日期或超出 12 月返回 400。
- [ ] 缺失期标记为 `unavailable`，而非全接口 404。
- [ ] 日频回退正确标记 `is_asof_fallback=true` 并进入质量汇总。
- [ ] 测试覆盖批量、默认、缺失、校验与日频映射。
- [ ] `backend/macro/docs/` 中有可公开分发的 API 文档。

## Out of scope

- 不改既有 `/signal`、`/months`、`/daily-snapshot` 契约。
- 不改前端、上游采集、调度、缓存或上传接口。
- 不在后端生成交易建议、宏观结论或 LLM 分析。
