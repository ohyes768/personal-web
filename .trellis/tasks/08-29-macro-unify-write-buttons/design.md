# 宏观页数据 Tab 写入 UX 统一 — 技术设计

> 与 [prd.md](./prd.md) 配套。R7 路径改名已在规划阶段落地，实现阶段以前端接线为主。

## 1. 模块边界

### 已改（R7）

| 文件 | 改动 |
|------|------|
| `backend/macro/src/api/routes.py` | `POST /fetch/volume-turnover/history`，函数 `fetch_volume_turnover_history`；旧 `/update/volume-turnover/history` 删除 |
| `backend/macro/src/services/baostock_service.py` | 注释路径更新 |
| `backend/macro/docs/数据更新端点规范.md` | 清单 + 变更记录 |
| `.trellis/spec/backend/global-macro-fin/backend/data-sources.md` | 契约路径更新 |

### 前端 — 修改

| 文件 | 改动 |
|------|------|
| `apps/macro/src/app/modules/economic/components/InitButton.tsx` | 增加 `onSuccess?`，成功后调用（与 RefreshButton 对齐） |
| `apps/macro/src/lib/modules/economic/api.ts` | `initMarketSentimentHistory` + `updateMarketSentiment`（串行三 update） |
| `apps/macro/src/app/modules/economic/components/MarketSentimentTab.tsx` | 接 InitButton + RefreshButton；去掉「无需手动刷新」 |
| `apps/macro/src/app/modules/economic/page.tsx` | 向 MarketSentimentTab 传 `refreshKey` / `onRefreshSuccess` |
| 五个已有数据 Tab | 文案统一为「初始化历史数据」/「更新数据」；InitButton 补 `onSuccess` |

不新建按钮组件。不改信号首页、对比、BaoStock 取数、调度 JSON。

## 2. 契约

### 2.1 市场情绪初始化

```
POST /api/macro/fetch/volume-turnover/history
```

后端 query 默认 `start_date=2010-01-01`、`end_date=昨天`。前端 POST 空 body 即可，不传 query。

响应：现有 `UpdateResponse`（`success` / `message`）。`directClient` 直读该 JSON。

### 2.2 市场情绪更新（串行）

```
POST /api/macro/update/volume
POST /api/macro/update/turnover
POST /api/macro/update/margin
```

顺序固定。任一步 `success === false` 或抛错 → 整体失败，不置灰。三步都成功才 `success: true`。

原因：`routes.py` 全局 `_is_updating`，并发会得到 `UPDATE_IN_PROGRESS`。

### 2.3 按钮契约（不变）

- Init：`storageKey` 独立；成功永久置灰；`hasData` 兜底。
- Refresh：`cadence="daily"`；成功置灰到明天本地 00:00。

市场情绪 `storageKey`：

- 初始化：`last_initialized_macro_market_sentiment`
- 更新：`last_updated_market_sentiment_daily`

`hasData`：`!!(fullData?.volume?.length || fullData?.turnover?.length)`（用全量 props，不被当前时间范围切片误判）。

## 3. 数据流

```
用户点初始化
  → InitButton.onInit
  → POST /fetch/volume-turnover/history
  → 成功：localStorage + onSuccess → page refreshKey++
  → useTabEconomicData 重拉 /api/macro/data/market-sentiment

用户点更新
  → RefreshButton.onRefresh
  → volume → turnover → margin（await 串行）
  → 成功：localStorage + onSuccess → 同上重拉
```

## 4. 复用 / 不复用

复用：`InitButton`、`RefreshButton`、`economicApi` + `directClient`、页级 `onRefreshSuccess`。

不复用：流动性 Tab 的 `Promise.all` +「任一成功」（会撞锁）。不把三个 update 合成一个后端端点。

## 5. 兼容与回滚

- 旧 `/update/volume-turnover/history` 已 404。调度只打 `/update/volume|turnover`，不受影响。
- 回滚前端：还原 MarketSentimentTab / InitButton / 文案即可。
- 回滚路径改名：把 decorator 改回旧路径（不推荐；规范要求 `/fetch/`）。

## 6. 风险

- 历史回补可能数十秒：InitButton 保持「初始化中...」直到返回。
- 融资余额无 history：初始化后 margin 曲线仍可能很短（PRD 接受）。
