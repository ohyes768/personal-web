# 估值契约（理杏仁 PB / PE-TTM 近10年分位，多指数）

> 来源：11-02-index-trends-pe-percentile（单指数 PE 分位）→ 11-04（每日采集）
> → 11-19-chinext50-pb-valuation（多指数 × 双指标，PB 为主、PE-TTM 为辅）。
> Last verified: 2026-11-19

## Scope / Trigger

`backend/index-trends` 的理杏仁估值采集、缓存、状态判定与查询/页面展示。
改供应商适配、目标日计算、估值表结构或状态字段前必读。

## 指数与指标

- 指数来自注册表 `src/core/indexes.py`（当前 000300 沪深300、399673 创业板50）。
  **一个指数一次请求**，两条指标（PE-TTM 与 PB）一起取回。
- 指标注册表（`src/data/lixinger.py`）：

  | metric key | 数值字段 | 分位字段 |
  |---|---|---|
  | `pe_ttm_mcw` | `pe_ttm.mcw` | `pe_ttm.y10.mcw.cvpos` |
  | `pb_mcw` | `pb.mcw` | `pb.y10.mcw.cvpos` |

- 分位窗口固定 **y10（近10年）**。理杏仁只提供 1/3/5/10/20 年与上市以来的现成分位，
  **没有 6 年**；因此与天弘官方"PB 近6年分位"策略并不严格可比，这是已知差异。
- 单条指标缺失不拖垮另一条：解析时逐指标取值，缺哪一个就只少那一个点。

## 供应商契约

- `POST https://open.lixinger.com/api/cn/index/fundamental`，
  请求体 `stockCodes=[<指数代码>]`、`metricsList` 为上面四个字段、
  `startDate`/`endDate`（**必须显式给出**：官方默认 endDate 是上周一）、`token`。
- 成功响应 `code=1`，`data` 是数组；指标字段是**平铺的带点号键**，不是嵌套对象；
  `date` 带 `+08:00`。
- `cvpos` 原值是 0–1 的比例，对外换算为 0–100%（1 位小数）；数值保留 2 位小数。
- **分位直接采用供应商口径**，不本地重算，也不承诺与其他站点一致。

## 目标日

- 页面与默认采集：**最近一个已收盘交易日**（每日口径）。
  以 Asia/Shanghai **15:05** 收盘阈值为界：阈值之前取上一个交易日，
  阈值之后可取当日；周末与节假日沿用最近一个已收盘交易日，**绝不引用未来数据**。
- 历史指定周查询能力仍按该自然周最后交易日取值，不能用 now−7 天；Web 不再生成周报。
- 目标日由交易日历决定；日历不可用时返回 `calendar_unavailable`，不猜周五是交易日。
- 绝不引用晚于目标日的数据。

## 状态机

**按指标各自判状态**，再聚合出指数级的顶层对象：

- 顶层（兼容旧调用）：`state`/`reason`/`source`/`metric`/`window`/`target_date`/
  `as_of`/`value`/`pe_ttm`/`percentile_pct`/`captured_at` + `index_code`/`name`/`metrics`。
  顶层的 `state`/`as_of`/`value` 等字段**取自 `pe_ttm_mcw`**；`pe_ttm` 是 `value` 的
  历史别名（旧页面与简报按这个名字读）。
- `metrics`：`{metric key: 该指标的完整状态快照}`，两条指标都在，哪怕一条是 `disabled`。
- 单指标状态：
  - `disabled`：未配置 Token（**不发起任何请求**）。
  - `ok`：数据日期严格等于目标日，且本次采集无失败标记。
  - `stale`：有合格数据但日期早于目标日（`reason=not_updated_to_target`）。
  - `empty`：供应商无合格记录（`reason=no_data`）。**空数据不是 error**：
    供应商照常应答，只是这条指标还没有值。
  - `error`：本次采集失败；可以带缓存值，但状态**不冒充 ok**，页面必须写明"缓存值/更新失败"。
- 数值缺失用 `null`，不用 `0`。

## 采集调度

- 每日 **18:30**（`INDEX_TRENDS_VALUATION_REFRESH_CRON`，默认 `30 18 * * mon-fri`）
  独立采集，**与 16:30 行情刷新解耦**：行情刷新不联动估值，行情失败也不影响估值采集。
- 采集按注册表逐个指数执行；**一个指数失败不中断其余指数**（见 `main.py` 的 `valuation_job`）。
- 定时采集前先查交易日历：确认当日休市就**跳过**，不发任何请求；
  日历不可用时抛 `CalendarUnavailableError`（明确异常，不猜交易日）。
- 启动时仍做一次估值初始化（尽力而为，缓存命中不发请求），失败不阻断启动。
- 采集入口（定时 / 启动 / 手动 / 查询）**共用一把锁**串行执行
  "查缓存 → 请求 → 发布"，锁内重新查缓存：重叠执行不重复请求、不重复发布。
- 周报生成与投递由 Hermes 负责（读本服务的查询 API）；
  本服务不生成或发送周报，也不在启动时补发。

## 缓存与冷却

- 表：`index_valuation_history`（复合主键 index_code/source/metric/window/date，
  **`value` 列存指标数值**）与 `valuation_fetch_meta`（主键 **index_code + metric**）。
  `index_valuations` 是旧版"单指标快照"表，保留为历史档案、不再写入；
  迁移 `006_multi_index` 会把它的 PE 行回填进 `index_valuation_history`。
- 首次采集某指标时回填整段 10 年（`INITIAL_BACKFILL_DAYS`），让分位走势图一开始就有历史；
  之后只补最近 30 天并顺带补齐空档。
- 同一目标日已有成功记录且无失败标记 → **跳过网络请求**。
- 失败后同一目标日进入冷却（默认 15 分钟）；**目标日变化不受旧冷却影响**。
- 失败只更新采集元数据，**不覆盖已存的成功数据**。
- 失败标记**只属于它自己的目标日与指标**：`(指数, 指标)` 各自记账，
  别的目标日/指标按自己的数据判定状态，不拿旧失败说失败，也不拿新失败抹掉历史数据。
- 状态 API **只读缓存**，不在 GET 内请求供应商。

## 接口

- `GET /api/indices/{code}/status?model=…`：行情 + `valuation`（顶层兼容字段 + `metrics`）。
- `GET /api/indices/{code}/valuation/history?metric=pb_mcw|pe_ttm_mcw[&start_date=…]`：
  分位序列 `{dates, values, percentiles}`，供分位走势图使用。
  `metric` 不在注册表内 → **400** 并列出支持值；未知指数 → **404** 并列出支持代码。

## 凭据边界

- Token 只由后端环境读取（`INDEX_TRENDS_LIXINGER_TOKEN`，`SecretStr`）。
  不进入前端响应、日志、数据库与版本库；错误信息只暴露固定 reason 码，
  **不回显供应商正文、请求体或 Token**。
- 供应商记录非法（bool、NaN、Infinity、数值≤0、cvpos 越界、指数代码不符、日期不可解析或晚于目标日）
  一律跳过；一条合格记录都没有时按响应异常处理。

## 采集、查询与页面

- Web 负责每日行情/估值刷新、启动估值初始化与页面手动刷新，估值异常不改变行情的成功/失败语义。
- Hermes 只读状态 API，负责简报生成、定时与投递；Web 不再生成、发送或启动补发周报。
- 旧报告快照 `snapshot_json` 与历史状态保留，不因估值更新而修改。
- 页面在当前通道摘要里单列估值区域，**不复用通道位置的文案或区域标签**：
  通道位置描述相对趋势通道，分位描述相对自身历史估值，两者含义不同。
  指标默认显示 **PB 分位**（创业板盈利波动大，PE 分母不稳），PE 用于交叉验证。

## Tests Required

`tests/test_lixinger_provider.py`（解析与脱敏）、`tests/test_valuation_service.py`
（每日目标日、缓存命中、冷却、状态判定、并发保护）、
`tests/test_valuation_daily_job.py`（两个独立任务、休市跳过、日历异常、并发只请求一次）、
`tests/test_valuation_store.py`（迁移与读写）、
`tests/test_api_valuation.py`（状态 API 只读、不泄露凭据）、
`tests/test_refresh_lifecycle.py`（每日刷新与估值任务分离、启动行为与历史保留）、
`tests/test_multi_index.py`（多指数存储隔离、旧库迁移、双指标解析、metric 白名单）。

## Wrong vs Correct

Wrong：把 PB 的数值写进 `pe_ttm` 列；两条指标共用一份采集元数据（一条失败把另一条判成失败）；
把 `data=[]` 判成 `error`；在状态 API 里顺手请求供应商；失败时把数值填 0；
把供应商 `msg` 拼进错误文案；用 now−7 天猜目标日；把周一到周五当成交易日；
在 16:30 行情刷新里顺带采集估值；让两个采集入口并发写同一份缓存。
Correct：按 `(index_code, metric, window, date)` 存 `value`；两条指标各自记账、各自判状态；
只读缓存、缺值用 null、错误只给 reason 码、目标日来自交易日历；
定时采集先判休市再发请求；采集串行化。
