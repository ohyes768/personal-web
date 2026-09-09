# Design: 基金筛选页分页改造（4 tab）

## 1. 范围与边界

### 在范围内

| 层 | 改动 |
|---|---|
| 后端 API 路由 | `backend/fund-select/src/api/routes.py` 4 个 `@router*.get("/screen", ...)` 加 `page` / `limit` 参数 |
| 后端 service | `backend/fund-select/src/services/filter_service.py` `_screen` 加 `page`/`limit` 形参；4 个 `screen_*` wrapper 透传 |
| 后端测试 | `test_filter_service.py` + `test_discovery_filter_service.py` + `test_stock_filter_service.py` 增加分页场景 |
| 前端类型 | `apps/fund-select/src/lib/types.ts` `FundFilters` 加 `page` / `limit` |
| 前端 URL 同步 | `apps/fund-select/src/lib/useFilters.ts` `parseFiltersFromSearch` / `filtersToSearch` 加 page/limit |
| 前端 API client | `apps/fund-select/src/lib/api.ts` `buildQuery` 加 page/limit |
| 前端 hooks | `apps/fund-select/src/lib/hooks.ts` 4 个 hook 把 page/limit 加进 query 串 |
| 前端页面 | `apps/fund-select/src/app/{bond,stock,discovery-bond,discovery-stock}/page.tsx` 4 个页面挂分页器 |
| 前端组件 | 新增 `apps/fund-select/src/components/Pagination.tsx` |

### 不在范围内

- SQL 层做 ORDER BY + LIMIT/OFFSET 改造（保持 in-memory 排序，按需优化）
- 其它端点（refresh / stats / detail / detail rank 等不分页的接口）
- 排序/筛选面板 UI 变化
- export / 全量刷新弹窗 / 对比抽屉逻辑
- 其它前端（apps/dividend / apps/macro / apps/news / apps/douyin）无变更

## 2. 契约

### 2.1 后端 API（4 个 screen 端点同形）

**请求新增参数：**

| 参数 | 类型 | 范围 | 默认 | 错误 |
|---|---|---|---|---|
| `page` | int | ≥ 1 | 1 | < 1 → 422 |
| `limit` | int | 1–200 | 50 | < 1 或 > 200 → 422 |

**响应 shape 不变：**

```json
{
  "total": 1234,
  "items": [...]
}
```

`total` 是筛后总命中数；`items` 长度 ≤ `limit`。

### 2.2 前端 FundFilters

```ts
export interface FundFilters {
  // 现有 10 个字段
  page: number;     // 默认 1
  limit: number;    // 默认 50
}
```

### 2.3 URL 参数

- `?page=2` 表示当前页（page=1 不写进 URL）
- `?limit=25` 表示每页 25（limit=50 不写进 URL）

## 3. 数据流

### 3.1 后端分页流程

```
GET /api/funds/discovery-bond/screen?min_age=3&page=2&limit=25
  → routes.py 解析 page=2, limit=25（Query 校验）
  → FilterService.screen_discovery_bond(..., page=2, limit=25)
  → _screen(kind="discovery-bond", ..., page=2, limit=25):
      1. 组装 SQL q（Fund LEFT JOIN × 5）
      2. 执行 q → rows 全量（不超过 universe 上限）
      3. 二次查询 FundAchievementRank（codes = rows 全量）
      4. items = [_to_dto(...) for f, p, fee, hold, risk, market_rank in rows]
      5. total = len(items)  # 全量命中数
      6. sort_key = sort if sort in SORT_COLUMNS else default_sort
      7. descending = order != "asc"
      8. valued = [it for it in items if getter(it) is not None]
         valued.sort(key=getter, reverse=descending)
         empty = [it for it in items if getter(it) is None]
         items = valued + empty
      9. ★ 新增：offset = (page - 1) * limit
                   items = items[offset : offset + limit]
      10. return {"total": total, "items": items}
```

**关键不变性：**
- `total` 是筛后**总数**，与 page/limit 无关
- ach_map 仍按全量 codes 查（保证排序前的 ach 数据完整）
- 排序在切片**之前**：保证多页之间无重叠、无遗漏、排序稳定

### 3.2 前端数据流

```
用户操作（点页码 / 改 limit）
  → FundsPage 调用 setPage(2) 或 setLimit(25)
    → useFilters 内部 pushQuery(filtersToSearch({...filters, page: 2}))
      → URL 出现 ?page=2
        → searchParams 变化
          → useFilters 返回新 filters（page=2）
            → useFundList(filters) useEffect 依赖 query 串变化
              → fundApi.screen(filters) 拉新一页
                → 渲染 FundTable + Pagination
```

### 3.3 筛选 vs 排序 对 page 的影响

| 触发 | page 重置？ | URL 表现 |
|---|---|---|
| 改 numeric 维度（min_age / min_size_yi / ...） | ✅ 是 | `page` 从 URL 移除 |
| 改 sort 字段（toggleSort 不同 field） | ❌ 否 | `page` 保持 |
| 改 sort order（toggleSort 同 field） | ❌ 否 | `page` 保持 |
| 改 exclude_qdii / market_types | ✅ 是 | `page` 从 URL 移除 |
| 点分页器下一页 | 改成新值 | `page=N` 写进 URL |
| 改每页条数 | 重置为 1 | `limit=N` 写进 URL，`page` 移除 |
| 浏览器后退 | 恢复 URL | 列表回到对应页 |

## 4. 关键实现细节

### 4.1 routes.py 加 Query 参数

每个 `@router.get("/screen", ...)` 加：

```python
page: int = Query(1, ge=1, description="页码，1-indexed"),
limit: int = Query(50, ge=1, le=200, description="每页条数"),
```

调用 `svc.screen*(..., page=page, limit=limit)`。

### 4.2 FilterService._screen 加 page/limit

```python
def _screen(
    self,
    kind: str,
    min_age, min_size_yi, max_dd_3y, min_mgr_exp,
    sort, order, universe_codes,
    exclude_qdii=False, min_sharpe=None, market_types=None,
    min_ret_1y=None, min_ret_3y=None, max_nav_stale_days=None,
    page: int = 1,
    limit: int = 50,
) -> dict:
    # ... 既有逻辑 ...
    # ★ 新增：在 valued + empty 之后、return 之前
    total = len(items)
    offset = (page - 1) * limit
    items = items[offset : offset + limit]
    return {"total": total, "items": items}
```

4 个 `screen*` wrapper 也加 page/limit 形参并透传。

### 4.3 useFilters.ts 增加 page/limit

`parseFiltersFromSearch`：从 URL 读 `page`/`limit`，未指定 / 非法值用默认值。

`filtersToSearch`：page=1 / limit=50 不写 URL；否则写。

`useFilters` 返回新增方法：
- `setPage(page: number)`
- `setLimit(limit: number)`

并在 `setFilter` 内部：若是 numeric / exclude_qdii / market_types 改动，自动把 page 置 1。

### 4.4 hooks.ts

4 个 useFundList* 的 query 串里追加 `filters.page` 和 `filters.limit`。新增 `useDiscoveryStockFundList` / `useDiscoveryBondFundList` 也同步。无需改 fetch 逻辑。

### 4.5 Pagination.tsx 组件

```tsx
'use client';

interface PaginationProps {
  page: number;
  limit: number;
  total: number;
  onPageChange: (page: number) => void;
  onLimitChange: (limit: number) => void;
}

const LIMIT_OPTIONS = [25, 50, 100] as const;

export function Pagination({ page, limit, total, onPageChange, onLimitChange }: PaginationProps) {
  const totalPages = Math.max(1, Math.ceil(total / limit));
  // total <= limit → 不渲染（调用方也可省）
  if (total <= limit) return null;
  
  const start = (page - 1) * limit + 1;
  const end = Math.min(page * limit, total);
  
  return (
    <div className="flex items-center justify-between gap-3 px-2 py-3 text-xs">
      <div className="text-ink-muted">
        第 <span className="tnum">{start}</span>–
        <span className="tnum">{end}</span> 条 / 共 <span className="tnum">{total}</span> 条
      </div>
      <div className="flex items-center gap-2">
        <button
          onClick={() => onPageChange(page - 1)}
          disabled={page <= 1}
          className="...省略 Tailwind"
        >上一页</button>
        <span className="text-ink-muted">
          第 <span className="tnum">{page}</span> / <span className="tnum">{totalPages}</span> 页
        </span>
        <button
          onClick={() => onPageChange(page + 1)}
          disabled={page >= totalPages}
          className="..."
        >下一页</button>
      </div>
      <div className="flex items-center gap-1 text-ink-muted">
        每页
        <select
          value={limit}
          onChange={e => onLimitChange(Number(e.target.value))}
          className="..."
        >
          {LIMIT_OPTIONS.map(n => <option key={n} value={n}>{n}</option>)}
        </select>
        条
      </div>
    </div>
  );
}
```

### 4.6 4 个 page 组件挂载

每个 page 在 `<FundTable />` 下方加：

```tsx
<Pagination
  page={filters.page}
  limit={filters.limit}
  total={total}
  onPageChange={setPage}
  onLimitChange={setLimit}
/>
```

## 5. 兼容性 & 回滚

### 兼容性

- URL 不带 `page`/`limit` → 默认 page=1, limit=50，向后兼容
- 4 个 screen 端点响应 shape 完全不变；只是 items 长度从「全量」变「当页」
- 老的 e2e / 集成断言如果用 `assert len(items) == total`，会失败；本次同步更新

### 回滚

- 后端 `Query` 参数带默认值；旧客户端不传 page/limit，行为不变（page=1, limit=50，债基 tab 31 只 < 50 不显示分页器）
- 前端 hooks 默认 page=1/limit=50；不开分页器时行为与改造前完全一致（31 只直接全显示）
- 真要回滚：删 `Pagination` 组件挂载 + 移除 `setPage`/`setLimit` 调用即可；后端参数不动也安全

## 6. 测试策略

### 后端 pytest

- `test_filter_service.py` 新增：
  - 空集：page=1, limit=10 → total=0, items=[]
  - 单页：seed 30 只 → page=1, limit=10 → items 长度 10
  - 跨页：page=2, limit=10 → items 长度 10，与 page=1 无重叠
  - 越界：page=999, limit=10 → items=[]
  - None 排序尾部：sort=size_yy 缺测，None 仍排末位
- `test_discovery_filter_service.py` / `test_stock_filter_service.py` 同款
- `test_api.py` 用 FastAPI TestClient 验证 `?limit=0` / `?page=0` / `?limit=1000` → 422

### 前端

- 暂不写前端单测（项目当前没有前端测试基础设施，避免范围蔓延）；靠手动验证 + 浏览器 e2e
- 浏览器验证 4 个 tab 的 7 个验收标准（见 prd）

## 7. 实施顺序

1. 后端 `_screen` + 4 个 wrapper + 4 个 routes 加 page/limit
2. 后端测试
3. 前端 types/useFilters/api/hooks 4 处改
4. 新增 Pagination 组件
5. 4 个 page 组件挂分页器
6. 手动验证（4 个 tab × 默认状态 / 翻页 / 切换 limit / 切换筛选）
