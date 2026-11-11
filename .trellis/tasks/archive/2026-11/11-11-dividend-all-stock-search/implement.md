# Implement — Dividend「全部」页股票搜索

> 关联：`prd.md` / `design.md`。顺序执行，每步完成即验证。

## Step 1 — 后端：搜索过滤服务

- [ ] `backend/dividend-select/src/services/filter_service.py`
  - 新增 `filter_by_search(df, keyword) -> pd.DataFrame`：名称/代码包含匹配（代码 `str().str.zfill(6)`，不区分大小写），空关键词原样返回。
  - 新增 `sort_by_search_relevance(df, keyword) -> pd.DataFrame`：相关度（代码全等 > 代码前缀 > 名称前缀 > 名称包含 > 代码包含）→ 3 年平均股息率降序 → 代码升序。
- [ ] 验证：`python -m pytest tests/test_stock_search.py -v`（此时先写测试，见 Step 2）

## Step 2 — 后端：路由与测试

- [ ] `backend/dividend-select/src/api/routes.py`
  - `get_stocks` 新增 `search: Annotated[Optional[str], Query(description="...")] = None`（**必须** `Annotated` 写法）。
  - `_build_stock_list` 新增尾部默认参数 `search: Optional[str] = None`；搜索分支：`codes` 交集 → `filter_by_search` → `sort_by_search_relevance`，跳过阈值/交易所/行业/指数筛选与通用排序。
- [ ] `backend/dividend-select/tests/test_stock_search.py`（新）
  - 名称包含、代码包含（含前导零）、大小写、trim、无匹配、空关键词保持原行为。
  - 阈值外股票可被搜到（`min_yield=10` + 搜索仍返回低股息率股票）。
  - `codes` 与搜索取交集；`search` 不传时行为不变。
  - 走**真实路由调用链**（`asyncio.run(routes.get_stocks(...))`），不 mock `get_stocks`。
- [ ] 验证：`python -m pytest tests/test_stock_search.py -v` 全绿；再跑 `python -m pytest tests/ -q` 无回归。

## Step 3 — 前端：类型与纯函数

- [ ] `apps/dividend/src/lib/types.ts`：`DividendQueryParams` 增 `search?: string | null`。
- [ ] `apps/dividend/src/lib/stock-search.ts`（新）：`normalizeSearchKeyword`、`buildStockSearchParams`。
- [ ] `apps/dividend/src/lib/stock-search.test.ts`（新）：node:test 单测。
- [ ] 验证：`cd apps/dividend && node --experimental-strip-types --test src/lib/stock-search.test.ts`

## Step 4 — 前端：搜索 Hook 与组件

- [ ] `apps/dividend/src/lib/hooks/useStockSearch.ts`（新）：300ms 防抖 + 响应序号；`enabled=false`/空关键词 → 清空且不发请求；错误态可读。
- [ ] `apps/dividend/src/components/StockSearchBar.tsx`（新）：输入框 + 清除按钮 + 状态提示。

## Step 5 — 前端：页面接入

- [ ] `apps/dividend/src/app/page.tsx`
  - 搜索状态（输入值 / 归一关键词 / 是否激活）。
  - `displayData` 增搜索分支（后端结果 + technical）。
  - `stockCodes` = 阈值内 ∪ 搜索结果 → 技术指标覆盖搜索命中股票。
  - 搜索条接入（「全部」Tab，两个模式都可见）；空状态文案；清空恢复原行为。
- [ ] `apps/dividend/src/lib/hooks.ts`：`useTechnicalData` 改为「全量 M120 Map → 按 codes 派生子集」。

## Step 6 — 前端验证

- [ ] `cd apps/dividend && pnpm lint`
- [ ] `cd apps/dividend && node --experimental-strip-types --test src/lib/*.test.ts`
- [ ] `cd apps/dividend && pnpm build`
- [ ] e2e：`apps/dividend/e2e/stock-search.spec.ts`（新，`page.route` 拦截 API，不依赖真实后端）
  - 输入名称 → 请求带 `search=` → 表格出现命中股票 → 星标可收藏
  - 无匹配 → 明确空状态
  - 清空 → 恢复原列表
  - 「只看收藏」+ 搜索 → 请求带 `codes=`
- [ ] `cd apps/dividend && npx playwright test e2e/stock-search.spec.ts`（复用已运行的 3003 dev server，禁止另起实例）

## Step 7 — 规范与收尾

- [ ] 新增 `.trellis/spec/backend/dividend-select/backend/stock-search-contract.md`，在 `index.md` 索引表登记；`.trellis/spec/frontend/index.md` 加一行指向。
- [ ] 提交（Phase 3.4）：先列计划给用户确认，再 `git add` + `git commit`；不 push。

## 回滚点

- Step 1–2（后端）与 Step 3–5（前端）互相独立，可分别回滚；后端新增参数是可选的，旧前端不受影响。
- 无数据库/写盘副作用，无需数据回滚。
