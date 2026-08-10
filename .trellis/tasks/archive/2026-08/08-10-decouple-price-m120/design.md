# Design — 行情价与M120解耦

## 现状数据流(改造前)

```
前端挡位监控 bar
   └─ currentPrice = technicalData[code].realtime ?? .close
      └─ useTechnicalData → GET /api/dividend/m120
         └─ m120_service.read_m120_with_deviation()
            ├─ 读 M120均线_<周>.csv  ← 主表(缺失则 return {})
            └─ 读 实时价格.csv        ← 被 join 进 M120 主表
                                        M120 缺失 → 现价一起消失
```

## 改造后数据流

```
前端挡位监控 bar
   └─ currentPrice = priceMap[code].realtime ?? .close
      └─ useRealtimePrices(alertCodes) → GET /api/dividend/prices
         └─ m120_service.read_prices_only()
            └─ 读 实时价格.csv  ← 独立主表，不依赖 M120

前端其他(DividendTable/对比/报告/CSV)
   └─ 仍走 technicalData → GET /api/dividend/m120  ← 不动
```

## 接口契约

`GET /api/dividend/prices?codes=<逗号分隔,可选>`

```jsonc
// PriceListResponse
{
  "total": 12,
  "items": [
    {
      "code": "000922",
      "close": 5.23,        // 昨日收盘(可 null)
      "realtime": 5.31,     // 实时价格(可 null)
      "pe": 8.2,            // 静态PE(可 null)
      "pb": 0.95,           // 市净率(可 null)
      "yield_ttm": 5.42     // 实时股息率TTM(可 null)
    }
  ],
  "last_updated": "2026-08-10T15:05:00"  // 实时价格 CSV mtime(可 null)
}
```

- `codes` 缺省 → 返回实时价格 CSV 全部股票。
- `codes` 给定 → 仅返回这些 code(挡位监控场景，几只~几十只)。
- `yield_ttm` 计算复用 m120 endpoint 现有逻辑(需主 CSV「近5年分红详情」+ calculator)。

## 后端改动点 (backend/dividend-select)

### 1. `services/m120_service.py`
- 抽取私有方法 `_read_price_csv() -> dict[str, dict]`：把 `read_m120_with_deviation()` 现有 line 432-466 读实时价格 CSV 的逻辑(含新旧格式兼容)整体搬入。返回 `{code: {close, realtime, pe, pb}}`。
- `read_m120_with_deviation()` 改为调用 `_read_price_csv()` 替代内联段(行为不变，同文件去重)。
- 新增 `read_prices_only() -> dict[str, dict]`：直接 `return self._read_price_csv()`。文件缺失/读取失败返回 `{}`。

### 2. `api/models.py`
新增：
```python
class PriceItem(BaseModel):
    code: str
    close: Optional[float] = None
    realtime: Optional[float] = None
    pe: Optional[float] = None
    pb: Optional[float] = None
    yield_ttm: Optional[float] = None

class PriceListResponse(BaseModel):
    total: int
    items: list[PriceItem]
    last_updated: Optional[str] = None
```

### 3. `api/routes.py`
- 抽模块级 helper `_compute_yield_ttm(row, realtime_price, calculator) -> Optional[float]`：搬迁 m120 endpoint line 604-626 的 TTM 计算逻辑。m120 endpoint 改为调用它(行为不变，同文件去重)。
- 新增 endpoint：
```python
@router.get("/prices", response_model=PriceListResponse)
async def get_prices(codes: str = Query("", description="逗号分隔股票代码，空=全部")):
    prices = m120_service.read_prices_only()
    # codes 过滤
    # 读主 CSV 建 code→row map(仅对请求 code 算 yield_ttm)
    # 构建 PriceItem 列表
    # last_updated = 实时价格 CSV mtime
```

## 前端改动点 (apps/dividend)

### 1. `lib/types.ts`
新增 `PriceItem` 接口(code/close/realtime/pe/pb/yield_ttm)。

### 2. `lib/api.ts`
```ts
getPrices: (codes?: string[]) =>
  directClient.get<PriceListResponse>('/api/dividend/prices', codes?.length ? { codes: codes.join(',') } : undefined),
```

### 3. `lib/hooks/useRealtimePrices.ts` (新文件)
输入 `codes: string[]`，输出 `{ priceMap: Map<string, PriceItem> }`。codes 为空 → 空 Map。沿用 `useMemo(JSON.stringify)` 防循环(与现有 useTechnicalData 一致)。

### 4. `app/page.tsx`
- 派生 `alertCodes = alertStocks.map(s => s.stock.code)`。
- `const { priceMap } = useRealtimePrices(alertCodes);`
- 挡位监控渲染段(1068-1087)：`const price = priceMap.get(stock.code);` `currentPrice = price?.realtime ?? price?.close ?? null`；`currentPE/currentPB/yieldTtm` 改读 `price`。删除对 `technicalData.get` 的引用(仅此段)。

## 边界与降级

- 实时价格 CSV 也不存在 → `read_prices_only()` 返回 `{}` → 前端 `currentPrice=null` → bar 不渲染(空白)。**属 Out of Scope**，不在本次加空状态文案，保持 surgical。
- `yield_ttm` 依赖主 CSV；挡位监控的 code 必在主 CSV(alertStocks 已保证)，无 KeyError 风险。
- `_compute_yield_ttm` 内部已 try/except，失败返回 None，不影响其他字段。

## 兼容性 / 回滚

- 新增接口 + 新增前端 hook，**不修改任何既有接口契约**，零破坏性。
- m120 endpoint 与 `read_m120_with_deviation` 仅做同文件内聚重构(抽 helper)，行为等价。
- 回滚：还原前端 `page.tsx` 挡位段读 `technicalData` 即可恢复旧行为；后端新接口/hook 可保留不调用(无害)。

## 子模块流程备忘

后端属 `backend/dividend-select` 子模块：
1. 子模块内改代码 → `git add/commit/push origin main`
2. 回主仓库 `git add backend/dividend-select` 更新 gitlink
3. 主仓库 commit/push
(子模块必须先 push，主仓库才能 push gitlink)
