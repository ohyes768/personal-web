# 实施清单：各 Tab init/update 对齐

## 顺序

### 1. `postSerial` + 改聚合函数

文件：`apps/macro/src/lib/modules/economic/api.ts`

- [ ] 增加内部 `postSerial`（design §2.1）。
- [ ] `initHistory` / `updateUsTreasuriesAndRates` / `initRatesHistory` / `updateRates` / `initLiquidityHistory` / `updateLiquidity` / `initMarketSentimentHistory` / `updateMarketSentiment` 全部改为路径数组 + `postSerial`。
- [ ] 商品、股指保持单次 POST。
- [ ] 删除所有 `Promise.all` 与「任一成功即视为成功」注释/逻辑。
- [ ] 未再被 Tab 使用的 `initVIXHistory` 等单指标函数：本任务不删（可能无调用方）；若确认无引用可留着，不扩大 diff。

验证：

```bash
rg "Promise.all" apps/macro/src/lib/modules/economic/api.ts
rg "任一成功" apps/macro/src/lib/modules/economic/api.ts
rg "fetch/dr007/history|update/dr007|fetch/china-bonds/history" apps/macro/src/lib/modules/economic/api.ts
```

`Promise.all` 与「任一成功」应为 0 命中。`initRatesHistory` 含 dr007 + us-treasuries；`initHistory` 含 china-bonds。

### 2. 六个 Tab 的 hasData

- [ ] `TreasuryExchangeTab.tsx`：`fullData` 上美债 10Y ∧ 美元指数 ∧ 中国 10Y。
- [ ] `RatesTab.tsx`：`fullData` 上 DR007 ∧ TED ∧ 中国 10Y ∧ 美债 3M。
- [ ] `LiquidityTab.tsx`：改读 `fullData`（表达式保持 VIX∧TGA∧HIBOR）。
- [ ] `CommodityTab.tsx` / `StockIndexTab.tsx`：改读 `fullData` 的 gold / SPX。
- [ ] `MarketSentimentTab.tsx`：volume ∧ turnover ∧ `fund_flow.north_deal_amount`。

验证：`rg "hasData=" apps/macro/src/app/modules/economic/components/*Tab.tsx` 六处都指向 `fullData` 或由其派生的未切片字段。

### 3. 静态检查

```bash
cd apps/macro && pnpm exec tsc --noEmit
```

（或仓库惯用的 `pnpm build`；实现时用能跑通的那条。）

### 4. 浏览器（macro 开发服务已起时）

- [ ] 利率利差：点初始化，DevTools 按序 4 个 history，无并行；成功后图上有 DR007、美债 3M。
- [ ] 中美利差：点初始化，按序 3 个 history（含中债）。
- [ ] 人为让第二步失败（停后端或断网于中途）：按钮不置灰。
- [ ] 信号首页、对比仍无这两个按钮。
- [ ] 商品/股指/流动性/市场情绪按钮仍在，单端点或串行行为不回退。

若开发服务未起：用 `scripts/start-macro-dev.bat`；AC8 在实现阶段补浏览器验证，规划阶段不阻塞 `task.py start`。

## 风险文件

- `apps/macro/src/lib/modules/economic/api.ts`：所有写数入口，改错会影响六个 Tab。
- 六个 `*Tab.tsx` 的 `hasData`：误用切片数据会让已初始化按钮重新亮起或永远置灰。

与进行中任务：

- `08-29-macro-hsgt-fund-flow`：市场情绪链已含 fund-flow，本任务只换成 `postSerial`，不改路径。
- `08-29-macro-chart-readability`：不碰图表组件。
- `08-28-macro-per-tab-data`：不碰读数 hook。

## 回滚

还原 `api.ts` 与六个 Tab 的 `hasData` 即可。无 CSV 迁移、无后端契约变更。

## `task.py start` 前检查

- [x] `prd.md` 有可测 AC
- [x] `design.md` / `implement.md` 已写
- [ ] 用户确认规划后才 `python ./.trellis/scripts/task.py start 08-29-macro-tab-write-align`
