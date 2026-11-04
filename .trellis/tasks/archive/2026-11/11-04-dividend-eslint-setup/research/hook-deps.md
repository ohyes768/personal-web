# Research: apps/dividend — react-hooks/exhaustive-deps 12 条告警逐条判定

- **Query**: 判定 apps/dividend 的 12 条 `react-hooks/exhaustive-deps` 告警是真缺陷还是误报，给出证据与修法建议（不改代码）
- **Scope**: internal（apps/dividend 源码 + eslint-plugin-react-hooks 5.2.0 行为实测）
- **Date**: 2026-11-04

> **重要前提（并发编辑）**：本次调研期间 `apps/dividend/src/app/page.tsx`、`src/lib/hooks.ts`、`src/lib/types.ts` 被另一会话并发修改（git status 显示为 M）。本报告的行号基于 **2026-11-04 14:35 的工作区状态**，与任务描述里的行号（page.tsx:490 / hooks.ts:72 等）有偏移。12 条告警的**集合完全未变**，只是行号平移。

---

## 结论速查表

| 位置（当前行号） | 告警 | 判定 | 修法（一句话） | 是否改运行时行为 |
|---|---|---|---|---|
| `src/components/ScreeningTab.tsx:58` | cleanup 里读 `requestId.current` | **误报**（但暴露了一个真实的脆弱点：卸载只作废序号、没取消请求） | 把 `requestId.current++` 抽成稳定 `useCallback` 包装器，或直接 `eslint-disable` 并注释说明 | **否**（`++` 语义完全等价） |
| `src/app/page.tsx:537` | useEffect 缺 `minYieldInput` | **误报 / 有条件风险**（依赖刻意不加，否则每敲一个字符触发一次 refetch） | 用 `minYieldInputRef` 读最新值（ref 不进依赖数组），或 `eslint-disable` + 注释 | **否**（ref 与闭包读到的是同一个当前值） |
| `src/lib/hooks.ts:87` | useMemo 缺 `stockCodes` + 依赖数组含复杂表达式 | **误报**（`JSON.stringify` 是刻意的深比较去抖） | 提取 `const stockCodesKey = JSON.stringify(stockCodes)` + `useMemo(() => JSON.parse(stockCodesKey), [stockCodesKey])` | **否**（实测：数组内容相同→引用稳定；内容变化→引用变化，与原语义一致） |
| `src/lib/hooks.ts:207` | useCallback 缺 `CACHE_DURATION` | **误报**（常量在函数体内，每渲染重建但值恒定） | 把 `CACHE_KEY_PREFIX` / `CACHE_DURATION` 提到模块作用域 | **否** |
| `src/lib/hooks.ts:300` | 同上（`useStockInfo`） | **误报 + 死代码**（`useStockInfo` 全仓无调用方） | 同 87 行 | **否** |
| `src/lib/hooks.ts:686` | useCallback 缺 `refreshJobs` | **误报**（`refreshJobs` 是每渲染新建的对象字面量，加进依赖会导致回调每渲染重建） | 从 `refreshJobs` 解构出 `accept`（它由 useCallback 产出，引用稳定），依赖改用 `accept` | **否**（`accept` 引用稳定，依赖数组实际不变） |
| `src/lib/hooks.ts:719` | 同上（`updateFinancial`） | **误报** | 同 686 行 | **否** |
| `src/lib/hooks/useQualityAnalysis.ts:128` | useEffect 缺 `stopPolling` | **误报**（`stopPolling` 是 `useCallback([])`，引用终身稳定） | 直接把 `stopPolling` 加进依赖数组 | **否**（引用稳定 → 依赖数组实际不变 → effect 不会多跑） |
| `src/lib/hooks/useRealtimePrices.ts:19` | useMemo 缺 `codes` + 依赖数组含复杂表达式 | **误报** | 同 87 行（`codesKey` + `JSON.parse`） | **否** |

**12 条全部是误报，没有一条是真实的 stale closure / 竞态 / 读到过期数据。**

关键风险不在"要不要加依赖"，而在**加错依赖会引入无限重渲染**——详见下文「引用稳定性」一节。

---

## 逐条展开

### 1. `ScreeningTab.tsx:58` — cleanup 里读 `requestId.current`

**告警原文**：
```
The ref value 'requestId.current' will likely have changed by the time this effect
cleanup function runs. If this ref points to a node rendered by React, copy
'requestId.current' to a variable inside the effect, and use that variable in the
cleanup function.
```

**证据**（`src/components/ScreeningTab.tsx:35-59`）：
```ts
const requestId = useRef(0);
const query = useCallback(async (next: ScreeningConditions) => {
  appliedConditions.current = next;
  const id = ++requestId.current;        // 每次请求领一个递增号
  setLoading(true); setError(''); setSelected(new Set()); setResult(null); ...
  try {
    const response = await dividendApi.screenStocks(next);
    if (id === requestId.current) setResult(response);   // 只接受"最新号"的响应
  } catch (err) {
    if (id === requestId.current) setError(...);
  } finally {
    if (id === requestId.current) setLoading(false);
  }
}, []);

useEffect(() => {
  ...
  setConditions(next); void query(next);
  return () => { requestId.current++; };   // ← line 58，cleanup 里读+写 ref
}, [query]);
```

**请求生命周期追踪**（任务特别要求的核查项）：
- 发请求的 hook：**不是** useRealtimePrices/独立 hook，就是本文件里的 `query` → `dividendApi.screenStocks` → `directClient.post` → `fetch`。
- 全仓 `grep -rn "AbortController\|signal\|abort" src/` → **0 命中**。即：**没有任何地方真正 abort 请求**。
- 所以 cleanup 的 `requestId.current++` 做的**不是**取消请求，而是"作废序号"：让所有在途请求的 `id !== requestId.current`，其 `setResult/setError/setLoading` 全部被跳过。这等价于"忽略卸载后的迟到响应"，是防 `setState on unmounted component` 的标准手法。

**"取消请求是否会取消错的那个"？—— 不会，但有一个真实的脆弱点**：
- `query` 是 `useCallback([])`，引用终身稳定；`useEffect` 依赖 `[query]`，因此**这个 effect 只在挂载时跑一次、卸载时 cleanup 一次**。cleanup 时 `requestId.current` 必然是"当前最新号"，作废的是**所有**在途请求（不是某一个）——语义正确。
- 真正的脆弱点：**cleanup 只作废序号，不取消 fetch**。请求仍会跑完、仍会打到后端，只是响应被丢弃。若要真正取消，需要引入 `AbortController` 并把它透传到 `ApiClient.request`（`RequestInit.signal`）。那是**功能增强**，不属于本次 ESLint 清理范围。

**判定：误报。** 规则触发的原因已从插件源码确认（`node_modules/eslint-plugin-react-hooks/cjs/eslint-plugin-react-hooks.development.js:1336-1395`）：该检查只对 "React 托管的 ref" 报警，判定方式是"在同一个 ref 的**所有引用**里能否找到 `ref.current = <某值>` 形式的赋值"。`requestId.current++` 是**自增表达式**（UpdateExpression），不是 AssignmentExpression，所以规则没认出来。实测验证：

```
requestId.current = requestId.current + 1;   → 不报警（被识别成"用户自己管的 ref"）
requestId.current++;                          → 仍然报警
```
即：**把 `++` 改写成 `= requestId.current + 1` 就能消警，语义完全等价**。但这依赖插件实现的内部判定，比较脆。

**推荐修法**（按稳健性排序）：
1. **抽成稳定包装器**（推荐）：`const invalidateRequests = useCallback(() => { requestId.current += 1; }, []);`，cleanup 里调 `invalidateRequests()`，依赖数组加 `invalidateRequests`。语义不变，且不依赖插件内部判定。实测此写法 0 告警。
2. `eslint-disable-next-line react-hooks/exhaustive-deps` + 一行注释说明"这是自增作废序号，不是 React 托管的 DOM ref"。最省事，但把说明留在代码里。
3. 改写成 `requestId.current = requestId.current + 1;`。最省事且不改结构，但依赖插件实现细节。

**运行时行为变化：以上全部为"否"。**

---

### 2. `page.tsx:537` — useEffect 缺 `minYieldInput`

**证据**（`src/app/page.tsx:531-539`）：
```ts
const lastRevisionRef = useRef(0);
useEffect(() => {
  if (!refreshJobs.revision || lastRevisionRef.current === refreshJobs.revision) return;
  lastRevisionRef.current = refreshJobs.revision;
  if (activeTab !== 'all') return;
  setRefreshKey(k => k + 1);
  void refetch({ min_yield: parseFloat(minYieldInput) || 0, sort_by: 'avg_yield_3y', sort_order: 'desc' });
}, [refreshJobs.revision, refetch, activeTab]);
```

**这个 effect 的语义**：只在"后台刷新任务完成（revision 变化）"时按**当前**阈值重拉一次列表。

**为什么要把 `minYieldInput` 排除在依赖外**：`minYieldInput` 是 `<input type="number">` 的受控值（`src/app/page.tsx:689`），**每敲一个字符就变一次**。若把它放进依赖数组，用户在阈值框里输入 "3.5" 会触发 3 次 `refetch` + 3 次 `setRefreshKey`（后者会让 `<DividendTable key={refreshKey}>` 整表重挂载）。这是典型的"加依赖导致请求风暴"。

**这是不是 stale closure？—— 不是（在本仓库的当前结构下）**：
effect 体内的 `minYieldInput` 读取发生在 **effect 执行的那一刻**，而 React 每次渲染都会用最新的 `minYieldInput` 重建 effect 闭包；当 `refreshJobs.revision` 变化触发重跑时，用的是**那次渲染的闭包**，其 `minYieldInput` 就是当时的最新值。所以读到的不是过期数据。

> 严格说，React 保证的是"effect 运行时闭包来自最近一次渲染"。若在**同一次渲染内** `minYieldInput` 变了而 revision 没变，effect 不重跑（这正是期望行为）。若 revision 变了，必然伴随一次新渲染，闭包里的 `minYieldInput` 就是新值。**结论：读到的一定是触发时刻的最新值，无 stale 问题。**

**修法**：
1. **用 ref 读最新值**（推荐，已实测 0 告警）：
```ts
const minYieldInputRef = useRef(minYieldInput);
useEffect(() => { minYieldInputRef.current = minYieldInput; }, [minYieldInput]);
...
void refetch({ min_yield: parseFloat(minYieldInputRef.current) || 0, ... });
```
2. `eslint-disable-next-line react-hooks/exhaustive-deps` + 注释"刻意不跟随输入框逐字变化"。

**运行时行为变化：均为"否"。**

---

### 3 & 5. `hooks.ts:87` / `hooks.ts:300` — useMemo 缺 `stockCodes` + 复杂表达式依赖

**证据**（`src/lib/hooks.ts:86-87`，`useTechnicalData` 内）：
```ts
// 使用 useMemo 缓存 stockCodes，避免无限循环
const memoizedStockCodes = useMemo(() => stockCodes, [JSON.stringify(stockCodes)]);
```
两条告警同时出现：
```
has a missing dependency: 'stockCodes'
has a complex expression in the dependency array. Extract it to a separate variable so it can be statically checked.
```

**为什么这样写**：调用方 `page.tsx:516` 的 `stockCodes` 是 `useMemo(() => data.map(s => s.code), [data])`——**每次 `data` 变化都是新数组引用**。而 `useTechnicalData` 内部的 effect 依赖 `[memoizedStockCodes, refreshKey]`。若 memo 直接依赖 `stockCodes` 引用，`data` 每变一次（每次 refetch）effect 就重跑一次 → 重复拉 M120。

用 `JSON.stringify(stockCodes)` 做 key = **按内容去抖**：代码集合不变时 memo 返回同一个引用，effect 不重跑。**这是刻意的、有注释说明的设计，不是疏忽。**

**"引用稳定性"分析（任务特别要求的核查项）**：
| 依赖 | 来源 | 引用稳定性 | 直接加进依赖会怎样 |
|---|---|---|---|
| `stockCodes`（hooks.ts:87） | `page.tsx:516` `useMemo(..., [data])` | **不稳定**（`data` 变则新引用） | effect 每次 refetch 都重跑 → 重复请求 M120。**不是无限重渲染**（不会自激），但是行为退化 |
| `stockCodes`（hooks.ts:300） | `useStockInfo` 无任何调用方 | N/A | 无影响 |
| `codes`（useRealtimePrices.ts:19） | `page.tsx:631` `useMemo`（稳定）**和** `ScreeningTab.tsx:85` `result?.items.filter(...).map(...) \|\| []`（**每次渲染新数组**） | **两种都有** | 若用引用做依赖，`ScreeningTab` 场景下 `eligibleCodes` 每渲染变一次 → effect 每渲染重跑 → **真正的无限重渲染 + 无限请求**。这是最危险的一条 |

> `ScreeningTab.tsx:85` 的 `eligibleCodes` 是 render 内联表达式，**每次渲染必然是新数组**（`result` 不变时 `.filter().map()` 仍返回新数组）。这就是 `useRealtimePrices` 必须按内容去抖的根本原因。

**修法**（3 处统一）：
```ts
const stockCodesKey = JSON.stringify(stockCodes);
const memoizedStockCodes = useMemo(() => JSON.parse(stockCodesKey) as string[], [stockCodesKey]);
```
- 提取 `stockCodesKey` 消除 "complex expression" 告警；
- 回调体只引用 `stockCodesKey`，消除 "missing dependency" 告警；
- `JSON.parse` 出来的数组内容与 `stockCodes` 完全一致，**引用稳定性语义不变**：内容变→新引用；内容不变→同一引用。

实测：`useMemo(() => JSON.parse(codesKey) as string[], [codesKey])` → 0 告警。

**运行时行为变化：否。**（已实测：memo 的引用稳定性与原写法一致——内容相同则引用稳定，内容变化则引用变化。）

> 附注：`hooks.ts:300` 所在的 `useStockInfo` **全仓无调用方**（`grep -rn "useStockInfo" src/ e2e/` 只命中定义本身），属于死代码。它和 `dividendApi.getStocksInfo`（`api.ts:124`）一起是死链。按 CLAUDE.md 第 3 条"发现无关死代码要提及、不要擅自删除"，此处只登记不建议本次删。

---

### 4. `hooks.ts:207` — useCallback 缺 `CACHE_DURATION`

**证据**（`src/lib/hooks.ts:183-184`，`useRefreshPrice` 内）：
```ts
export function useRefreshPrice() {
  const [refreshStates, setRefreshStates] = useState<Map<string, RefreshState>>(new Map());

  // 缓存相关
  const CACHE_KEY_PREFIX = 'dividend-deviation-';
  const CACHE_DURATION = 24 * 60 * 60 * 1000; // 1天（毫秒）
  ...
  const getCache = useCallback((code: string): DeviationCache | null => {
    ...
    if (now - data.timestamp > CACHE_DURATION) { ... }   // ← 207 行告警
    ...
  }, []);
```

**为什么这是误报**：`CACHE_DURATION` 在**函数体内**声明，每渲染重建，但**值恒定**（`24*60*60*1000` 是编译期常量表达式）。`getCache` 的 `useCallback` 依赖 `[]`，闭包捕获的 `CACHE_DURATION` 值永远是同一个 → 闭包里**不可能读到过期值**。

插件之所以报警，是因为它按"函数体内声明的变量"一律视为可变引用（实测：`const LITERAL = 86400000` 在函数体内**不报警**，但 `const COMPUTED = 24 * 60 * 60 * 1000` **报警**——插件只对"字面量"和"模块级常量"放行，对**表达式**形式的 const 不放行）。

**修法**：把两个常量提到**模块作用域**（`hooks.ts` 文件顶部，`import` 之后）：
```ts
/** 实时价偏离度本地缓存：key 前缀与有效期（1天） */
const CACHE_KEY_PREFIX = 'dividend-deviation-';
const CACHE_DURATION = 24 * 60 * 60 * 1000; // 1天（毫秒）
```
模块级常量插件直接放行。实测 0 告警。

**运行时行为变化：否。**（值恒定，只是声明位置从函数体移到模块体。）

---

### 6 & 7. `hooks.ts:686` / `hooks.ts:719` — useCallback 缺 `refreshJobs`

**证据**（`src/lib/hooks.ts:686` / `:719`）：
```ts
const updateM120 = useCallback(async (codes?: string[]) => {
  ...
  const result = await dividendUpdateApi.refreshM120(codes);
  refreshJobs.accept(result);
  ...
}, [refreshJobs.accept]);   // ← 依赖写的是 refreshJobs.accept，插件要的是 refreshJobs
```

**关键事实：`refreshJobs` 本身是每渲染新建的对象**（`useRefreshJobs.ts:66`：`return { jobs, errors, revision, accept };` —— 每次调用都返回新字面量）。

所以插件建议的"把 `refreshJobs` 加进依赖"是**错的**：那会让 `updateM120` / `updateFinancial` **每渲染都重建**。这两个函数在 `page.tsx` 里被当事件回调传给 `DataUpdateDrawer` / `UpdateTaskRow`（`page.tsx:815/871/888`），重建本身不至于成环，但会让下游 memo 失效、且和插件本意（"读到的值可能是过期的"）完全无关。

**`refreshJobs.accept` 引用是稳定的**（`useRefreshJobs.ts:29-32`）：
```ts
const accept = useCallback((job: RefreshJob) => {
  generations.current[job.kind]++;
  track(job);
}, [track]);   // track 是 useCallback([])，引用终身稳定
```
所以依赖数组写 `refreshJobs.accept` **本来就完全正确**——它每渲染都是同一个函数引用，`useCallback` 不会重建，闭包里的 `accept` 也不会过期。

**修法**（推荐）：把 `accept` 从对象里解构出来，让依赖数组直接引用它，插件就不会要求整个 `refreshJobs`：
```ts
// accept 由 useRefreshJobs 内部 useCallback 产出，引用稳定；单独取出以便作为依赖
const { accept: acceptRefreshJob } = refreshJobs;
...
const updateM120 = useCallback(async (codes?: string[]) => {
  ...
  acceptRefreshJob(result);
  ...
}, [acceptRefreshJob]);
```
（解构出来的新局部变量 `acceptRefreshJob` 每渲染都是同一个函数引用，与原 `refreshJobs.accept` 等价。）

**运行时行为变化：否。**（依赖数组的实际内容不变——`acceptRefreshJob` 与 `refreshJobs.accept` 是同一个函数引用。）

---

### 8. `useQualityAnalysis.ts:128` — useEffect 缺 `stopPolling`

**证据**（`src/lib/hooks/useQualityAnalysis.ts:65-70` 与 `:111-128`）：
```ts
const stopPolling = useCallback(() => {
  if (pollTimer.current) {
    clearTimeout(pollTimer.current);
    pollTimer.current = null;
  }
}, []);          // ← 依赖数组为空，引用终身稳定

useEffect(() => {
  mounted.current = true;
  void refreshScores();
  void (async () => { ... startPolling(discovered.job_id); })();
  return () => {
    mounted.current = false;
    stopPolling();          // ← 128 行告警
  };
}, [refreshScores, startPolling]);
```

**判定：误报，且这是 12 条里最容易修的一条。**
`stopPolling` 是 `useCallback([])` → 引用终身稳定 → 闭包不可能读到过期值。**直接把 `stopPolling` 加进依赖数组即可**：

```ts
}, [refreshScores, startPolling, stopPolling]);
```

实测已验证：该改法消除告警，**且不会引入 "unnecessary dependency" 误报**（因为 `stopPolling` 确实在 effect 体内被使用）。

**运行时行为变化：否。**（`stopPolling` 引用稳定 → 依赖数组实际内容不变 → effect 的触发时机完全不变，不会多跑一次。）

---

### 9. `useRealtimePrices.ts:19` — useMemo 缺 `codes` + 复杂表达式依赖

**证据**（`src/lib/hooks/useRealtimePrices.ts:18-19`）：
```ts
// 缓存 codes 引用，避免每次渲染触发 fetch（与 useTechnicalData 一致）
const memoCodes = useMemo(() => codes, [JSON.stringify(codes)]);
```

**这是 12 条里"加错依赖后果最严重"的一条**（见上文第 3 节的引用稳定性表）。`ScreeningTab.tsx:86` 传进来的 `eligibleCodes` 是 render 内联 `result?.items.filter(...).map(...) || []`——**每次渲染都是新数组**。若按插件建议把 `codes` 加进 `useMemo` 依赖，`memoCodes` 每渲染变一次 → 下面的 `useEffect([memoCodes])` 每渲染重跑 → `dividendApi.getPrices` 每渲染发一次 → `setPriceMap` → 再渲染 → **无限渲染循环 + 请求风暴**。

**修法**：同第 3 节，统一为
```ts
const codesKey = JSON.stringify(codes);
const memoCodes = useMemo(() => JSON.parse(codesKey) as string[], [codesKey]);
```

**运行时行为变化：否。**

---

## 附加确认：api-client.ts 的 6 处 `any`

这 6 条是 **error 级**（`@typescript-eslint/no-explicit-any`，severity=2），必须处理才有 `npx eslint .` 退出码 0。

### 现状与影响面

| 位置 | 现状 | 影响面 |
|---|---|---|
| `api-client.ts:4` | `export interface ApiResponse<T = any>` | **`ApiResponse` 只在本文件内被引用 2 次**（`:4` 定义、`:58` 用作 `const result: ApiResponse<T>`），全仓无外部 import。`:58` 处的 `T` 总是显式传入（`request<T>` 的 T），**默认的 `any` 从未被使用** |
| `:67` | `get<T>(endpoint, params?: Record<string, any>)` | 调用方全部走 `api.ts`，参数类型是 `DividendQueryParams`（interface）、`M120Params`（内联字面量类型）、`BoardInfoRequest`（interface）等 |
| `:94/99/104` | `post/put/patch<T>(endpoint, data?: any)` | body 参数，实参都是对象字面量或已定义类型 |
| `:109` | `delete<T>(endpoint, params?: Record<string, any>)` | 仅 `api.ts:161` `removeFavorite` 调用，**不传 params** |

### `ApiResponse` 是否真的"用得上"？

`ApiResponse` **没有外部消费者**。而且注意：`directClient`（`'direct'` 模式）走的分支是 `if (this.mode === 'direct') return response.json() as Promise<T>;`——**根本不会碰 `ApiResponse`**。`ApiResponse` 只服务于 `apiClient`（`'wrapped'` 模式），而 **`apiClient` 全仓无任何调用方**（`grep -rn "\bapiClient\b" src/ e2e/` 只命中定义行 `:121`）。

→ **`ApiResponse` + `apiClient` 是死代码**。按 CLAUDE.md 第 3 条，此处只登记不建议本次删；但如果决定删，`ApiResponse<T = any>` 这条 error 会**直接消失**，比改成 `unknown` 更彻底。

### `Record<string, any>` → 改成什么最安全？（关键坑）

**坑：`Record<string, any>` 的参数位不能直接换成 `Record<string, unknown>`。**

TS 的"隐式索引签名"规则只对**类型别名（type alias）**生效，**对 interface 不生效**。实测：
```
interface DividendQueryParams { min_yield?: number | null; ... }
const x: Record<string, unknown> = p;   // ❌ TS2322: Index signature for type 'string' is missing
const y: Record<string, any> = p;       // ✅ 通过（any 走的是另一条豁免路径）
```
而 `api.ts` 传进来的正是 interface（`DividendQueryParams`、`BoardInfoRequest`）。所以直接改成 `Record<string, unknown>` 会在 `api.ts` 的调用点炸一片。

**已实测通过的两个方案**：

**方案 A（推荐，改动最小，只动 api-client.ts 一个文件）**：
```ts
export interface ApiResponse<T = unknown> { ... }

async get<T, P extends object = object>(endpoint: string, params?: P): Promise<T> { ... }
async delete<T, P extends object = object>(endpoint: string, params?: P): Promise<T> { ... }
async post<T>(endpoint: string, data?: unknown): Promise<T> { ... }
async put<T>(endpoint: string, data?: unknown): Promise<T> { ... }
async patch<T>(endpoint: string, data?: unknown): Promise<T> { ... }
```
- `P extends object = object`：约束 params 必须是对象，但**不要求索引签名**，所以 interface 实参直接通过。
- `data?: unknown`：body 参数收紧为 unknown，`JSON.stringify(data)` 依然成立（`JSON.stringify` 接受 `any`；实测 `JSON.stringify(u: unknown)` 通过）。
- **对调用方零改动**，`api.ts` 一行不用动。
- **实测：整个 src typecheck EXIT=0，eslint 0 error。**

> 注意 `P extends object = object` 的 `= object` 默认值不可省：若写成 `P extends object`（无默认），当调用方显式写了 `<T>`（如 `directClient.get<DividendListResponse>('/api/dividend/stocks', params)`）时，TS 会报 `TS2558: Expected 2 type arguments, but got 1`——**这正是 `api.ts` 里所有 `get<T>` 调用的写法**。加了 `= object` 默认值后，P 取默认 `object`，实参只受"是对象"约束。实测确认。

**方案 B（更严格，但需连带改 types.ts）**：
- `api.ts` 的 `DividendQueryParams`、`BoardInfoRequest` 从 `interface` 改成 `type` 别名（隐式索引签名才生效）；
- `params?: Record<string, unknown>` + body 内 `Object.entries(params).filter(...).map(([k,v]) => [k, String(v)])`（因为 `unknown` 不能直接塞进 `URLSearchParams`）。
- 实测：需同时改 `types.ts` 两个 interface + `api-client.ts` 的 body，typecheck EXIT=0。

**运行时行为变化**：方案 A —— **否**（`data?: any → unknown` 只影响类型层，运行时 `JSON.stringify` 行为一致；`params` 的运行时处理代码一行未动）。方案 B —— **有轻微风险**：`String(v)` 把 number 变成字符串，与原来 `URLSearchParams` 隐式转换的结果一致（实测 `URLSearchParams` 内部就是 `String()`），但 `append(k, v)` 那条分支原本传的是原始值，改后要显式 `String(v)`，需逐条核对。

**推荐方案 A**：改动面最小（1 文件、6 行）、零调用方改动、typecheck + lint 双绿。

---

## 附加确认：`hooks.ts:78` 的 `minYield` 未使用参数能否直接删

**证据**：
```ts
// src/lib/hooks.ts:74-78
export function useTechnicalData(
  enabled: boolean,
  stockCodes: string[],
  refreshKey?: number,
  minYield?: number,        // ← 78 行：'minYield' is defined but never used
) {
```
函数体内 `minYield` **完全未被使用**（实测 `sed -n '74,150p' src/lib/hooks.ts | grep minYield` 只命中参数声明本身）。

**能不能直接删？—— 能，但要连带改调用方。**

调用方只有一处（`src/app/page.tsx:519`）：
```ts
const { technicalData } = useTechnicalData(activeTab === 'all', stockCodes, refreshKey, parseFloat(minYieldInput) || 0);
```
删掉第 4 个参数后，调用方要改成：
```ts
const { technicalData } = useTechnicalData(activeTab === 'all', stockCodes, refreshKey);
```

**注意事项**：
1. **不能只删参数不改编调用方**——TS 会报 `Expected 3 arguments, but got 4`。两处必须同一次改。
2. `minYield` 是**第 4 个位置参数**，删它不影响前 3 个的位置，前 3 个实参 `activeTab === 'all'` / `stockCodes` / `refreshKey` 不动。
3. **运行时行为变化：无。** 参数从未被读取，删掉后函数行为完全一致。`parseFloat(minYieldInput) || 0` 这个实参表达式本身只是求值后丢弃，删掉连这点开销都没了。
4. 顺带一提：这个参数本来就是**语义残留**——`useTechnicalData` 内部调 `dividendApi.getM120Data({})` **故意不传 min_yield**（代码注释：「不传 min_yield，后端默认 0 = 不过滤，拿全部股票的实时价格」）。所以删参数反而让代码更自洽。

**替代方案**：若不想动函数签名，可保留参数但改名为 `_minYield`——**实测无效**（`@typescript-eslint/no-unused-vars` 默认 `args: "after-used"`，下划线前缀不被豁免；实测 `_minYield` 仍报警）。所以只剩"删参数 + 改编调用方"这一条干净路径。

---

## 本次应修 / 本次只登记不修（建议清单）

> 以下是**建议**，最终取舍请主 agent 决定。

### 建议本次修（高价值、低风险、已实测验证）

| # | 事项 | 理由 | 验证 |
|---|---|---|---|
| 1 | **api-client.ts 6 处 `any`**（error 级，不修则 eslint 退出码非 0） | 阻断 lint 通过。方案 A：6 行改动 + 零调用方改动 | typecheck EXIT=0，eslint errors=0（实测） |
| 2 | **12 条 exhaustive-deps** 按本报告逐条修 | 全部误报，但修法要选对，否则会引入**无限重渲染**（尤其 `useRealtimePrices`） | 全套改动后 typecheck EXIT=0，eslint errors=0 / exhaustive-deps=0（实测） |
| 3 | `hooks.ts:78` `minYield` 参数 + `page.tsx:519` 调用方 | 唯一调用方一处，删除零风险 | 已在同一沙箱验证 |

### 建议只登记不修

| # | 事项 | 理由 |
|---|---|---|
| 4 | **22 条 `@typescript-eslint/no-unused-vars` warning** | 任务说明已定为"纯死代码、不在本次重点"。多数是未使用的 import/解构变量，删除会牵动类型导入 |
| 5 | **`useStockInfo` + `dividendApi.getStocksInfo` 死链** | 全仓无调用方。删是清理、不删无害。CLAUDE.md 第 3 条：提及而不擅自删 |
| 6 | **`ApiResponse` + `apiClient`（'wrapped' 模式）死代码** | 全仓无调用方。删可一次性消灭 `ApiResponse<T = any>` 那条 error；但属于功能面清理，超出"修 lint"范围 |
| 7 | **`ScreeningTab` 真正取消在途请求（AbortController）** | 当前只作废序号不 abort。属功能增强，不属 lint 清理。已记入第 1 条的分析 |
| 8 | **`page.tsx` 阈值输入触发 refetch 的请求风暴隐患** | 已用 ref 规避。若将来要"输入即筛选"，需产品决策 |

### 落地时的注意事项

1. **并发编辑**：本次调研期间 `page.tsx` / `hooks.ts` / `types.ts` 被另一会话修改。**实施前必须重新 `git diff` 核对**（CLAUDE.md 与 MEMORY「多会话并行共仓库」都强调了这点），行号以实施时的实际文件为准。
2. **不要用 `npx eslint --fix`**：本仓库的 `eslint-plugin-react-hooks@5.2.0` 对 exhaustive-deps **没有提供 autofix**（实测 `--fix-dry-run` 对 `refreshJobs.accept` 与 `JSON.stringify(codes)` 两种情形都输出 "no fix available"），所以 `--fix` 既帮不上忙、也不会自动改坏——但也意味着这 12 条**只能手工按本报告修**。若将来升级到带 autofix 的插件版本，需重新评估：`refreshJobs.accept → refreshJobs`（**导致每渲染重建回调**）与 `JSON.stringify(codes) → codes`（**导致 `useRealtimePrices` 无限重渲染**）这两种自动修复方向都会造成退化。
3. `eslint.config.mjs` 已存在且本次**不要删改**（任务明确要求）；本报告的所有修法都不需要改它。

---

## 附：本次调研的验证方式

所有"实测"结论均在**沙箱副本**上跑通，未改动仓库任何产品代码：

- 沙箱位置：`.trellis/tasks/11-04-dividend-eslint-setup/research/.tmp/`（`src` 为 `apps/dividend/src` 的副本，`node_modules` 用 Windows junction 指向真目录）
- 验证命令：
  - `npx eslint src --format json`（沙箱内，配同一份 `eslint.config.mjs`）
  - `node <apps/dividend>/node_modules/typescript/bin/tsc -p tsconfig.json`（沙箱内，严格模式，含 `strict`）
- 插件行为确认：直接读 `node_modules/eslint-plugin-react-hooks/cjs/eslint-plugin-react-hooks.development.js:1336-1395` 的 ref-cleanup 检查源码，并用 `eslint --stdin` 逐条验证候选写法。
- 基线（当前工作区，`apps/dividend`）：`errors=6 warnings=34`，其中 `no-explicit-any=6`（error）、`exhaustive-deps=12`、`no-unused-vars=22`（均 warning）。
