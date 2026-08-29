# 按 Tab 拆读数 — 技术设计

> 与 [prd.md](./prd.md) 配套。仓库已有 `/data/{tab}` 骨架；本文写清要改的契约、日期轴、对比按需、缓存与 loading。

## 1. 边界

### 后端 — 改

| 文件 | 改动 |
|------|------|
| `backend/macro/src/services/data_service.py` | `TAB_SECTIONS` / `TAB_RESPONSE_FIELDS`：rates 加回 `us_treasuries`；market-sentiment 去掉 `us_treasuries`，dates 用三条情绪 CSV 并集；新增 `query_data_by_indicators` + id→section 映射；comparison 禁止无 indicators 的全量 |
| `backend/macro/src/api/routes.py` | `get_data_by_tab` 改 `def`；`tab=comparison` 读 `indicators` query，缺则 400；非法 id 400 |
| `backend/macro/tests/test_query_data_by_tab.py` | 扩：日期轴、rates 字段、indicators、400 路径 |

### 前端 — 改

| 文件 | 改动 |
|------|------|
| `apps/macro/src/lib/modules/economic/api.ts` | `getTabData` 不变；新增 `getComparisonData(indicators: IndicatorId[])` |
| `apps/macro/src/lib/hooks/useTabEconomicData.ts` | 删 localStorage；内存 TTL 5min；对比走 indicators 缓存 |
| `apps/macro/src/app/modules/economic/page.tsx` | 对比 Tab 把 `selectedIds` 的请求交给 hook（或 ComparisonTab 内自拉） |
| `apps/macro/src/app/modules/economic/components/ComparisonTab.tsx` | 按 selectedIds 请求；子集不重拉；内容区 loading |
| `apps/macro/src/app/modules/economic/components/TabPanelLoading.tsx` | **新建**：Tab 内转圈，非全屏 |
| 各 `*Tab.tsx` | 用 `TabPanelLoading` 替换灰字 / 全屏 overlay |

### 不改

`POST /update/*`、scheduler、`/signal`。默认 Tab 仍为 `macro-signal`（其它任务）。

`MarketSentimentChart` 的 `yaxis2.overlaying: 'y'` 已补，换手率才能叠到成交额/融资余额同一张图。

## 2. 契约

### 2.1 业务 Tab

```
GET /api/macro/data/{tab}?start_date=2000-01-01
```

`{tab}` ∈ `treasury-exchange | liquidity-risk | rates | commodities | stock-indices | market-sentiment`

响应：`DataResponse`，`data` 只含该 Tab 字段。`dates.length` 等于各序列 length。

### 2.2 对比

```
GET /api/macro/data/comparison?indicators=dxy,us_10y,vix,gold&start_date=2000-01-01
```

`indicators` 必填。id 白名单与 `apps/macro/src/lib/modules/comparison/types.ts` 的 `IndicatorId` 一致。

id → CSV 段：

| ids | section |
|-----|---------|
| us_3m, us_2y, us_10y | us_treasuries |
| cn_10y, cn_10y_2y | china_bond |
| dxy, usd_cny, usd_jpy, usd_eur | exchange_rates |
| vix | vix |
| tga | tga |
| hibor | hibor |
| north_net, south_net | fund_flow |
| ted_spread, sofr | ted_spread |
| gold, silver, oil, copper | commodities |
| hk_hsi, sh_000001, spx, ixic, dji | indices |

响应仍是 `EconomicDataResponse` 子集（给 `extractSeries` 用），不要另造一套扁平 map。默认四指标含美债时日期轴仍是美债交易日（见 §2.3）；不含美债的指标组合才用所选 section 并集。

`tab` + `indicators`：仅 `comparison` 接受 indicators；其它 tab 带 indicators → 400。

### 2.3 日期轴（相对现状的变化）

现状：几乎所有 Tab 的 `TAB_SECTIONS` 都塞了 `us_treasuries`，`result["dates"]` 来自美债。

落地规则：`_query_data_impl` 在 **sections 含 `us_treasuries` 且美债 CSV 非空** 时仍用美债交易日；否则用已 load CSV 的 index 并集。禁止无美债时 `date_range(start, end)` 填自然日。

| Tab | dates |
|-----|--------|
| treasury-exchange | 美债交易日（本 Tab 展示美债） |
| rates | 美债交易日（本 Tab 含 us_treasuries；未改成四段并集） |
| liquidity-risk | vix ∪ tga ∪ hibor |
| commodities | commodities |
| stock-indices | indices |
| market-sentiment | volume ∪ turnover ∪ margin |
| comparison | 所选 section 含美债时用美债交易日；否则用这些 section 的并集 |

HTTP 的 comparison 只走 `query_data_by_indicators`。`query_data_by_tab("comparison")` 直接拒绝，避免 `TAB_SECTIONS None` 全量脚枪。

### 2.4 错误

| 情况 | HTTP | body |
|------|------|------|
| 未知 tab（含 bonds, macro-signal） | 400 | detail 列出合法 tab |
| comparison 无 indicators | 400 | 说明必填 |
| 未知 indicator id | 400 | 指出非法 id |
| CSV 空 | 200 | dates=[]，序列空数组 |

## 3. 前端数据流

```
page.tsx
  useTabEconomicData(activeTab, refreshKey, comparisonIndicators?)
    → 非 comparison：GET /data/{tab}（内存命中则跳过）
    → comparison：GET /data/comparison?indicators=...
  tabDataMap[tab] 或 comparisonCache[sortedIds]
    → 各 *Tab fullData + isLoading
  useFilteredEconomicData(fullData, timeRange) 本地切片
```

对比的 `selectedIds` 存在 ComparisonTab。两种接法：

- **推荐**：`ComparisonTab` 自己调 `economicApi.getComparisonData`，page 不再给 comparison 塞全量 `tabDataMap['comparison']`。page 的 hook 对 `activeTab==='comparison'` 不发 `/data/comparison` 全量请求。
- 不推荐：把 selectedIds 抬到 page，hook 参数膨胀。

内存缓存：

```
type CacheEntry = { data: EconomicDataResponse; fetchedAt: number }
tabCache: Map<ChartTabType, CacheEntry>     // 不含 comparison
comparisonCache: Map<string, CacheEntry>    // key = sorted ids join
TTL = 5 * 60 * 1000
```

`refreshKey` 变：只清当前 Tab（或当前 indicators key）。

删除 `TAB_CACHE_KEY_PREFIX` localStorage 读写。

## 4. Loading

新建 `TabPanelLoading`：相对定位容器内居中转圈 + 文案，高度约 700px，与图区一致。`isLoading` 时渲染它，不渲染图。`TreasuryExchangeTab` 去掉全屏 `LoadingOverlay`。

## 5. 兼容与回滚

- 无 tab 的 `GET /data` 行为不变。
- 旧前端若仍打 `/data` 总包，继续可用。
- 回滚：revert 本任务 commits；骨架 `/data/{tab}` 可留。

## 6. 风险

| 风险 | 处理 |
|------|------|
| 对比切指标频繁请求 | 子集命中缓存；最多 6 个 id |
| 并集日期轴让稀疏序列出现大量 null | Plotly `connectgaps: false` 已有 |
| `get_data_by_tab` 改 def | 与 `get_data` 相同，避免堵 loop |
| rates 加 us_treasuries 后 payload 变大 | 可接受，只多一条 3m/2y/10y |
