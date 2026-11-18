# 技术设计：基金代码搜索改为列表出结果

> 依赖既有能力：`GET /api/funds/lookup/{code}`（11-14）、`/bond?code=` 直达抽屉（08 双向闭环）、
> 来源分段合并页（11-15）。本设计只改「命中之后发生什么」。

## 1. 边界

| 层 | 文件 | 改动 |
|---|---|---|
| 后端 API | `src/api/routes.py` | `/screen` 与 `/stock/screen` 新增 `code` 查询参数 |
| 后端服务 | `src/services/filter_service.py` | 新增 `search_by_code(code, curated_kind)`：按 code 取一条（忽略阈值/宇宙/is_active） |
| 后端服务 | `src/services/lookup_service.py` | `path` 改为 `<page>?search_code=<code>`，discovery-* 落点收敛到 `/bond` `/stock` |
| 后端测试 | `tests/test_lookup_service.py`、`tests/test_lookup_api.py`、新增 `tests/test_code_search.py` | 契约更新 + 搜索覆盖 |
| 前端纯逻辑 | `src/lib/search-code.ts`（新） | `parseSearchCode` / `serializeSearchCode` / `searchCodeApiQuery` |
| 前端纯逻辑 | `src/lib/useFilters.ts` | `search_code` 参与 URL 解析与序列化；`setSearchCode` |
| 前端纯逻辑 | `src/lib/api.ts` | `buildQuery`：有 `search_code` 时只发 `code=` |
| 前端 hooks | `src/lib/hooks.ts` | `useFundList` / `useStockFundList` 的 query 依赖加入 `search_code` |
| 前端组件 | `src/components/FundCodeSearch.tsx` | 命中后直接 `router.push(path)`，不再加 `focus=1` |
| 前端组件 | `src/components/FilterChipBar.tsx` | 新增「代码搜索 XXX ×」chip |
| 前端组件 | `src/components/FundTable.tsx` | 新增 `highlightCode` / `emptyHint` |
| 前端页面 | `src/app/bond/page.tsx`、`src/app/stock/page.tsx` | 删除 `focus=1` 清筛选分支；接 chip + 高亮 + 空态 |

### 不变量

1. `/bond?code=xxx`（经理页徽章）**仍自动开抽屉**，协议不改。
2. 搜索态**不清任何筛选**，也不写 `cleared=1`；退出搜索后原筛选原样回来。
3. basePath 契约：前端只推相对路径，`path` 不带 `/funds` 前缀。
4. `lookup` 仍是只读纯查询：不写库、不触发采集。

---

## 2. 后端：按 code 取一条

### 2.1 接口

`GET /api/funds/screen?code=003547`、`GET /api/funds/stock/screen?code=003547`：

```python
code: Optional[str] = Query(None, pattern=r"^\d{6}$", description="按代码精确取一只（忽略所有阈值）")
```

- 有 `code` → 走 `search_by_code`，**其余参数全部忽略**（阈值、`exclude_qdii`、
  `market_type`、`source` 只作为回显）。
- 无 `code` → 现有链路逐字节不变（回归基线靠现有 746 条测试守住）。
- 格式非法（不足/超出 6 位、含字母）→ 422（与 `lookup` 同口径）。
- 代码不在库 → `{"total": 0, "items": []}`（业务空结果，200）。

### 2.2 语义决策

| 决策 | 取值 | 理由 |
|---|---|---|
| 是否套阈值 | **不套** | 搜的是「库里这一只」，不是「当前筛选命中的这一只」。否则用户搜 002910 却因规模 4.9 亿看不到结果，会以为代码错了 |
| 是否要求 `is_active` | **不要求** | 代码搜索是查询动作；已清盘基金也该能点开看历史。列表常规浏览仍只看在售 |
| 是否要求 ∈ 当前 tab 宇宙 | **不要求** | 债基页搜到股基代码时后端仍返回该条（前端已先经 `lookup` 判定 tab 再跳转，正常路径不会发生） |
| 是否带 `in_curated` | 带 | 与列表同构，表格/文案可复用 |

### 2.3 实现

```python
def search_by_code(self, code: str, curated_kind: str) -> dict:
    """代码搜索（忽略阈值/宇宙/is_active）。返回 {total, items}，与 /screen 同构。"""
```

- 查询与 `_screen` 同一组 outerjoin（Fund + Performance + Fees + HoldingsBond +
  RiskMetrics + MarketFundRank），条件只有 `Fund.code == code`。
- 排名：复用 `RANK_PERIODS` + 一次 `FundAchievementRank` 查询（同 `_screen`）。
- 复用 `_to_dto` 出条目，补 `in_curated`（`resolve_universe_codes(curated_kind)`）。
- **不要**在 `_screen` 里加 `code` 分支：`_screen` 承担排序/分页/宇宙语义，
  塞进「单条特例」会让 6 个调用点多一个隐式分支。

---

## 3. 后端：lookup 的 path 变化

```python
PAGE_BY_TAB = {
    "bond": "/bond",
    "stock": "/stock",
    # 11-15 之后 discovery-* 只是 redirect 壳：直接落合并页，DNS 少一跳、URL 更干净
    "discovery-bond": "/bond",
    "discovery-stock": "/stock",
}
path = f"{PAGE_BY_TAB[tab]}?search_code={code}"
```

- `tab` 字段**语义不变**（仍是四值分类，供经理页徽章等复用）；只有 `path` 变。
- `discovery-*` 落点直接给合并页：`/discovery-stock?search_code=` 会 302 到
  `/stock?source=market&search_code=`，多一跳且把 `source=market` 留在 URL 里，
  退出搜索后用户莫名处在「市场」分段。直接给 `/stock` 更符合预期。
- 契约测试相应更新：`test_lookup_service` / `test_lookup_api` 里 `path` 断言从
  `?code=` 改为 `?search_code=`，`discovery-*` 断言改为 `/stock` `/bond`。

---

## 4. 前端：搜索态是 URL 状态

### 4.1 参数

`search_code=<6 位>`，与筛选参数**并存**（不清、不覆盖）。解析规则：

- 值必须 6 位数字（全角归一、trim），否则视为无搜索；
- 搜索态存在期间，筛选参数照常解析但要发给后端时被忽略（后端也忽略，双保险）。

### 4.2 为什么放进 `useFilters` 而不是组件本地 state

| 方案 | 结论 |
|---|---|
| 组件本地 state | 刷新丢失、不可分享、返回键不可回退 → 否 |
| 放进 `useFilters` + URL | 刷新/前进后退/分享都对；`?code=` 直达协议不受影响 → **采用** |

代价：`FundFilters` 多一个可选字段，`activeCount` 必须**排除**它（否则 chip 计数串味）。

### 4.3 退出搜索的触发

| 动作 | 是否退出搜索 |
|---|---|
| 点 chip 的 × | 退出 |
| 改任一 numeric 阈值 / 分类 / exclude_qdii / source / limit | 退出（命中集语义变了） |
| 翻页 / 改排序 | 不退出（搜索结果只有 1 行，翻页无意义但无需打断） |
| 再搜一次别的代码 | 替换为新代码 |

实现：`setFilter(...)` / `setLimit(...)` 里若 `filters.search_code` 非空则一并置 null。
`setPage` / `toggleSort` 不动它。

### 4.4 组件行为

- `FundCodeSearch`：`found && path` → `router.push(path)`（path 里已带 `search_code`），
  清空输入；失败分支原样保留（弹框）。**删除 `focus=1` 追加**。
- `FilterChipBar`：新增 props `searchCode` / `onClearSearch`，渲染
  `代码 002910 ×`（与现有 chip 同样式，用 `bg-info-tint text-info` 保持视觉统一）。
- `FundTable`：新增 `highlightCode?: string | null`，命中行加
  `bg-accent/5 ring-1 ring-inset ring-accent/40`（与对比选中的 `bg-info-tint` 区分，
  两者可能同时出现：搜索态也能勾对比）。`emptyHint?: string` 用于搜索空结果文案。
- 页面：`/bond`、`/stock` 删除 `focus === '1'` 分支；把 `filters.search_code` /
  `setFilter('search_code', null)` 传给 chip 行与表格。

---

## 5. 空结果与错误矩阵

| 输入/状态 | 结果 |
|---|---|
| lookup `found=false` | 弹框「未找到该基金」（不变） |
| lookup 网络/5xx | 弹框「查询失败」（不变） |
| 输入不足 6 位 | 弹框「请输入完整的基金代码」（不变） |
| `?search_code=000000`（lookup 未走，直接改 URL） | 表格空态「该代码不在库中」，chip 仍可 × 退出 |
| `?search_code=abc` | 视为无搜索，正常列表 |
| 搜索命中 + 该基金无业绩记录 | 返回该条，各指标列显示 `-`（`_to_dto` 已处理 NULL） |

---

## 6. 兼容性 / 风险

| 风险 | 处置 |
|---|---|
| `?focus=1` 旧链接 | 该参数从不由用户手工产生（搜索框瞬产生）。删掉分支后旧链接退化为「开抽屉 + 不清筛选」，可接受 |
| `discovery-*?code=` 直达（外部收藏） | redirect 保留 query，`?code=` 仍落到合并页并开抽屉，不破 |
| `/screen` 加 `code` 参数与 `/{code}` 详情路由冲突 | 不冲突：这是同资源上的 query 参数，不是新路径段 |
| 搜索态与「对比」混用 | 表格行结构一致，对比按钮照常；退出搜索后已选对比项不丢 |
| 后端与前端需同发 | `search_code` 需要后端 `code=` 支持；单独发前端会得到空列表 → 部署时一起发 |

## 7. 验证

- 后端：`./.venv/bin/python -m pytest tests/ -q`（746 基线 + 新增）。
- 前端：`node --experimental-strip-types --test src/lib/*.test.ts`、`npx tsc --noEmit`、`pnpm build`。
- 手验：`curl` 三个接口（lookup path / screen with code / 阈值被忽略），浏览器走一遍
  搜索→列表→点行→抽屉→chip × 回退（债基 + 股基各一次）。
