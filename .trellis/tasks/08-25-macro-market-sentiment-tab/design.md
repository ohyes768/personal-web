# 市场情绪 Tab — 技术设计

> 与 [prd.md](./prd.md) 配套。技术设计：模块边界、数据契约、数据流、复用清单、向后兼容、风险与回滚。

## 1. 模块边界与新文件清单

### 后端 — 新建

| 文件 | 角色 |
|------|------|
| `backend/macro/src/services/volume_service.py` | 两市成交额 fetcher（沪深交易所官方 API 当日点）|
| `backend/macro/src/services/turnover_service.py` | 换手率 fetcher（同源）|
| `backend/macro/src/services/margin_service.py` | 融资余额 fetcher（akshare 当日点）|
| `backend/macro/src/utils/trade_date.py` | 复用 skill `get_trade_date()` 逻辑，跨3 个 service 共享 |
| `backend/macro/tests/test_volume.py` | 单测（mock SSE/SZSE 响应）|
| `backend/macro/tests/test_turnover.py` | 单测（mock SSE/SZSE 响应）|
| `backend/macro/tests/test_margin.py` | 单测（mock akshare 返回）|

### 后端 — 修改

| 文件 | 改动 |
|------|------|
| `backend/macro/src/api/routes.py` | (a) 第 1019 行 `_ALLOWED_DATA_TYPES` 加 `volume / turnover / margin`；(b) 新增 `POST /api/macro/update/volume / turnover / margin` 三个端点（无 history）|
| `backend/macro/src/services/data_service.py` | `files` 加 `volume.csv / turnover.csv / margin.csv`；新增 `save_volume_data / load_volume / save_turnover_data / load_turnover / save_margin_data / load_margin`；`_query_data_impl` 加载3 个字段 |
| `backend/macro/src/models.py` | `VolumeUpdateData / TurnoverUpdateData / MarginUpdateData`（参考 `DR007UpdateData` 模板）|
| `backend/macro/docs/数据更新端点规范.md` | 加 3 行（3 个 update 端点）|

### 前端 — 修改

| 文件 | 改动 |
|------|------|
| `apps/macro/src/lib/types/economic.ts` | `EconomicDataResponse` 加 `volume?: number[]; turnover?: number[]; margin?: number[]` |
| `apps/macro/src/lib/types/economic.ts` | `TabType` union 加 `'market-sentiment'` |
| `apps/macro/src/app/modules/economic/page.tsx` | (a) 顶部 tabs 数组加 `{id: 'market-sentiment', ...}`；(b) 动态导入 `MarketSentimentTab`；(c) `handleTabChange` 加 market-sentiment 默认 6M 分支 |
| `apps/macro/src/lib/hooks/useFilteredEconomicData.ts` | `getDefaultEconomicData()` 加 3 个空数组；`timeFiltered` slice 3 个新字段 |
| `apps/macro/src/app/modules/economic/components/MarketSentimentTab.tsx` | 新建（参考 `RatesTab.tsx` 模板）|
| `apps/macro/src/app/modules/economic/components/MarketSentimentChart.tsx` | 新建（参考 `RatesChart.tsx` 单图模板）|
| `apps/macro/src/lib/modules/economic/api.ts` | 加 `updateVolume / updateTurnover / updateMargin` 方法 |

### 调度（n8n，已存在）

复用现有 n8n `POST /api/macro/update` 链路，每天 16:30 触发 3 个端点串行调用。无需改动调度。

## 2. 数据契约

### 2.1 后端响应新增字段

```jsonc
// GET /api/macro/data 响应新增顶层字段
{
  // ... 既有字段 ...
  "volume":   [null, 1.5e4, 1.6e4, ...],   // length == dates.length, 单位 亿元
  "turnover": [null, 0.85, 0.92, ...],       // 单位 %
  "margin":   [null, 1.78e4, 1.79e4, ...]    // 单位 亿元
}
```

**对齐规则**（与 dr007 / hibor 一致）：
- 数组长度 = `dates.length`
- 非交易日 / 缺失值 = `null`（Plotly `connectgaps=false` 自动断开）

### 2.2 CSV 格式（append-only）

```csv
date,total_amount_yi
2026-08-21,12500.45
2026-08-22,13780.12
...
```

```csv
date,turnover_rate
2026-08-21,0.92
2026-08-22,0.85
...
```

```csv
date,margin_balance_yi
2026-08-21,17800.23
2026-08-22,17850.45
...
```

**写入策略**：append + 去重（参考 dr007 的 `save_dr007_data` 合并写模式）。同一日期重复写入时新值覆盖旧值（防止节假日修正）。

### 2.3 错误处理

- **交易所 API 5xx / 网络异常**：`@async_retry(max_retries=3, delay=1.0)` 装饰器；重试失败抛 `requests.HTTPError`，routes 层捕获返回 `UpdateResponse(success=False)`
- **akshare 接口异常**：try/except 包装，routes 层捕获返回 `success=False, message="akshare 调用失败: <reason>"`
- **CSV 不存在 / 空文件**：`_query_data_impl` 返回空数组，前端拿到空 series，UI 不渲染该曲线

## 3. 复用与不复用清单

### 复用（按代码模式）

| 复用对象 | 复用方式 |
|----------|---------|
| `dr007_service.py` 的 class + 单例 + `@async_retry` 模式 | volume / turnover fetcher 骨架 |
| `data_service.save_dr007_data` 的合并写逻辑 | volume / turnover / margin 三处 save 函数 |
| `routes.py update_hibor` 端点模板 | volume / turnover / margin 三处 update 端点（去掉历史分叉）|
| `release_rules.py` 的 `total_amount_yi / turnover_rate / margin_balance_yi` workdaily 规则 | 已存在，无需新增 |
| `risk-appetite-skill/scripts/fetch_volume_exchange.py` 的 HTTP 调用细节 | **仅参考 URL + 参数**，不 import |
| `risk-appetite-skill/scripts/fetch_volume.py` 的换手率合成公式 `(sh_amt * sh_rate + sz_amt * sz_rate) / (sh_amt + sz_amt)` | 参考抄到本项目 |
| `risk-appetite-skill/scripts/fetch_margin.py` 的 akshare 调用 | 参考抄到本项目 |
| `RatesTab.tsx` / `RatesChart.tsx` 模式 | MarketSentimentTab / MarketSentimentChart 模板 |

### 不复用（明确）

| 对象 | 原因 |
|------|------|
| `risk-appetite-skill` 整个包 | 跨项目耦合，部署链路不同 |
| `risk-appetite-skill/scripts/fetch_common.py` | skill 私有 utils（含 cache / .env 加载）|
| `akshare.stock_zh_index_daily_em` 等不稳接口 | 实测大量失败，不在主线方案 |
| `china_bond_service.py` | CSV schema 不同，复杂度不匹配 |

## 4. 数据流

### 4.1 每日定时（盘后 16:30）

```
n8n 调度 (16:30)
   ↓
POST /api/macro/update/volume
   ↓
volume_service.fetch_today()
   ↓  get_trade_date() → 今日/昨日/最近交易日
   ↓  fetch_sse_volume(date) + fetch_szse_volume(date)
   ↓  合并 + 计算 total_amount_yi
   ↓
data_service.save_volume_data(df)
   ↓  读现有 CSV → 合并 → 按 date 去重 → 按 date 排序 → 写回
   ↓
backend/macro/data/volume.csv (append 一行)
```

turnover / margin 同链路，串行调用（margin 接口 akshare 可能慢，独立 fail 不阻塞其他）。

### 4.2 前端消费

```
useFullEconomicData (顶层 hook)
   ↓ GET /api/macro/data
EconomicDataResponse（含 volume / turnover / margin）
   ↓ props 透传
MarketSentimentTab.useFilteredEconomicData(fullData, timeRange, 'market-sentiment')
   ↓
MarketSentimentChart
   ├─ trace 1: volume (左轴, 亿元, 橙色)
   ├─ trace 2: turnover (右轴, %, 黄色)
   └─ trace 3: margin (左内轴, 亿元, 绿色)
   共享 xaxis
```

## 5. 关键技术决策

### 5.1 `utils/trade_date.py` 抽取

把 skill `get_trade_date()` 逻辑（约 30 行）抽到 `backend/macro/src/utils/trade_date.py`：

```python
from datetime import datetime, time, timedelta

def get_trade_date(now: datetime | None = None) -> str:
    """返回当前应查询数据的交易日（YYYY-MM-DD）。
    - 周末: 往前找最近交易日
    - 盘中(09:30-16:00): 上一交易日（交易所当日数据未生成）
    - 盘后/非盘中: 今日
    """
    if now is None:
        now = datetime.now()
    # ... 抄自 skill fetch_volume_exchange.py:33-61
```

**决策依据**：3 个 fetcher（volume / turnover / margin）都需要这个逻辑（margin 的 akshare 接口也返回 T-1 数据）。抽到 utils 比复制 3 份更清晰。

### 5.2 CSV 列名选型

- `volume.csv`: `total_amount_yi`（与 skill `risk_data.json` key 对齐，便于将来对接）
- `turnover.csv`: `turnover_rate`
- `margin.csv`: `margin_balance_yi`

**决策依据**：与 `release_rules.py` 已有的中文 key 同源（如 `'两市成交额': ReleaseRule("workdaily", ...)`），前端 `INDICATOR_LABELS` 也用这套 key。

### 5.3 端点设计 — 只 update 无 history

- 不做 `POST /api/macro/fetch/{volume,turnover,margin}/history`
- 理由：交易所官方 API 单 endpoint 仅查当日，无法回溯历史；做 history 端点会要求用户"主动初始化"，但数据源不支持
- append-only 模式：CSV 自然增长，无需 init

### 5.4 MarketSentimentChart 单图 vs 拆 subchart

- 与 rates tab 不同——本任务3 条曲线虽然量级有差异（万亿 vs 0-2%），但通过 3 个 yaxis（左 / 右内 / 右）可以同图叠加
- 拆 subchart 的代价：与 DR007 同图那种"短端/中长端"语义不同，本任务3 个指标同属"市场情绪"维度，单图更符合用户心智

### 5.5 不引入 skill 作为依赖

理由（同 dr007 设计）：
- `risk-appetite-skill/scripts/fetch_volume_exchange.py` 依赖 `fetch_common.py` → `.env` 加载逻辑
- `backend/macro` pyproject 不应反向依赖 `F:/personal-projects/skills/finance-macro/`
- skill 与后端部署链路不同：skill 输出到 `finance-macro/output/`，后端读 `backend/macro/data/`

## 6. 向后兼容性

### 6.1 API 兼容

- `EconomicDataResponse` 是**新增字段**（volume / turnover / margin），非破坏性。前端不读这些字段时忽略即可。
- `_ALLOWED_DATA_TYPES` 加 `volume / turnover / margin` 不影响已有调用方。

### 6.2 前端类型兼容

- `EconomicDataResponse.volume?` 等为可选字段——旧前端版本（还没升级）会忽略此字段，UI 行为不变。

### 6.3 CSV 缺失安全

- **空 CSV / 缺数据**：前端 MarketSentimentChart 检测对应字段全 null 时静默不渲染该曲线（与 hibor / china_bond 缺失段处理一致），不抛错。

## 7. 风险与回滚

| 风险 | 缓解 | 回滚 |
|------|------|------|
| akshare 融资余额接口挂了 | try/except + 单测 mock；监控 `/health` akshare 错误率 | `git revert` margin_service.py + routes.py；CSV 自然不再追加；前端 margin 字段变空不崩 |
| 交易所 API 限流（盘后 16:30 单次调度）| 单请求级 `@async_retry` | 同上 |
| `_ALLOWED_DATA_TYPES` 冲突（与 dr007 任务共享）| 串行合 PR；先合本任务再合 dr007（或反过来）| `git revert` 该行 |
| `TabType` 加成员后未更新所有 switch | grep 后修改（参考 dr007 任务经验）| `git revert` types/economic.ts |
| Plotly 单图 3 轴视觉拥挤 | 用 yaxis / yaxis2 / yaxis3 独立 scale | 调颜色或高度 |

## 8. 与 perf 任务的边界

- **本任务不碰**：nginx gzip / FastAPI GZipMiddleware / `Cache-Control` 头 / 前端分层加载 / localStorage 缓存
- **本任务会小增响应体积**：3 个新序列每条约 6KB（6000 交易日 × 1 float），vs 全量 3MB 可忽略（+0.6%）
- perf 任务可能影响本任务的 gzip 收益基准，在 AC 复核时让 perf 任务再跑一次 `curl --compressed`

## 9. 不在范围（明确）

- history 端点（不补历史）
- 融券余额、融资买入额、融券卖出额
- 北向/南向资金细粒度
- 两市换手率拆分（沪市/深市）
- 盘后实时刷新 / WebSocket
- Tab 与「流动性/风险」合并
- risk-appetite-skill 脚本迁移（解耦，不 import）
- akshare 成交额/换手率接口（实测全挂，不用）