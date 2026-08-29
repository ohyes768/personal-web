# 数据 Tab 写入对齐 — 实现清单

## 顺序

### 1. Helper + 美债（AC1–AC4）

`routes.py`：`_has_observations`、`_empty_increment_is_current`。`_fetch_us_treasuries` 去掉 per-series except。`update_us_treasuries` 走 helper。

### 2. 其余 R1 增量（AC8–AC9）

`exchange-rates`、`china-bonds`、`vix`、`tga`、`hibor`、`ted-spread`、`commodities`、`indices` 的 `if empty: raise` 换成 helper。TED 两段 empty 合并。

`fred_service.py`：`fetch_exchange_rates` 不再吞异常。

### 3. 前端 `postSerial` + 完整路径表（AC5–AC6、AC10、AC12）

`api.ts` 增加 `postSerial`。按 PRD R3 改：

- `initHistory`：美债 → 汇率 → **中债** history
- `updateUsTreasuriesAndRates`：美债 → 汇率 → 中债 update
- `initRatesHistory` / `updateRates`：中债 → TED → **DR007** → **美债**
- `initLiquidityHistory` / `updateLiquidity`：VIX → TGA → HIBOR
- 市场情绪两条：现有顺序，改走 `postSerial`
- 商品/股指：单次 post

`economicApi` 内禁止再对 `/fetch` `/update` 用 `Promise.all` 或「任一成功」。

验证：

```bash
rg "Promise.all" apps/macro/src/lib/modules/economic/api.ts
rg "任一成功" apps/macro/src/lib/modules/economic/api.ts
rg "fetch/china-bonds/history|fetch/dr007/history|update/dr007" apps/macro/src/lib/modules/economic/api.ts
```

### 4. 六个 Tab 的 hasData（AC13）

- `TreasuryExchangeTab`：`fullData` 美债 10Y ∧ 美元指数 ∧ 中国 10Y
- `RatesTab`：`fullData` DR007 ∧ TED ∧ 中国 10Y ∧ 美债 3M
- `LiquidityTab` / `CommodityTab` / `StockIndexTab`：改读 `fullData`
- `MarketSentimentTab`：volume ∧ turnover ∧ `fund_flow.north_deal_amount`

验证：`rg "hasData=" apps/macro/src/app/modules/economic/components/*Tab.tsx`

### 5. 测试（AC11）

`backend/macro/tests/test_incremental_empty.py`：

- 美债：有 last_date + 空观测 → 已是最新；抛 `RuntimeError("fred down")` → message 含原文；无 CSV + 空 → 失败
- 参数化 R1 其余端点各一条有 last_date + 空观测

不真连外网。`os.environ.setdefault("FRED_API_KEY", "test-not-a-real-key")`。

### 6. 文档（AC11）

《数据更新端点规范》：空窗条款、禁止吞异常。`data-sources.md`：六个数据 Tab 多端点必须串行，表列 PRD R3 路径。

## 验证

```bash
cd backend/macro
python -m pytest tests/test_incremental_empty.py -v
rg "Promise.all" ../../apps/macro/src/lib/modules/economic/api.ts
cd ../../apps/macro && pnpm exec tsc --noEmit
```

浏览器（有密钥则真点，否则看 Network 形态）：

- 中美利差初始化：按序 3 个 history（含中债）；更新串行；空窗成功则「下次更新」
- 流动性：更新串行；全成功后「下次更新」
- 利率初始化：按序 4 个 history；成功后图上有 DR007、美债 3M
- 商品或股指：单请求；若 CSV 已有且源空窗则 success 置灰
- 信号首页、对比无写数按钮
- 中途失败（停后端）：按钮不置灰

## 风险文件

- `routes.py`：勿改 save 列名、资金流向 10 日窗、china-bonds 的 `>=` 短路
- `api.ts`：所有写数入口；只动写入聚合，不改 `getTabData`
- 六个 `*Tab.tsx` 的 `hasData`：误用切片会让按钮误亮或永远置灰

与进行中任务：`08-29-macro-hsgt-fund-flow` 市场情绪链已含 fund-flow，本任务不回退；`08-29-macro-chart-readability` 不碰图表；`08-28-macro-per-tab-data` 不碰读数 hook。

## 回滚

还原上述代码与文档。无 CSV 迁移。

## `task.py start` 前检查

- [x] 已与 `08-29-macro-tab-write-align` 合并
- [ ] 用户确认规划后才 `python ./.trellis/scripts/task.py start 08-29-macro-us-treasury-empty-update`
