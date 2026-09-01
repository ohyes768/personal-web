# 新增"市场情绪"Tab（两市成交额 / 换手率 / 融资余额）

## Goal

在 `apps/macro` 顶部 Tab 导航新增第 9 个 Tab「市场情绪」，展示 A 股市场情绪相关的 3 个核心指标的时间序列：

1. **两市成交额**（沪市 + 深市合计，单位：亿元）
2. **换手率**（沪市 + 深市按成交额加权的全市场换手率，单位：%）
3. **融资余额**（沪市 + 深市合计，单位：亿元）

数据通过**每日定时任务**写入 CSV（每交易日盘后拉一次当日点，append 不覆盖）；前端展示随时间增长自然延展的曲线。

## 背景

### 当前宏观页 Tab 结构（8 个）

```
treasury-exchange / bonds / liquidity-risk / rates /
comparison / commodities / stock-indices / macro-signal
```

无任何 tab 展示**国内 A 股市场情绪指标**。

### 数据源真实验证（关键证据）

2026-08-25 上午实测了 5 个 akshare 接口 + 2 个交易所接口，结果：

| 接口 | 状态 |
|------|------|
| `akshare.stock_zh_index_daily_em("sh000001")` | ⚠️ 首次失败、重试成功 156 行 |
| `akshare.stock_zh_index_daily_em("sz399001")` | ❌ 持续 ConnectionError |
| `akshare.stock_market_activity_legu()` | ❌ AttributeError（乐咕挂了）|
| `akshare.stock_zh_a_spot_em()` | ❌ ConnectionError |
| `akshare.macro_china_market_margin_sh/sz()` | ✅ 3980/3782 行全量历史（融资余额可用）|
| 沪深交易所官方 API（`commonQuery.do` / `ShowReport/data`）| ✅ HTTP 200，响应正常 |

**结论**：akshare 不稳（今日 3/5 失败）；**融资余额走 akshare**、**成交额 + 换手率走沪深交易所官方 API**。交易所 API 单 endpoint 仅查当日，要补历史需逐日循环 90 次——不划算。**只取当日点**，靠定时任务每日追加。

### skill 已有的当日点实现（参考）

`risk-appetite-skill/scripts/fetch_volume_exchange.py` 已实现了：
- `fetch_both_exchanges()` — 当日两市合计成交额（带 `get_trade_date()` 自动判断盘中/盘后+回退上一交易日）
- `fetch_sse_volume / fetch_szse_volume` — 单独交易所
- `fetch_sse_turnover / fetch_szse_turnover` — 换手率

`risk-appetite-skill/scripts/fetch_margin.py` 的 `fetch_margin_ohlc()` 取当日融资余额（akshare 接口当日数据，T 日 09:45 出 T-1 数据）。

### macro-signal 已有 risk_data.json 上传

`apps/macro/src/app/modules/economic/components/macro-signal/constants.ts` 已列：
- `total_amount_yi` / `两市成交额`
- `turnover_rate` / `换手率`
- `margin_balance_yi` / `融资融券余额`

说明 risk-appetite-skill 已在写 `risk_data.json`，但走的是 macro-signal 上传链路（JSON 当日点），不是 CSV 全量序列。前端 `/api/macro/data` 接口**没有这3 个字段**。

## Requirements

### 1. 后端 fetcher（3 个 service，每日定时 fetch 当日点）

#### 1.1 `volume_service.py`（两市成交额）

- **数据源**（参考 `risk-appetite-skill/scripts/fetch_volume_exchange.py`）：
  - 沪市：`https://query.sse.com.cn/commonQuery.do?sqlId=COMMON_SSE_SJ_GPSJ_CJGK_MRGK_C&SEARCH_DATE={date}`
  - 深市：`https://www.szse.cn/api/report/ShowReport/data?CATALOGID=1803_sczm&TABKEY=tab1&txtQueryDate={date}`
- 日期选择：调用 skill `get_trade_date()` 逻辑（盘中→上一交易日；盘后→今日；非交易日→最近交易日）。**不 import skill**，把这段逻辑（约 30 行）抄到本项目 `utils/trade_date.py`
- 单位：亿元（skill 内部已转换）
- 返回：`async def fetch_today() -> dict[date, total_amount_yi]`
- **append 写入**：`save_volume_data(df)` 与现有 CSV 合并（按 date 去重，新值覆盖旧值）

#### 1.2 `turnover_service.py`（换手率）

- **数据源**（参考 `fetch_volume_exchange.py:fetch_sse_turnover` + `fetch_szse_turnover`）：
  - 沪市 SSE 加权换手率 + 深市 cjje/ltsz 自计算
- 合成公式：`combined = (sh_amt * sh_rate + sz_amt * sz_rate) / (sh_amt + sz_amt)`
- 单位：%
- 返回：`async def fetch_today() -> dict[date, turnover_rate]`
- **append 写入**

#### 1.3 `margin_service.py`（融资余额）

- **数据源**：`akshare.macro_china_market_margin_sh() + akshare.macro_china_market_margin_sz()` —— akshare 返回全量历史，但本任务**只看当日点**
- 合并：沪市 + 深市 `融资余额` 合计，万元 → 亿元（÷100000000）
- 返回：`async def fetch_today() -> dict[date, margin_balance_yi]`
- **append 写入**
- 注：融资余额接口当日数据 T 日 09:45 才出 T-1 数据

### 2. 后端响应契约

`EconomicDataResponse` 顶层新增3 个字段（**扁平数组**）：

```json
{
  // ... 既有字段 ...
  "volume":   (number | null)[],   // 两市合计成交额 (亿元)
  "turnover": (number | null)[],   // 加权换手率 (%)
  "margin":   (number | null)[]    // 融资余额 (亿元)
}
```

具体动作：
- `models.py` 加 `VolumeUpdateData / TurnoverUpdateData / MarginUpdateData`
- `data_service.py` 加 `save_volume_data / load_volume / save_turnover_data / load_turnover / save_margin_data / load_margin`
- `data_service._query_data_impl` 加载3 个 CSV，reindex + ffill 对齐到全量日期
- `routes.py` 加：
  - `POST /api/macro/update/volume`（当日增量，无需 history endpoint）
  - `POST /api/macro/update/turnover`
  - `POST /api/macro/update/margin`
- `_ALLOWED_DATA_TYPES` 扩到 `["volume", "turnover", "margin"]`
- `services/release_rules.py` 已有 3 个指标 workdaily 规则（line 64-66）—— 无需新增

**不做 history 端点**：CSV 自然增长，无需用户主动 init。

### 4. 调度

**复用现有 n8n `POST /api/macro/update` 链路**（每个 update 端点独立调用）：
- 每个交易日 16:30 触发（盘后 + 融资余额 T-1 数据已发布）
- 3 个端点串行调用：先 volume → turnover → margin
- 失败重试：单端点失败不影响其他

前端不需要新增按钮——复用现有 `RefreshButton`，3 个新指标的 label 加进现有的 `economicApi.update*` 方法。

### 5. 前端 Tab 与图表

- **`apps/macro/src/lib/types/economic.ts`**：`EconomicDataResponse` 加 `volume?: number[]; turnover?: number[]; margin?: number[]`
- **`TabType` 新增 `'market-sentiment'`**（union 第 9 个成员）
- **`page.tsx`**：
  - 顶部 tabs 数组加 `{id: 'market-sentiment', label: '市场情绪', description: '...'}`
  - 动态导入 `MarketSentimentTab`
  - 处理 `handleTabChange` 默认 6M 时间范围
- **`MarketSentimentTab.tsx`**（参考 `RatesTab.tsx`）：
  - `useFilteredEconomicData(fullData, timeRange, 'market-sentiment')`
- **`MarketSentimentChart.tsx`**：
  - 单图 3 条 trace 同图（两市成交额 左轴 + 换手率 右轴 + 融资余额 左内轴）
  - 颜色：橙（成交额）、黄（换手率）、绿（融资余额）
- **`useFilteredEconomicData.ts`**：
  - `getDefaultEconomicData()` 加 `volume: []` 等3 个默认空数组
  - `timeFiltered` 构造时把3 个字段 slice

### 6. 文档

- `backend/macro/docs/数据更新端点规范.md`：加 3 行（3 个 update 端点，无 history）
- `release_rules.py`：已含，无需新增

## 约束

- 不引入 `risk-appetite-skill` 作为后端依赖。fetcher 模式在本项目内独立维护（与 dr007 设计一致）。
- 不改变 `EconomicDataResponse` 现有字段
- `_ALLOWED_DATA_TYPES` 必须扩到 3 个 key
- **append-only 写入**：3 个 CSV 只能追加新日期，不能覆盖历史（参考 dr007 的合并写逻辑）
- **akshare 上游不稳**：margin fetcher 必须 try/except 包装，失败时返回 success=False，不抛 500
- 单测覆盖：mock akshare / mock 交易所响应，覆盖 save+load roundtrip + append 合并

## 验收标准（Acceptance Criteria）

- [ ] **AC1 后端 update volume**：`POST /api/macro/update/volume` 后 `data/volume.csv` 存在，每交易日 16:30 调度后追加 1 行（date, total_amount_yi），无重复日期
- [ ] **AC2 后端 update turnover**：同上
- [ ] **AC3 后端 update margin**：同上（融资余额字段来自 akshare）
- [ ] **AC4 后端响应**：`GET /api/macro/data` 返回 JSON 含 `volume / turnover / margin` 三个数组，长度 = `dates.length`，非 null 元素日期对应交易日
- [ ] **AC5 前端渲染**：切到「市场情绪」Tab，3M 视图可见 3 条曲线（随 CSV 累积天数增长自然延展），颜色与 legend 一致
- [ ] **AC6 时间范围**：切换 1M / 3M / 6M / 1Y / ALL 时 3 条曲线同步缩放
- [ ] **AC7 现有回归**：其他 8 个 Tab 数据渲染无变化
- [ ] **AC8 类型安全**：`pnpm build` 通过
- [ ] **AC9 后端测试**：新增 `tests/test_volume.py / test_turnover.py / test_margin.py`，mock 网络调用，覆盖 CSV 写入、append 合并、null 对齐三路径
- [ ] **AC10 文档**：`docs/数据更新端点规范.md` 加 3 行

## 范围外（明确不做）

- **history 端点**：不补历史，靠调度每日追加
- **融券余额、融资买入额、融券卖出额**：本任务只看 `margin_balance_yi`
- **北向/南向资金**（fund_flow）：已在 `EconomicDataResponse` 里
- **两市换手率拆分（沪市/深市）**：只看合成加权值
- **盘后实时刷新 / WebSocket**：本任务只做每日调度
- **新 Tab 与「流动性/风险」合并**：明确不做，保持独立
- **risk-appetite-skill 脚本迁移**：解耦，不 import
- **akshare 成交额/换手率接口**：实测全挂，不用

## 风险与依赖

- **风险 1**：akshare 融资余额接口挂了
  - 缓解：try/except + 单测 mock；监控 `/health` 上 akshare 错误率
- **风险 2**：交易所 API 限流（盘后大量调用）
  - 缓解：只在 16:30 单次调度 + 单请求级别重试
- **风险 3**：`TabType` union 加新成员后，所有 switch / match 都要更新
- **依赖**：与 `08-24-macro-page-perf` / `08-24-macro-add-dr007-to-rates-tab` 任务并行推进
- **冲突点**：
  - `routes.py` `_ALLOWED_DATA_TYPES` —— 与 dr007 任务共享，需协调顺序
  - `useFilteredEconomicData.ts` 的 `timeFiltered` 构造 —— 与 dr007 任务共享

## Notes

- **当日点 + 调度的折中**：放弃 akshare 不稳的成交额/换手率全量历史接口，转为交易所官方 API 当日点 + 每日调度。可靠性远高于 akshare，代价是曲线随调度天数自然增长（无历史回溯）
- **融资余额**仍走 akshare 因为 akshare 这次实测稳定（akshare 接口差异：macro_* 系列稳，stock_* 系列不稳）
- **新增 Tab 而非塞进 liquidity-risk**：liquidity-risk 的 VIX/TGA/HIBOR 是海外资金视角，与 A 股市场情绪性质不同
- **3 条曲线同图**：量级差异用多 y 轴解决
- **复用 skill 而不 import**：与 dr007 设计一致

## 后续规划（不在本任务范围）

- 若 akshare 修复后可补成交额/换手率的历史（独立任务）
- 把"市场情绪"加入 macro-signal 评分体系
- 北向资金细粒度曲线图加进 market-sentiment tab