# 宏观页按 Tab 拆读数 — Implementation Plan

> **For agentic workers:** 按本清单顺序做。先测后改。完成一步再做下一步。不要 `task.py start` 除非用户已审过本文与 prd/design。

**Goal:** 业务 Tab 只打 `/api/macro/data/{tab}`；对比按 `indicators` 按需拉；各 Tab 独立日期轴；内存 5min 缓存；Tab 内 loading。

**Architecture:** 扩现有 `query_data_by_tab` / `useTabEconomicData`，不新开一套 REST。对比请求下沉到 `ComparisonTab`。dates 改为该 Tab CSV 并集，不再为情绪 Tab 偷读美债。

**Tech Stack:** FastAPI, pandas, Next.js 15, React 19

---

## 文件地图

| 路径 | 职责 |
|------|------|
| `backend/macro/src/services/data_service.py` | TAB 映射、无美债时日期并集、indicators 查询；`query_data_by_tab("comparison")` 拒绝 |
| `backend/macro/src/api/routes.py` | `/data/{tab}` 改 def；comparison 校验 indicators |
| `backend/macro/tests/test_query_data_by_tab.py` | 契约单测 |
| `apps/macro/src/lib/modules/economic/api.ts` | `getComparisonData` |
| `apps/macro/src/lib/hooks/useTabEconomicData.ts` | 去 localStorage、5min TTL、comparison 不走全量 |
| `apps/macro/src/lib/hooks/useFilteredEconomicData.ts` | 去掉 ALL 档「首日 > 2020 当未加载完」守卫（短序列 Tab 否则空图） |
| `apps/macro/src/app/modules/economic/components/ComparisonTab.tsx` | 自拉 indicators；`isActive` 才请求；其它 Tab 的 `refreshKey` 不清对比缓存 |
| `apps/macro/src/app/modules/economic/components/TabPanelLoading.tsx` | Tab 内 loading |
| `apps/macro/src/app/modules/economic/components/MarketSentimentChart.tsx` | `yaxis2.overlaying: 'y'` |
| 各 `*Tab.tsx` | 换 loading 组件 |
| `apps/macro/src/app/modules/economic/page.tsx` | comparison 不再传全量 fullData |

---

## Step 1 — 后端日期轴 + 字段表（TDD）

**Verify 先红：** 在 `test_query_data_by_tab.py` 增加（用 tmp_path 或现有 data 目录）：

1. `market-sentiment` 的 `dates` 等于 volume/turnover/margin 有值日期的并集，且结果 **没有** `us_treasuries` 键
2. `rates` 结果 **有** `us_treasuries`
3. 构造只有 2 天 volume 的 fixture 时，`dates` 长度为 2，不是美债日历长度

**改 `data_service.py`：**

- `TAB_SECTIONS["market-sentiment"]` 去掉 `us_treasuries`
- `TAB_RESPONSE_FIELDS["rates"]` 加上 `us_treasuries`
- 抽取 `_union_index(*dataframes) -> DatetimeIndex`
- `_query_data_impl`：当 `sections` 不含 `us_treasuries` 时，**不要**用 `pd.date_range(start, end)` 当 target；用该 Tab 已 load 的 CSV index 并集
- `query_data_by_tab` 在 filter 之前把 `result["dates"]` 设成该并集

**Verify：** `cd backend/macro && .venv/Scripts/python -m pytest tests/test_query_data_by_tab.py -v`

**Rollback：** 还原 TAB_* 常量和 `_query_data_impl` 的 target_index。

---

## Step 2 — 对比 indicators 查询（TDD）

**先写测：**

- `query_data_by_indicators(["dxy","us_10y","vix","gold"])` 响应含 exchange_rates / us_treasuries / vix / commodities，不含 indices
- 未知 id 抛 ValueError
- 空列表抛 ValueError

**实现：**

- 模块级 `INDICATOR_SECTIONS: dict[str, str]`（与 design.md 表一致）
- `query_data_by_indicators(ids, start, end)` → sections 并集 → `_query_data_impl` → 按 TAB_RESPONSE 思路裁剪到这些 section + dates
- `routes.get_data_by_tab`：若 `tab=="comparison"`，解析 `indicators` Query；无或空 → 400；否则走 `query_data_by_indicators`
- handler 从 `async def` 改为 `def`（与 `get_data` 相同）

**Verify：**

```
pytest tests/test_query_data_by_tab.py -v
# 后端起来后：
curl -s "http://127.0.0.1:8094/api/data/comparison"  # 期望 400
curl -s "http://127.0.0.1:8094/api/data/comparison?indicators=dxy,vix" | 只含相关键
curl -s "http://127.0.0.1:8094/api/data/market-sentiment?start_date=2026-08-01"
```

**Rollback：** 删除 indicators 分支，comparison 恢复 `TAB_SECTIONS None`（不推荐长期留）。

---

## Step 3 — 前端 API + 缓存

**改 `api.ts`：** `getComparisonData(ids: IndicatorId[])` → `GET /api/macro/data/comparison?indicators=a,b&start_date=2000-01-01`

**改 `useTabEconomicData`：**

- 删除 `readTabCache` / `writeTabCache` / `CACHE_TTL_MS=3600000`
- 内存 entry 带 `fetchedAt`，超过 5min 视为未命中
- `activeTab === 'comparison'`：**不请求**（避免再打无 indicators 的 comparison）
- `refreshKey` 只清当前 tab 的内存 entry

**改 `page.tsx`：** ComparisonTab 不再传 `tabDataMap['comparison']`（传 null 或让子组件自管）。`isLoading` 对 comparison 为 false（由子组件自己的 loading 负责）。

**Rollback：** 恢复 localStorage 与 comparison 走 `getTabData('comparison')`。

---

## Step 4 — ComparisonTab 按需拉 + loading

**改 `ComparisonTab.tsx`：**

- 内部 `useEffect`：`selectedIds`（空则用 `DEFAULT_INDICATORS`）变化时请求
- key = `[...ids].sort().join(',')`
- 若新 key 是已缓存 key 的子集且未过 TTL，切片或直接用缓存（实现选：子集则不请求，`extractSeries` 缺的字段本来就不会画）
- 超集：请求完整新列表，loading true
- 内容区用 Step 5 的 `TabPanelLoading`

**Verify：** 打开对比 Tab，Network 只有带默认四指标的一条；再勾选 copper 多一条；去掉 copper 无新请求。

---

## Step 5 — TabPanelLoading

**新建** `TabPanelLoading.tsx`：容器 `h-[700px]`，CSS 转圈 + `message`。

各 Tab（TreasuryExchange / Liquidity / Rates / Commodity / StockIndex / MarketSentiment / Comparison）在 `isLoading` 时渲染该组件；TreasuryExchange **去掉** `LoadingOverlay`。

文案：「加载{中文名}数据中…」

---

## Step 6 — 全页核对

- `pnpm --filter` 或 `cd apps/macro && pnpm build`（类型：`getTabData` 的 tab union 不含 comparison 也可，comparison 走新方法）
- `ChartTabType` 若仍含 comparison，page 的 hook 对它 no-op 即可
- 市场情绪：切过去应看到 2 天量级的线（本地 CSV 若存在）

---

## 验证命令

```bash
cd backend/macro
.venv/Scripts/python -m pytest tests/test_query_data_by_tab.py -v

cd apps/macro
pnpm build
```

浏览器（需 8094 + 3001）：

1. 打开 `/macro`，Network 仅 `treasury-exchange`
2. 切市场情绪，仅 `market-sentiment`，图上能看到点
3. 切利率，有美债 3M
4. 切对比，URL 含 `indicators=`
5. 切回中美利差，5 分钟内无新请求
6. 首次进入有转圈，顶栏可点

## 风险文件 / 回滚点

| 步骤 | 回滚 |
|------|------|
| 1 | data_service TAB_* 与 dates 逻辑 |
| 2 | routes comparison 分支 |
| 3–4 | useTabEconomicData + ComparisonTab |
| 5 | Tab loading 组件 |

## `task.py start` 前检查

- [ ] prd / design / 本文无 TBD
- [ ] implement.jsonl / check.jsonl 已有真实 spec 条目
- [ ] 用户已看过方案（query 改成已落地的 path 参数）
