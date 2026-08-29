# 宏观页数据 Tab 写入 UX 统一 — 实现清单

## 顺序

### 0. R7 路径（已完成）

- [x] `POST /fetch/volume-turnover/history`；旧 `/update/volume-turnover/history` 删除
- [x] 规范文档 + data-sources.md

验证：`rg "update/volume-turnover/history" backend/macro --glob '!**/archive/**'` 应无代码命中。

### 1. InitButton 补 onSuccess

`InitButton.tsx`：props 加 `onSuccess?: () => void`；`res.success` 分支里调 `onSuccess?.()`（照 RefreshButton）。

五个数据 Tab + 市场情绪的 InitButton 都传 `onSuccess={onRefreshSuccess}`。

### 2. economicApi

- `initMarketSentimentHistory`：`directClient.post('/api/macro/fetch/volume-turnover/history')`
- `updateMarketSentiment`：串行 post volume → turnover → margin；第一步失败即返回该响应

### 3. MarketSentimentTab + page.tsx

- 加 `refreshKey` / `onRefreshSuccess` props（refreshKey 可只为对齐其它 Tab 签名）
- Init + Refresh，文案「初始化历史数据」/「更新数据」
- 去掉盘后调度旁注
- `page.tsx` 传入 `onRefreshSuccess={handleRefreshSuccess}`

### 4. 五个 Tab 文案

一律：`label="初始化历史数据"`、`label="更新数据"`。

涉及：TreasuryExchangeTab、LiquidityTab、RatesTab、CommodityTab、StockIndexTab。

### 5. 验证

```bash
rg "fetch/volume-turnover/history" backend/macro/src/api/routes.py
rg "update/volume-turnover/history" backend/macro/src --glob "*.py"
rg "初始化历史数据" apps/macro/src/app/modules/economic/components
rg "InitButton|RefreshButton" apps/macro/src/app/modules/economic/components/MacroSignalTab.tsx
rg "InitButton|RefreshButton" apps/macro/src/app/modules/economic/components/ComparisonTab.tsx
```

浏览器（`scripts/start-macro-dev.bat` 若已起）：

- 六个数据 Tab 都有两个按钮；信号首页、对比没有
- 市场情绪初始化请求 `/fetch/volume-turnover/history`
- 更新串行三条 `/update/volume|turnover|margin`
- 初始化成功后图表重拉（loading）

## 风险文件

- `page.tsx`：与 `08-28-macro-per-tab-data` 可能冲突，只加 props，不改读数 hook
- `InitButton.tsx`：六个 Tab 共用，onSuccess 必须可选

## 回滚

还原上述前端文件；R7 路径改名可单独保留。
