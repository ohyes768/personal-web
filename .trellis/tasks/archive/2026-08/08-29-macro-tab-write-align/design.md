# 技术设计：各 Tab init/update 指标与成败规则对齐

## 1. 模块边界

只改前端写入聚合。后端端点、锁、调度、读数 API、图表组件都不动。

| 层 | 动作 |
|----|------|
| `apps/macro/src/lib/modules/economic/api.ts` | 抽取串行 POST helper；按 PRD R1 改六个聚合函数的路径清单与顺序 |
| 六个 `*Tab.tsx` | 只改 `hasData`（R3）；`onInit` / `onRefresh` 绑定保持现有函数名 |
| `.trellis/spec/backend/global-macro-fin/backend/data-sources.md` | Phase 3 补一句：所有多端点数据 Tab 都串行，不只市场情绪 |

不改：`InitButton.tsx` / `RefreshButton.tsx` 组件契约、`routes.py`、`scheduler.json`、`page.tsx` 读数。

## 2. 契约

### 2.1 串行 helper

`api.ts` 内部函数（不导出或仅测导出，按仓库现状不强制单测）：

```ts
async function postSerial(paths: readonly string[]): Promise<UpdateResponse> {
  let last: UpdateResponse | undefined;
  for (const path of paths) {
    const res = await directClient.post<UpdateResponse>(path);
    if (!res.success) return res;
    last = res;
  }
  if (!last) {
    return { success: false, message: 'empty serial post list' };
  }
  return last;
}
```

规则：空列表视为失败（防御）；任一步失败立即返回该步 `UpdateResponse`；全部成功返回最后一步响应（按钮只看 `success`）。

六个聚合函数变成路径表 + `postSerial`，禁止再手写 `Promise.all` 和 `a.success || b.success`。

### 2.2 路径表（与 PRD R1 相同，实现以本表为准）

```ts
initHistory: [
  '/api/macro/fetch/us-treasuries/history',
  '/api/macro/fetch/exchange-rates/history',
  '/api/macro/fetch/china-bonds/history',
]
updateUsTreasuriesAndRates: [
  '/api/macro/update/us-treasuries',
  '/api/macro/update/exchange-rates',
  '/api/macro/update/china-bonds',
]
initRatesHistory: [
  '/api/macro/fetch/china-bonds/history',
  '/api/macro/fetch/ted-spread/history',
  '/api/macro/fetch/dr007/history',
  '/api/macro/fetch/us-treasuries/history',
]
updateRates: [
  '/api/macro/update/china-bonds',
  '/api/macro/update/ted-spread',
  '/api/macro/update/dr007',
  '/api/macro/update/us-treasuries',
]
initLiquidityHistory: [
  '/api/macro/fetch/vix/history',
  '/api/macro/fetch/tga/history',
  '/api/macro/fetch/hibor/history',
]
updateLiquidity: [
  '/api/macro/update/vix',
  '/api/macro/update/tga',
  '/api/macro/update/hibor',
]
```

商品、股指仍单次 `directClient.post`。市场情绪三/四步改为走 `postSerial`，路径不变。

重叠写入：中债 history/update 被中美利差和利率两边调用；美债被两边调用。CSV `keep=last` / 增量追加，重复跑安全。并发两个 Tab 按钮仍可能撞全局锁——UI 没有同时点两个 Tab 的入口（同一时刻只显示一个 Tab），可接受。

### 2.3 hasData

全部改为读 `fullData`，不读 `useFilteredEconomicData` 的切片。避免短时间范围把「已初始化」打成 false 或 true 的误判。表达式见 PRD R3。

利率 Tab 现状用切片后的 `data` 且 `ted OR china`，必须改。中美利差现状用切片 `dates.length`，必须改成美债+汇率+中债 AND。市场情绪现状 `volume OR turnover OR fund_flow`，改成 volume AND turnover AND north_deal_amount。

## 3. 数据流

```
用户点初始化/更新
  → InitButton / RefreshButton
  → economicApi.<tabFn>
  → postSerial(paths)  // 或单次 post
       每步 POST /api/macro/fetch|update/...
       后端 _is_updating：一步完成才释放，下一步才能进
  → 任一步失败：按钮保持可点，展示 message
  → 全成功：localStorage 置灰 + onSuccess → refreshKey++ → GET /data/{tab}
```

## 4. 权衡

- **不拆全局锁、不新增 Tab 级后端聚合**：前端串行已满足「不撞锁 + 全部成功」；改锁影响调度 self-call，超出本任务。
- **重叠 CSV 两边都写**：满足「单 Tab 可独立初始化」；多打几次幂等请求，可接受。
- **利率初始化 4 个 history 可能很慢**：InitButton 已有「初始化中...」直到返回；不加重试/超时 UI。
- **抽取 postSerial 而不是复制 6 份 for 循环**：spec `code-reuse-thinking-guide.md` 明确禁止再抄流动性的 `Promise.all`。

## 5. 兼容与回滚

- 读数 API、CSV 列、调度路径不变。
- 已置灰的 localStorage key 不改名：用户若以前「假成功」置灰，需手动 `localStorage.removeItem`（InitButton 已有 title 提示）。本任务不迁移旧 key。
- 回滚：还原 `api.ts` 与六个 Tab 的 `hasData`。

## 6. 风险

- 中美利差初始化新增长债 history，首次点击耗时增加。
- 利率初始化新增美债+DR007 history，若美债 history 已存在，后端应覆盖/合并而非报错（沿用现有 fetch 行为，实现时对空 CSV 与已有 CSV 各看一眼文档，不改后端）。
- `08-29-macro-hsgt-fund-flow` 若未合入，市场情绪路径以当前工作区 `api.ts` 为准（已含 fund-flow）；本任务不回退该链。
