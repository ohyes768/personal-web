# 估值契约（理杏仁 PE-TTM 近10年分位）

> 来源：11-02-index-trends-pe-percentile 任务。沪深300 估值分位来源、口径与状态机。
> Last verified: 2026-11-02

## Scope / Trigger

`backend/index-trends` 的理杏仁估值采集、缓存、状态判定与周报/页面展示。
改供应商适配、目标日计算、估值表结构或状态字段前必读。

## 供应商契约

- `POST https://open.lixinger.com/api/cn/index/fundamental`，
  请求体 `stockCodes=["000300"]`、`metricsList=["pe_ttm.mcw","pe_ttm.y10.mcw.cvpos"]`、
  `startDate`/`endDate`（**必须显式给出**：官方默认 endDate 是上周一）、`token`。
- 成功响应 `code=1`，`data` 是数组；指标字段是**平铺的带点号键**，不是嵌套对象；
  `date` 带 `+08:00`。
- `cvpos` 原值是 0–1 的比例，对外换算为 0–100%（1 位小数）；PE 2 位小数。
- **分位直接采用供应商口径**，不本地重算，也不承诺与其他站点一致。

## 目标日

- 页面：最近一个**应当完成的自然周**的最后交易日（该周最后交易日 15:05 已过才算完成；
  周五收盘后才从上周切到本周；进行中的周不取盘中值）。
- 周报：报告所属自然周的最后交易日（与周报 `close_date` 对齐，绝不能用 now−7 天）。
- 目标日由交易日历决定；日历不可用时返回 `calendar_unavailable`，不猜周五是交易日。
- 绝不引用晚于目标日的数据；全周休市沿用最近有交易完整周的估值并注明"休市沿用"。

## 状态机

对外统一对象：`state`（`ok`/`stale`/`empty`/`error`/`disabled`）、`reason`、
`source`/`metric`/`window`、`target_date`、`as_of`、`pe_ttm`、`percentile_pct`、`captured_at`。

- `disabled`：未配置 Token（**不发起任何请求**）。
- `ok`：数据日期严格等于目标日，且本次采集无失败标记。
- `stale`：有合格数据但日期早于目标日（`reason=not_updated_to_target`）。
- `empty`：供应商无合格记录。
- `error`：本次采集失败；可以带缓存值，但状态**不冒充 ok**，页面必须写明"缓存值/更新失败"。
- 数值缺失用 `null`，不用 `0`。

## 缓存与冷却

- 表：`index_valuations`（复合主键 index_code/source/metric/window/date）与
  `valuation_fetch_meta`（目标日、最近尝试、最近成功、错误码）；迁移 `005_valuation_tables`，
  只加表，可重复执行。
- 同一目标日已有成功记录且无失败标记 → **跳过网络请求**。
- 失败后同一目标日进入冷却（默认 15 分钟）；**目标日变化不受旧冷却影响**。
- 失败只更新采集元数据，**不覆盖已存的成功数据**。
- 状态 API **只读缓存**，不在 GET 内请求供应商。

## 凭据边界

- Token 只由后端环境读取（`INDEX_TRENDS_LIXINGER_TOKEN`，`SecretStr`）。
  不进入前端响应、日志、数据库与版本库；错误信息只暴露固定 reason 码，
  **不回显供应商正文、请求体或 Token**。
- 供应商记录非法（bool、NaN、Infinity、PE≤0、cvpos 越界、指数代码不符、日期不可解析或晚于目标日）
  一律跳过；一条合格记录都没有时按响应异常处理。

## 报告与页面

- 周报在幂等/禁用/周未完成检查之后、正文生成之前取估值；估值异常**不改变**
  `business_status` 与投递结果，只增加一行提示。
- 报告快照 `snapshot_json` 固化发送时的估值对象；已 `sent` 的报告不因估值更新而重发。
- 页面在当前通道摘要里单列估值区域，**不复用通道位置的文案或区域标签**：
  通道位置描述相对趋势通道，分位描述相对自身历史估值，两者含义不同。

## Tests Required

`tests/test_lixinger_provider.py`（解析与脱敏）、`tests/test_valuation_service.py`
（目标日、缓存命中、冷却、状态判定）、`tests/test_valuation_store.py`（迁移与读写）、
`tests/test_api_valuation.py`（状态 API 只读、不泄露凭据）、
`tests/test_weekly_report_valuation.py`（报告行、快照、失败不阻断、休市沿用）。

## Wrong vs Correct

Wrong：在状态 API 里顺手请求供应商；失败时把 `pe_ttm` 填 0；把供应商 `msg` 拼进错误文案；
用 now−7 天当周报目标日。
Correct：只读缓存、缺值用 null、错误只给 reason 码、目标日来自交易日历。
