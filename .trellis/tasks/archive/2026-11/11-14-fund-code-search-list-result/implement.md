# 执行计划：基金代码搜索改为列表出结果

## 顺序原则

后端先行（先有 `code=` 搜索接口，前端才有东西可打），再改 lookup 落点，
最后前端接线。每步都能单独跑测试。

## 1. 后端

- [ ] 1.1 `src/services/filter_service.py`：新增 `search_by_code(code, curated_kind)`
      - 同一组 outerjoin，条件仅 `Fund.code == code`
      - 复用 `_to_dto` + `RANK_PERIODS` 排名查询
      - 返回 `{total, items}`，补 `in_curated`
- [ ] 1.2 `src/api/routes.py`：`/screen` 与 `stock/screen` 加
      `code: Optional[str] = Query(None, pattern=r"^\d{6}$")`；命中时短路到 `search_by_code`
- [ ] 1.3 `src/services/lookup_service.py`：`path` 改 `search_code`，`discovery-*` 落点收敛
- [ ] 1.4 更新 `tests/test_lookup_service.py` / `tests/test_lookup_api.py` 的 path 断言
- [ ] 1.5 新增 `tests/test_code_search.py`：
      单条命中、阈值被忽略、is_active=False 仍返回、不存在 code → total=0、
      非法 code → 422、非搜索态行为回归（带阈值仍过滤）、DTO 字段齐
- [ ] 1.6 `./.venv/bin/python -m pytest tests/ -q` 全绿

## 2. 前端纯逻辑

- [ ] 2.1 新增 `src/lib/search-code.ts`：`parseSearchCode` / `toSearchParams`
      （归一化 + 6 位校验，复用 `lookup.ts` 的 `toHalfWidth` 思路）
- [ ] 2.2 新增 `src/lib/search-code.test.ts`
- [ ] 2.3 `src/lib/types.ts`：`FundFilters` 加 `search_code?: string | null`
- [ ] 2.4 `src/lib/useFilters.ts`：解析/序列化 `search_code`；`setFilter`/`setLimit` 时清空；
      `activeCount` 不含搜索态
- [ ] 2.5 `src/lib/api.ts`：`buildQuery` 有 `search_code` 时只发 `code=`
- [ ] 2.6 `src/lib/hooks.ts`：两个 list hook 的 `query` 依赖加 `search_code`

## 3. 前端组件与页面

- [ ] 3.1 `FundCodeSearch.tsx`：`router.push(res.path)`（去掉 `focus=1`）
- [ ] 3.2 `FilterChipBar.tsx`：`searchCode` + `onClearSearch`，渲染「代码 XXX ×」chip
- [ ] 3.3 `FundTable.tsx`：`highlightCode` / `emptyHint`
- [ ] 3.4 `src/app/bond/page.tsx`、`src/app/stock/page.tsx`：删 `focus=1` 分支，
      接线 chip / 高亮 / 空态

## 4. 验证

- [ ] 4.1 `node --experimental-strip-types --test src/lib/*.test.ts`
- [ ] 4.2 `npx tsc --noEmit`
- [ ] 4.3 `pnpm build`
- [ ] 4.4 接口手验（端口 8095，容器里跑的是旧镜像，用 `.venv` 本地拉起或直接打
      TestClient 断言）：
      - `GET /api/funds/lookup/003547` → `path=/bond?search_code=003547`
      - `GET /api/funds/screen?code=003547&min_size_yi=999` → 仍返回该条
      - `GET /api/funds/stock/screen?code=002910` → 返回该条
- [ ] 4.5 浏览器手验（3005）：股基搜 002910 → 列表 1 行高亮 → 点行开抽屉 →
      chip × 回退筛选；债基搜 003547 同上；`/bond?code=003547` 仍自动开抽屉
- [ ] 4.6 390px 布局不溢出（chip 行加了一枚 chip，需确认换行正常）

## 5. 收尾

- [ ] 5.1 更新 `.trellis/spec/backend/fund-select/backend/contracts.md` §20
      （lookup path 语义 + `/screen?code=` 新契约）
- [ ] 5.2 提交（一个 commit，前端 + 后端 + 测试 + spec）

## 回滚点

- 只需回滚 1.2 / 1.3 即可让前端新参数失效（前端会拿到空列表）；
  若要彻底回到旧交互，回滚 3.1 + 3.4。
