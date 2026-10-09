# Design — 按 Tab 拆分宏观数据 API

## API

```
GET /api/data/{tab}
  tab: treasury-exchange | bonds | liquidity-risk | rates | comparison | commodities | stock-indices
  Query: start_date?, end_date?  （缺省 → historical_start_date ~ today）

Response: 同 DataResponse { success, message, data: Partial<EconomicDataResponse> }
```

无效 tab → HTTP 400。

## 后端

`data_service.py`:

- `TAB_SECTIONS: Dict[str, Optional[Set[str]]]` — `comparison` 为 `None` 表示全量。
- `_query_data_impl(..., sections: Optional[Set[str]] = None)` — 各 CSV 块外包 `if sections is None or "xxx" in sections`。
- `query_data_by_tab(tab, start_date, end_date)` — 校验 tab、解析 sections、走缓存。

`routes.py`:

- `@router.get("/data/{tab}")` 新路由；原 `/data` 调 `query_data()` 不变。

## 前端

- 新 hook `useTabEconomicData(activeTab, refreshKey)`：
  - `tabDataCache: Record<string, EconomicDataResponse>`
  - `activeTab` 变化且缓存未命中 → `economicApi.getTabData(tab)`
  - `refreshKey` 变化 → 清该 tab 缓存并重拉
- `page.tsx` 替换 `useFullEconomicData`；各 Tab 从 cache 取 `fullData`。
- `economicApi.getTabData(tab, startDate?)` → `GET /api/macro/data/{tab}`

## 兼容

- nginx 剥 `/api/macro` 前缀规则不变。
- 旧 `/api/data` 保留供脚本/调试。
