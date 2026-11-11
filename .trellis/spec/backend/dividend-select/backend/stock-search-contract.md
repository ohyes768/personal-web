# 股息率「全部」页股票搜索契约

> 建立于 2026-11-11（11-11-dividend-all-stock-search）。
> 适用 `backend/dividend-select` 的 `/stocks?search=` 与 `apps/dividend` 的搜索条。
> 读时一并参考 `snapshot-cache-contract.md`（`/stocks` 参数扩展与线程隔离）、
> `code-type-guidelines.md`（代码前导零）、`screening-watchlist-contract.md`（收藏独立于阈值）。

## 1. Scope / Trigger

- 给 `/api/dividend/stocks` 增加查询参数、加关键词过滤/排序时。
- 改「全部」页的搜索条、显示分支、收藏范围收窄时。
- 改 `useTechnicalData` / `useStockSearch` 等前端数据链路时。

## 2. Signatures

- `GET /api/dividend/stocks?search=<关键词>`：在**完整收集池**上按股票名称或代码包含匹配。
  新参数写法必须是 `Annotated[Optional[str], Query(...)] = None`（`screen` / quality analyze
  在 Python 里直接调用 `get_stocks`，`= Query(None)` 的默认对象不会被解析）。
- `FilterService.filter_by_search(df, keyword)`：只做匹配，不排序。
- `FilterService.sort_by_search_relevance(df, keyword)`：只做相关度排序。
- `normalize_search_keyword(keyword)`：**模块级**函数（不是 service 实例方法），
  路由控制流依赖它——用实例方法会被 mock 掉的 service 破坏（Mock 返回值恒真）。
- 前端 `buildStockSearchParams(keyword, codes?)` / `normalizeSearchKeyword(raw)`（`src/lib/stock-search.ts`）。

## 3. Contracts

### 3.1 匹配语义

- 关键词归一：去掉首尾空格；空串/空白 = **未搜索**，此时接口行为与改动前逐字节一致。
- 命中条件：`股票名称` 包含关键词 **或** `股票代码` 包含关键词（不区分大小写）。
- 代码按 `str().str.zfill(6)` 归一后做子串匹配，前导零不丢：`000333` 命中 `000333`，
  `00333` 也命中（子串语义），响应里的 `code` 仍是六位字符串。
- 语料是**完整收集池**（主 CSV 全量行），不是阈值过滤后的子集。

### 3.2 与其它筛选参数的关系

- 搜索期间 `min_yield` / `max_yield` / `exchange` / `industry` / `index` **全部忽略**：
  已收集但低于股息率阈值、或不符合「选股关注」条件的股票同样能被搜到。
- `codes` 仍然生效，与搜索结果取**交集**（「只看收藏」用它把范围收窄到收藏）。
- 搜索期间用相关度排序取代通用排序（通用排序只按股息率，会把精确命中挤到后面）：
  代码全等 > 代码前缀 > 名称前缀 > 名称包含 > 代码包含；同级按 3 年平均股息率降序、
  再按代码升序（稳定）。
- 搜索是**纯读**：不触发采集、不写盘、不产生任何新采集记录；未收集的股票返回无匹配。

### 3.3 前端行为（apps/dividend）

- 搜索条只在「全部」Tab 出现；「只看收藏」打开时同样可见，但搜索只在收藏范围内生效
  （请求带 `codes=<收藏 codes>`）。**收藏为空时传空字符串而不是不传**——空 `codes`
  会被后端当成「不过滤」，会退化成全池搜索。
- 显示分支优先级：搜索命中 > 只看收藏 > 原有阈值列表。清空搜索恢复原有过滤行为。
- 搜索结果复用现有表格与星标收藏操作（结果项是完整 `DividendStock`），
  不新增关注池、不新增 Tab、不提供手输代码添加入口。
- 无匹配显示明确空状态（说明只覆盖已收集股票、不做全市场搜索）；搜索加载中显示占位骨架，
  不闪空表。已收集总数来自 `/api/dividend/stats`，不硬编码。
- 输入防抖 300ms，响应带序号（慢的旧响应不覆盖新关键词结果）。
- 技术指标：`/m120?min_yield=0` 本来就返回全量，前端保留全量 Map 再按展示 code 派生子集，
  搜索命中的阈值外股票也能拿到 M120/现价，且搜索每次命中不重拉 M120。

## 4. Validation & Error Matrix

| 输入/状态 | 结果 |
|---|---|
| `search` 缺失/空串/纯空格 | 未搜索：原阈值/交易所筛选链路不变 |
| 关键词命中名称 | 返回命中项（忽略阈值） |
| 关键词命中代码（含前导零） | 返回命中项，`code` 保留六位前导零 |
| 关键词无匹配 | `total=0, items=[]`；前端显示空状态；不触发采集 |
| `search` + `min_yield=10` | 仍返回低股息率的已收集股票 |
| `search` + `codes` | 交集：codes 之外的命中项被剔除 |
| `search` + 非法 `codes` | 422（与 batch favorites / codes 过滤同口径） |
| 只看收藏 + 收藏为空 | 不发搜索请求（避免退化成全池搜索），显示「还没有收藏」空状态 |
| 搜索请求失败 | 显示「搜索失败：…」提示，结果清空，不影响原有列表数据 |

## 5. Good / Base / Bad Cases

- Good：股息率 3.3% 的股票（低于当前 5% 阈值）在 `search=长江` 时被搜到。
- Base：`search` 为空白 → 与改动前完全一致的列表。
- Bad：把搜索实现成「过滤前端当前阈值列表」→ 阈值外股票永远搜不到（与 screening 的
  "从收集池出发" 同理）。
- Bad：收藏为空时把 `codes` 传成 undefined → 搜索悄悄变成全池搜索。

## 6. Tests Required

- 后端（`tests/test_stock_search.py`）：名称/代码匹配、前导零、大小写、trim、无匹配、
  阈值/交易所被忽略、空关键词保持原行为、`codes` 交集、相关度排序、HTTP 契约、
  `/stocks/screen` 内部调用链不受影响、不修改池数据、不触发采集。
  必须走**真实路由调用链**（`asyncio.run(routes.get_stocks(...))`），不能只 mock `get_stocks`。
- 前端单测（`src/lib/stock-search.test.ts`）：关键词归一与请求参数拼装。
- 前端 e2e（`e2e/stock-search.spec.ts`）：搜索命中阈值外股票并可收藏、无匹配空状态、
  清空恢复原列表、只看收藏时请求带 `codes`。

## 7. Wrong vs Correct

- Wrong：在前端过滤当前阈值列表；把搜索语义在 Python 与 TypeScript 各写一份；
  用 service 实例方法做路由控制流（mock 会破坏它）。
- Correct：后端在完整收集池上匹配并返回相关度排序；前端只负责输入、展示与收藏范围收窄。
