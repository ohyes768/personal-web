# Design — Dividend「全部」页股票搜索

> 关联 PRD：`prd.md`（11-11-dividend-all-stock-search）

## 1. 现状与约束

| 事实 | 位置 | 影响 |
|---|---|---|
| 收集池 = 主 CSV `data/YYYY-MM/近3年股息率汇总*.csv`（列：`股票代码`/`股票名称`/`交易所`/…） | `src/services/data_reader.py` | 搜索的语料只能是这份池子 |
| `GET /api/dividend/stocks` 已支持 `min_yield`/`max_yield`/`exchange`/`industry`/`index`/`sort_by`/`sort_order`/`codes` | `src/api/routes.py:548` | 搜索作为**新查询参数**加在同一入口，不另开接口 |
| `min_yield>0` 走 `filter_by_3y_dividend`（3年平均 ≥ 阈值 **且** 2023/2024/2025 每年分红>0） | `src/services/filter_service.py:170` | 阈值内/外两只股票都可能在池子里；搜索必须绕开它 |
| `/stocks` 的 `codes` 与筛选参数取交集；`codes` 非六位数字 422 | `snapshot-cache-contract.md` §`/stocks codes 精确过滤` | 「只看收藏」可复用 `codes` 做交集 |
| `GET /api/dividend/m120` 用 `min_yield=0` 已返回**全量** M120 | `routes.py:752` | 技术指标可以覆盖阈值外股票，无需新后端通道 |
| 前端「全部」页 `displayData` 只吃阈值后的 `data`；收藏独立（`useWatchlist` + `min_yield=0&codes=`） | `apps/dividend/src/app/page.tsx:613` | 搜索结果要作为**第三条**显示分支 |
| `useTechnicalData` 只把 `stockCodes` 里的 code 映射进 Map，代码变化即重新请求全量 M120 | `apps/dividend/src/lib/hooks.ts:74` | 搜索命中阈值外股票时需要 M120；不能让每次按键都重拉 M120 |
| 前端测试跑法：`node --experimental-strip-types --test src/lib/*.test.ts`；e2e 用 `page.route` 拦截 API | `.trellis/spec/frontend/index.md` | 单测走 node:test，e2e 不依赖真实后端 |

## 2. 方案选择

### 备选 A：前端一次性拉全池，本地过滤
前端 `GET /stocks?min_yield=0` 拿全池 → TS 本地 contains 匹配。

- 优点：前端零延迟过滤、只需一份匹配实现。
- 缺点：全池 payload（含申万/股东/财务合并字段）常驻浏览器；TS 与后端筛选语义要各写一份；`favOnly` 分支同样要本地匹配 → **两套匹配实现**。

### 备选 B：后端加 `search` 参数（**采纳**）
`GET /stocks?search=关键词` 在收集池上做名称/代码包含匹配。

- 优点：语料与语义只有一份（后端）；payload 小；`codes` 交集天然支持「只看收藏」；沿用既有 `/stocks` 入口与响应结构，零新契约类型。
- 缺点：每次按键一次请求 → 用 300ms 防抖 + 响应序号防旧响应覆盖。

**采纳 B**，并让「只看收藏」也走后端（`search` + `codes=<收藏 codes>`），从而不存在第二套匹配实现。

## 3. 后端契约

### 3.1 新增查询参数

`GET /api/dividend/stocks?search=<关键词>`

- 参数写法必须是 `Annotated[Optional[str], Query(...)] = None`：`screen_stocks` / quality analyze 会**在 Python 里直接调用** `get_stocks(...)`，`= Query(None)` 的默认对象在 Python 调用链里不会解析（`snapshot-cache-contract.md` §线程隔离）。
- 关键词归一：`keyword = (search or "").strip()`；空串视为**未传**（保持原行为，一个字节都不变）。

### 3.2 搜索语义

| 维度 | 规则 |
|---|---|
| 语料 | 完整收集池（主 CSV 全量行），**不是**阈值过滤后的子集 |
| 匹配 | `股票名称` 包含关键词 **或** `股票代码`（6 位 str，保留前导零）包含关键词；名称/代码比较不区分大小写 |
| 前导零 | 代码列按 `str().str.zfill(6)` 归一后做子串匹配；`000333` 命中 `000333`，`00333` 也命中（子串），前导零不丢 |
| 与其它筛选的关系 | `min_yield`/`max_yield`/`exchange`/`industry`/`index` 在搜索期间**全部忽略**（PRD 要求能搜到阈值外/不符合选股关注条件的已收集股票） |
| `codes` | 仍然生效，与搜索结果取**交集**（「只看收藏」用它把范围收窄到收藏） |
| 排序 | 相关度优先：代码全等 > 代码前缀 > 名称前缀 > 名称包含 > 代码包含；同级按 3 年平均股息率降序，再按代码升序（稳定） |
| 空结果 | 返回 `total=0, items=[]`，不触发任何采集/写盘 |
| 副作用 | 无。只读主 CSV + 只读辅助快照，**不产生**任何新采集记录 |

### 3.3 代码落点

- `src/services/filter_service.py`：新增 `filter_by_search(df, keyword)`（筛选）与 `sort_by_search_relevance(df, keyword)`（相关度排序）。与既有 `filter_by_*` 同层同风格（DataFrame 纯函数、日志用 `logger.debug`）。
- `src/api/routes.py`：
  - `get_stocks` 增 `search` 参数（`Annotated` 写法）。
  - `_build_stock_list` 增尾部默认参数 `search: Optional[str] = None`（既有测试按关键字调用，不破坏）。
  - 搜索分支：`codes` 交集 → `filter_by_search` → `sort_by_search_relevance` → **跳过** `min_yield`/交易所/行业/指数筛选与通用排序 → 正常组装模型。
  - 搜索分支仍走 `asyncio.to_thread(_build_stock_list, ...)`（同步 Pandas 组装不堵事件循环）。

### 3.4 路由内部调用方

`screen_stocks` / quality analyze 内部 `await get_stocks(...)` **不传 search** → 行为不变。

## 4. 前端设计

### 4.1 新增/改动文件

| 文件 | 变更 |
|---|---|
| `src/lib/types.ts` | `DividendQueryParams` 增 `search?: string \| null` |
| `src/lib/stock-search.ts`（新） | 纯函数：`normalizeSearchKeyword(raw)`（trim，空→空串）、`buildStockSearchParams(keyword, codes?)`（拼 `search`/`min_yield=0`/`codes`） |
| `src/lib/stock-search.test.ts`（新） | node:test 单测（关键词归一、参数拼装） |
| `src/lib/hooks/useStockSearch.ts`（新） | 300ms 防抖 + 响应序号防抖旧覆盖；`enabled=false` 或关键词为空 → 清空结果且不发请求 |
| `src/components/StockSearchBar.tsx`（新） | 搜索输入框 + 清除按钮 + 状态提示（命中数 / 搜索范围说明） |
| `src/lib/hooks.ts` | `useTechnicalData` 改为「保留全量 M120 Map → 按传入 codes 派生子集」，避免搜索每次命中都重拉 M120 |
| `src/app/page.tsx` | 搜索状态、显示分支、空状态、搜索条接入 |

### 4.2 显示分支（`displayData`）

```
activeTab === 'all' && 关键词非空  → searchRows（后端搜索结果 + technical）
activeTab === 'all' && favOnly    → independentFavorites（原行为，收藏独立于阈值）
其余                               → stocksWithTechnical（原行为）
```

- `searchRows` 的每项是完整 `DividendStock`，因此**星标收藏、对比、详情弹框**全部沿用现有链路，不需要新交互。
- 搜索为空（清空）→ 回到原过滤行为。

### 4.3 「只看收藏」+ 搜索

- `favOnly` 打开时，搜索请求带 `codes=<收藏 codes>` → 搜索只在收藏范围内生效。
- `favOnly` 且收藏为空 → 不发搜索请求（空 `codes` 会被后端当成「不过滤」），直接显示既有「还没有收藏」空状态。

### 4.4 技术指标（M120/现价）

`useTechnicalData` 重构：

- state 存**全量** M120 Map（`/m120?min_yield=0` 本来就返回全量）。
- `technicalData` 由 `fullMap` 按传入 `stockCodes` 派生（`useMemo`）。
- 页面传入的 `stockCodes` = 阈值内代码 ∪ 搜索结果代码 → 搜索命中的阈值外股票也有 M120/现价/PE/PB。
- 副作用：M120 只在 `enabled` 变化或 `refreshKey` 变化时重拉（原先 code 集合变化也会重拉）。查询按钮与刷新任务都会 bump `refreshKey`，刷新语义不变。

### 4.5 空状态与文案

- 搜索中：`搜索中…`
- 有结果：`在 {totalCollected} 只已收集股票中匹配到 {n} 只`（`totalCollected` 来自 `/api/dividend/stats`，**不硬编码**）
- 无结果：`没有找到匹配的已收集股票` + 副文案「搜索只覆盖已收集的 {totalCollected} 只股票；未收集的股票不会出现在这里，也不会触发采集。」
- 「只看收藏」+ 搜索无结果：副文案改为「收藏中没有匹配「{keyword}」的股票」。

## 5. 风险与回滚

| 风险 | 缓解 |
|---|---|
| `get_stocks` 新参数写法错误 → 内部 `await get_stocks(...)` 崩溃 | 必须用 `Annotated[..., Query(...)] = None`；后端测试走**真实路由调用链**（不 mock `get_stocks`） |
| 搜索把阈值外股票带进列表 → M120 列空 | `/m120` 数据本就可能缺；表格已有空值处理（`technical` 可选） |
| 每次按键打后端 | 300ms 防抖 + 序号丢弃旧响应 |
| `useTechnicalData` 重构影响既有 Tab | 仅「全部」Tab 使用；改动后回归跑 lint/build + 单测 + e2e |
| 回滚 | 后端/前端改动各自独立回滚；无 DB/写盘副作用 |

## 6. 不做的事

- 不加新 Tab、不建独立关注池、不做全市场搜索、不扩展采集范围。
- 不改「选股关注」筛选规则、不改「挡位监控」行为。
- 不做 Hermes 挡位评估/报告/队列，不动基本面评估入口。
