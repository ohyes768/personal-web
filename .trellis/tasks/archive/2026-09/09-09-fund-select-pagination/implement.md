# Implement: 基金筛选页分页改造（4 tab）

按依赖顺序执行，每步独立可验证。

## 1. 后端 service 层

### 1.1 `backend/fund-select/src/services/filter_service.py`

- [ ] `_screen(self, kind, min_age, min_size_yi, max_dd_3y, min_mgr_exp, sort, order, universe_codes, exclude_qdii=False, min_sharpe=None, market_types=None, min_ret_1y=None, min_ret_3y=None, max_nav_stale_days=None, page=1, limit=50)` 加形参
- [ ] 在 `_to_dto` 循环之后、排序之前：`total = len(items)`（这是改造前计算 total 的等价位置）
- [ ] 排序逻辑保持不变（valued.sort + empty 拼接）
- [ ] 在 return 前：`offset = (page - 1) * limit; items = items[offset : offset + limit]; return {"total": total, "items": items}`
- [ ] `screen` / `screen_stock` / `screen_discovery_bond` / `screen_discovery_stock` 四个 wrapper 加 `page=1, limit=50` 形参并透传给 `_screen`

### 1.2 验证

```bash
cd backend/fund-select && uv run python -c "from src.services.filter_service import FilterService; print('import ok')"
```

## 2. 后端 routes 层

### 2.1 `backend/fund-select/src/api/routes.py`

4 个 `@router*.get("/screen", ...)` 端点都加：

```python
page: int = Query(1, ge=1, description="页码，1-indexed"),
limit: int = Query(50, ge=1, le=200, description="每页条数"),
```

调用 `svc.screen*(..., page=page, limit=limit)`。

涉及端点（已在 design 列出）：

- line ~52 `@router.get("/screen", ...)`
- line ~159 `@router_stock.get("/screen", ...)`
- line ~269 `@router_discovery_bond.get("/screen", ...)`
- line ~347 `@router_discovery_stock.get("/screen", ...)`

## 3. 后端测试

### 3.1 `backend/fund-select/tests/test_filter_service.py`

在已有 fixture 上新增测试函数：

```python
def test_screen_pagination_default_returns_all_when_under_limit(...)
def test_screen_pagination_first_page(...)
def test_screen_pagination_second_page_no_overlap(...)
def test_screen_pagination_oversized_page_returns_empty(...)
def test_screen_pagination_total_unaffected_by_page(...)
def test_screen_pagination_none_sort_still_tail(...)
```

### 3.2 `backend/fund-select/tests/test_stock_filter_service.py`

同上 6 个 case。

### 3.3 `backend/fund-select/tests/test_discovery_filter_service.py`

同上 6 个 case（discovery-bond + discovery-stock 可合并 / 复用 fixture）。

### 3.4 `backend/fund-select/tests/test_api.py`

```python
def test_screen_limit_zero_returns_422(...)
def test_screen_limit_too_large_returns_422(...)
def test_screen_page_zero_returns_422(...)
```

### 3.5 运行

```bash
cd backend/fund-select && python -m pytest tests/ -v
```

应全部通过，无 FAIL / ERROR。如有 skip，看是否是已有原因。

## 4. 前端类型

### 4.1 `apps/fund-select/src/lib/types.ts`

```ts
export interface FundFilters {
  // 现有 10 个字段
  page: number;     // 默认 1
  limit: number;    // 默认 50
}
```

`DEFAULT_FILTERS` / `STOCK_DEFAULT_FILTERS` / `DISCOVERY_BOND_DEFAULT_FILTERS` / `DISCOVERY_STOCK_DEFAULT_FILTERS` 都加 `page: 1, limit: 50`。

## 5. 前端 URL 同步

### 5.1 `apps/fund-select/src/lib/useFilters.ts`

- [ ] `parseFiltersFromSearch`：新增 `page` / `limit` 解析（默认 1 / 50；非法值用默认）
- [ ] `filtersToSearch`：page !== 1 写 URL；limit !== 50 写 URL
- [ ] `useFilters` 返回新增方法：
  - `setPage(page: number): void`（同步 URL；写新 page 值）
  - `setLimit(limit: number): void`（同步 URL；page 强制 1，limit 写新值）
- [ ] `setFilter` 内部：对 numeric / exclude_qdii / market_types 改动时，把 page 置 1

### 5.2 验证

`pnpm tsc --noEmit` 在 `apps/fund-select` 下通过。

## 6. 前端 API client

### 6.1 `apps/fund-select/src/lib/api.ts`

`buildQuery` 函数末尾追加：

```ts
if (filters.page != null && filters.page > 1) params.set('page', String(filters.page));
if (filters.limit != null && filters.limit !== 50) params.set('limit', String(filters.limit));
```

4 个 `*Api.screen` 方法自动透传（已经在用 `buildQuery(filters)`）。

## 7. 前端 hooks

### 7.1 `apps/fund-select/src/lib/hooks.ts`

4 个 hook 的 query 串都追加 `filters.page` 和 `filters.limit`：

```ts
const query = [
  // 现有
  filters.page, filters.limit,
].join('|');
```

## 8. 前端分页器组件

### 8.1 新增 `apps/fund-select/src/components/Pagination.tsx`

按 `design.md` 第 4.5 节的代码骨架实现。

要点：
- `total <= limit` → return null（调用方也可省，但组件内部再兜一道）
- 上下页按钮 disabled 边界
- LIMIT_OPTIONS = [25, 50, 100]
- 样式与 FundTable / FundsHeader 一致：`text-xs`、`text-ink-muted`、`tnum`（数字 tabular-nums）

## 9. 4 个 page 组件挂分页器

### 9.1 `apps/fund-select/src/app/bond/page.tsx`

在 `</section>` 之前（即 `FundTable` 之后）加：

```tsx
<Pagination
  page={filters.page}
  limit={filters.limit}
  total={total}
  onPageChange={setPage}
  onLimitChange={setLimit}
/>
```

`FundsPageInner` 内从 `useFilters()` 解构新增 `setPage` / `setLimit`。

### 9.2 `apps/fund-select/src/app/stock/page.tsx`

同 9.1。

### 9.3 `apps/fund-select/src/app/discovery-bond/page.tsx`

同 9.1。

### 9.4 `apps/fund-select/src/app/discovery-stock/page.tsx`

同 9.1。

## 10. 端到端验证

### 10.1 前端构建

```bash
cd apps/fund-select && pnpm build
```

无 TS / Next.js 构建错误。

### 10.2 启动后端 + 前端

```bash
# 后端
cd backend/fund-select
uv run uvicorn src.main:app --reload --host 0.0.0.0 --port 8095

# 前端
cd apps/fund-select
pnpm dev
```

### 10.3 浏览器手动验证（按 PRD 验收标准）

| # | 验证项 | 期望 |
|---|---|---|
| 1 | `/funds/bond` 首屏 | 列表加载 50 条，URL 不带 page / limit |
| 2 | `/funds/discovery-stock` 首屏 | 列表加载 50 条，分页器出现「第 1-50 条 / 共 N 条」 |
| 3 | 点击下一页 | URL 出现 `page=2`，表格换页 |
| 4 | 切每页 25 | URL 出现 `limit=25`，page 回到 1 |
| 5 | 改左侧 min_age | URL 去掉 `page`，page 回到 1 |
| 6 | 点表头排序 | URL sort 变，`page` 保持 |
| 7 | 浏览器后退 | 恢复上一 page 状态 |
| 8 | 直接访问 `/funds/bond?page=3` | 跳到第 3 页 |

## 11. 提交

- [ ] 暂存未追踪的 .trellis 任务目录不进 commit
- [ ] 改动文件清单：
  - `backend/fund-select/src/services/filter_service.py`
  - `backend/fund-select/src/api/routes.py`
  - `backend/fund-select/tests/test_filter_service.py`
  - `backend/fund-select/tests/test_stock_filter_service.py`
  - `backend/fund-select/tests/test_discovery_filter_service.py`
  - `backend/fund-select/tests/test_api.py`
  - `apps/fund-select/src/lib/types.ts`
  - `apps/fund-select/src/lib/useFilters.ts`
  - `apps/fund-select/src/lib/api.ts`
  - `apps/fund-select/src/lib/hooks.ts`
  - `apps/fund-select/src/components/Pagination.tsx`（新增）
  - `apps/fund-select/src/app/bond/page.tsx`
  - `apps/fund-select/src/app/stock/page.tsx`
  - `apps/fund-select/src/app/discovery-bond/page.tsx`
  - `apps/fund-select/src/app/discovery-stock/page.tsx`
- [ ] `git status` 确认无意外文件
- [ ] `pnpm lint` 在 `apps/fund-select` 下通过
- [ ] commit message 走 conventional format：

```
feat(fund-select): 列表分页（4 tab，server page/limit）
```
