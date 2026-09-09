# PRD: 基金筛选页分页改造（4 tab）

## 大白话

`/funds/{bond,stock,discovery-bond,discovery-stock}` 四个 tab 的列表接口现在一次性返回全量结果。discovery-* 两个市场 tab 在 akshare 子类全选时单 tab 经常有 2000+ 只基金，前端渲染慢、内存占用高、表格滚动卡顿。

本任务给这四个 tab 统一接入**服务端 page/limit 经典分页**：后端只返回当页数据 + 总命中数，前端只渲染当页 + 一个分页器。

## 目标用户 & 场景

- 债基 tab 用户：当前名单 31 只，分页后体验变化不大（默认 50/页不出现分页器），但 URL 行为与其它 tab 一致。
- 股基 tab 用户：funds_stock.yaml 名单 30 只左右，分页后同样可能不出现分页器。
- **市场 tab 用户（discovery-bond / discovery-stock）**：核心痛点用户。500+ 只起步，分页后渲染数据量恒定，滚动流畅。

## 范围

### 在范围内

1. 后端 4 个 screen 端点接受 `page` / `limit` query 参数，返回当页 items + 总命中数 total
2. 后端 `FilterService._screen` 排序后做切片，保持现有 in-memory 排序（不动 SQL）
3. 前端 `FundFilters` 增加 `page` / `limit` 两个状态字段
4. 前端 4 个 useFundList* hooks 把 page/limit 加进 query 触发串，筛选变更时重置 page=1
5. 前端 4 个 page 组件底部挂分页器组件
6. URL 同步：page / limit 写入查询串，分享链接可还原
7. 排序变更时 page 是否重置：保持当前页（用户在排序字段之间翻页是合理操作）
8. 筛选维度变更时 page 重置为 1（命中集变了，原 page 没意义）

### 不在范围内

- SQL 层做 ORDER BY + LIMIT/OFFSET 改造（保持 in-memory 排序，按需优化）
- 虚拟滚动 / 无限滚动
- cursor 分页
- 单 tab 内排序之外的二次排序
- 后端其它端点（refresh / stats / detail / detail rank 等不分页的接口）
- export / 全量刷新弹窗 / 对比抽屉逻辑

## 功能需求

### F1. 服务端分页参数

| 端点 | 参数 |
|---|---|
| `GET /api/funds/screen` | `page`（≥1，默认 1）、`limit`（1-200，默认 50） |
| `GET /api/funds/stock/screen` | 同上 |
| `GET /api/funds/discovery-bond/screen` | 同上 |
| `GET /api/funds/discovery-stock/screen` | 同上 |

返回结构保持 `{ total: int, items: FundListItem[] }` 不变；`total` 仍是筛后总命中数（不是当前页条数）。

非法值（page<1、limit<1、limit>200）→ 422。

### F2. 后端排序与切片

`FilterService._screen` 当前在 Python 端按 `key_map[sort_key]` 排序后返回全量 items。改造点：

- 计算 `total = len(items)` 后保留不变
- 排序保持原逻辑（None 永远排尾部）
- 在返回前做 `items = items[offset:offset+limit]`
- ach_map 查询仍然用排序**前**的 codes（保持正确性），不影响最终 items

性能影响：当前 4000+ items 排序 < 100ms（Python `list.sort`）；增加 slicing 可忽略。

### F3. 前端筛选 + 分页状态

`FundFilters` 增加两个字段（仅前端 state，不进 `filtersToSearch` 现有逻辑的 numeric 维度列表，但写进 URL）：

```ts
interface FundFilters {
  // ... 现有字段
  page: number;     // 默认 1
  limit: number;    // 默认 50，可选 25 / 50 / 100
}
```

`useFilters` / `parseFiltersFromSearch` / `filtersToSearch` 把 `page` / `limit` 写入查询串：
- 默认值不进 URL（page=1, limit=50 省略，避免 URL 噪音）
- 用户改动 page / limit 后写进 URL
- 任意 numeric 筛选维度变化时强制 page=1
- 排序字段 / 排序方向变化时**保持 page**（用户期望）

### F4. hooks 触发串

`useFundList` / `useStockFundList` / `useDiscoveryBondFundList` / `useDiscoveryStockFundList` 的 query 串里追加 `filters.page` 和 `filters.limit`。`setFilter` 提供一个新方法（或扩展 `setFilter` 语义）让 `page` / `limit` 也能触发 URL 同步。

### F5. 分页器组件

新增 `components/Pagination.tsx`，props：

```ts
interface PaginationProps {
  page: number;          // 当前 1-indexed
  limit: number;         // 当前每页条数
  total: number;         // 总命中数
  onPageChange: (page: number) => void;
  onLimitChange: (limit: number) => void;
}
```

UI：
- 居中显示「第 X-Y 条 / 共 N 条」+ 「第 X / M 页」
- 上一页 / 下一页 按钮（边界禁用）
- 数字输入框跳页（可选；首版可省）
- 每页条数下拉：25 / 50 / 100
- `total <= limit` 时整组件不渲染

放在 `FundTable` 下方，由 4 个 page 组件传入 currentPage / limit / total / handlers。

### F6. URL 同步

| URL 参数 | 写入条件 | 默认 |
|---|---|---|
| `page` | `page !== 1` | 1 |
| `limit` | `limit !== 50` | 50 |

`/funds/bond` 首屏不带 page/limit → `?min_age=3&min_size_yi=5&...` 现状不变。

## 非功能需求

### 性能

- 单页请求响应时间：discovery-bond 全 universe（~500 只）page=1, limit=50 → 后端 P95 < 800ms（含 DB JOIN + Python sort + 4 周期排名查询）
- 前端首屏渲染时间（含 fetch）：市场 tab < 1.5s
- hooks 内已有 `AbortController` 防止竞态，新增 page 切换时复用同一机制

### 兼容性

- URL 不带 page/limit 时行为向后兼容（page=1, limit=50）
- 4 个 screen 端点响应 shape 完全不变（仅 total 含义更清晰、items 长度变小）
- 旧的 curl 调用 / e2e 测试如果断言 items 长度等于 total，会失败 → 必须同步更新这些断言

### 可测性

- 后端 `FilterService._screen` 接受 `page`/`limit` 形参，纯函数测试覆盖：空集、单页、多页、边界（page 越界返回空 items）、None 排序尾部逻辑
- 前端 hooks / URL 解析做单测

## 验收标准

### 后端

1. `GET /api/funds/screen?page=1&limit=10` 返回 items 长度 ≤ 10，total = 筛后总数
2. `GET /api/funds/screen?page=2&limit=10` 返回 items 长度 ≤ 10，与 page=1 无重叠（按当前 sort 排序后切片）
3. `GET /api/funds/screen?page=999&limit=10` 返回 items=[]，total 不变
4. `GET /api/funds/screen?limit=0` 返回 422
5. `GET /api/funds/screen?limit=1000` 返回 422
6. `GET /api/funds/screen?page=0` 返回 422
7. 4 个端点（bond / stock / discovery-bond / discovery-stock）行为一致
8. Python 测试 `pytest backend/fund-select/tests/test_filter_service.py` 和 `test_discovery_filter_service.py` 全部通过

### 前端

1. 4 个 tab 首屏 URL 不带 `page` / `limit` 时正常显示（默认 page=1, limit=50）
2. market_types 切换 → 列表回到 page 1，URL 去掉 `page` 参数
3. sort 字段切换 → page 不变（用户能在新排序下翻页）
4. 点击「下一页」→ URL 出现 `page=2`，列表刷新为第二页
5. 每页条数切到 25 → URL 出现 `limit=25`，列表刷新为 25 条
6. 债基 tab 31 只：默认 50 条不出现分页器
7. 市场 tab 500+ 只：分页器显示「第 1-50 条 / 共 N 条」
8. 直接访问 `/funds/bond?page=3` → 列表加载第 3 页（兼容历史分享链接）
9. `pnpm build`（apps/fund-select）无 TS 错误

### 端到端

1. 在浏览器里打开 `/funds/discovery-stock`，验证首屏只渲染 50 行表格
2. 点击「下一页」，验证 URL 出现 `page=2`，表格换页
3. 在左侧面板改筛选条件，验证 page 自动回到 1
4. 浏览器后退按钮可恢复前一个 page 状态

## 风险与权衡

| 风险 | 影响 | 缓解 |
|---|---|---|
| 在内存排序后再切片，深页仍要遍历全表 | 大 universe 深页性能下降 | 5000 只 × list.sort < 100ms，深页定位靠 offset 切片仍是 O(N) 但 5000 量级可接受；如未来涨到 5w+ 再切 SQL |
| FundAchievementRank 仍按全量 codes 二次查询 | 每页多查一次 ach，但 ach_rows 是按 IN 查询，page 内 codes 是子集，可继续用同一 IN | 暂不优化，等真出现性能瓶颈再调整 |
| 前端 hooks 4 个几乎一样，分页改动要复制 4 处 | 改动面大、易遗漏 | 在 4 个 hook 上同时改；后续若再加 tab 可考虑提取公共 hook |
| URL 多两个参数 | 历史分享链接不向后兼容 | 默认值不进 URL，老链接行为不变 |
| 旧的 e2e / 集成断言假定 items 长度等于 total | 那些断言会失败 | 实施时同步更新；验收里点出 |

## 未来优化（不在本次范围）

- 后端 SQL 层 `ORDER BY + LIMIT/OFFSET`：把排序推到 DB，进一步省内存
- 字段精简：DTO 列表项字段太多，每页 50 条仍偏重，可继续瘦身
- 虚拟滚动 / 无限滚动：替换分页器
- 服务端 cursor 分页：避免 OFFSET 深页性能
