# 数据 Tab 写入对齐 — 技术设计

合并原 `08-29-macro-tab-write-align` 的前端路径表与 hasData。

## Boundaries

- **In**：`routes.py` 空窗 helper + 列出的 `update_*`；`_fetch_us_treasuries` / `FredService.fetch_exchange_rates` 异常上抛；`apps/macro/.../economic/api.ts` 抽 `postSerial` 并按 PRD R3 路径表改所有数据 Tab 的 init/update；六个 `*Tab.tsx` 的 `hasData`；规范与 `data-sources.md`。
- **Out**：n8n `POST /api/macro/update`、欧债/日债月度、资金流向 10 日窗、`RefreshButton`/`InitButton` 组件、信号首页、对比、图表布局、读数 hook、调度 JSON。

## Backend helper

```python
def _has_observations(data) -> bool:
    """dict[str, Series] 或 Series：任一 last_valid_index 非空。"""

def _empty_increment_is_current(data_service, data_type: str) -> bool:
    return data_service.get_last_date(data_type) is not None
```

拉数之后：无观测且有 last_date → success「已是最新」；无观测且无底库 → 仍 raise。有观测则现有 save。

R1 端点：us-treasuries、exchange-rates、china-bonds、vix、tga、hibor、ted-spread、commodities、indices。

china-bonds 保留 `start >= latest_end` 短路；空窗 helper 覆盖「start < today 但接口当天没数」。

## Exception propagation

| 路径 | 改为 |
|------|------|
| `_fetch_us_treasuries` | 不捕获，retry 耗尽上抛 |
| `FredService.fetch_exchange_rates` | 不捕获；单系列失败则整次失败 |
| VIX/TGA/TED/HIBOR | 失败已上抛；空 Series 走 helper |

## Frontend `postSerial`

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

六个聚合函数走路径数组 + `postSerial`。商品/股指保持单次 `post`。`economicApi` 内对 fetch/update 的 `Promise.all` 清零。

路径表以 PRD R3 为准。相对合并前空窗任务的增量：

- `initHistory` 追加 `/fetch/china-bonds/history`
- `initRatesHistory` / `updateRates` 追加 DR007 与美债（history / update）

重叠写入：中债、美债被中美利差和利率两边调用；CSV 增量幂等。同一时刻只显示一个 Tab，两个按钮不会并行。

未再被 Tab 使用的单指标函数（如 `initVIXHistory`）本任务不删。

## hasData

全部改为读 `fullData`，表达式见 PRD R4。利率现状用切片 `data` 且 `ted OR china`，必须改。中美利差现状用切片 `dates.length`，必须改成三线 AND。市场情绪现状 OR，改成 volume ∧ turnover ∧ north_deal_amount。

## Compatibility

- HTTP 200 + `UpdateResponse`；调度按 `body.success`。空窗 failed→success 是要的。
- 空窗不 `save_*`。
- `error_code` 仍仅 `UPDATE_FAILED` / `UPDATE_IN_PROGRESS`。
- localStorage key 不改名。

## Tradeoffs

- 商品/股指纳入空窗：周末/休市阿里云全空与 FRED 同形，不改会让这两个 Tab 按钮同样不置灰。
- 资金流向不纳入：`fetch_recent(days=10)` 空批更像源挂了，不是「已是最新」。
- 不拆全局锁、不新增 Tab 级后端聚合：前端串行已满足不撞锁。
- 利率初始化 4 个 history 可能很慢：InitButton 已有「初始化中...」。
- n8n 综合端点仍单独任务（OECD 与美债混在一个 dict）。

## Rollback

还原 `routes.py`、`fred_service.py`、`api.ts`、六个 Tab 的 `hasData` 与两份文档。无 CSV 迁移。
