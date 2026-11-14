# 基金代码搜索改为列表出结果

## Goal

债基 / 股基两个 tab 的「基金代码搜索框」改为：命中后在**主表里出结果**（列表只显示这一只，
行高亮），用户**点这一行**才打开详情抽屉。不再「跳转后自动弹抽屉」。

## 背景（现状）

`apps/fund-select/src/components/FundCodeSearch.tsx` 当前行为：

1. 输入 6 位代码回车 → `GET /api/funds/lookup/{code}` 判定应去哪个 tab
2. `router.push(<path>?code=xxx&focus=1)`
3. 目标页看到 `focus=1` → 清空全部筛选（`?cleared=1`）→ 同时用 `stub` 模式**自动打开详情抽屉**

痛点：用户输入代码后，列表里看不到这只基金（筛选被清空、抽屉盖上来），
「搜到了什么」全靠一个弹框；关掉抽屉后还要自己在列表里再找一遍。

## Requirements

### R1. 搜索命中 → 主表出结果

- 代码搜索命中后，主表**只显示这一只基金**（列表条数 1），该行有明确高亮。
- 列表行复用现有 `FundTable`（相同列、相同对比按钮、相同点击行行为）。
- 搜索态下**不自动打开**详情抽屉；点击该行才打开（走既有 `onRowClick`）。

### R2. 搜索态是 URL 可分享的独立状态

- 新增 URL 参数 `search_code=<6 位代码>`（`/bond?search_code=002910`、`/stock?search_code=002910`）。
- 搜索态**不再破坏用户原有筛选**：不写 `cleared=1`、不清任何筛选维度。
- 顶部 chip 行显示一枚「代码搜索 002910 ×」chip，点 × 即回到原筛选列表。
- 搜索态下改任何一个筛选维度 / 分类 / 每页条数 → 自动退出搜索态（回到正常筛选）。
  改排序不退出（单行排序无意义，但无需打断）。
- 刷新页面（URL 停留）仍处于同一个搜索结果。

### R3. 搜索语义：锁定单只，忽略阈值

- 搜索态下后端**只按 code 取数**，`min_age / min_size_yi / max_dd_3y / min_mgr_exp /
  min_sharpe / exclude_qdii / market_type / source` 全部不生效
  （与股息率「全部」页搜索契约同口径：搜的是库里的基金，不是「当前筛选命中的基金」）。
- 因此库里存在、但没过当前阈值的基金也能被搜出来。
- 已清盘（`is_active = false`）的基金：仍返回该条（代码搜索是「查这一只」，不是浏览在售池），
  由页面照常展示，用户可点开看详情。

### R4. 路由判定保持不变，只改落点形式

- 仍用 `GET /api/funds/lookup/{code}` 判定 tab（yaml 名单优先 + market_type/subtype 兜底）。
- `path` 从 `/bond?code=xxx` 改为 `/bond?search_code=xxx`；`discovery-bond` / `discovery-stock`
  落点收敛到合并后的 `/bond` / `/stock` 页（这两个路由本来就只是 redirect）。
- `/bond?code=xxx`（经理页徽章）语义**不变**：仍然直达并打开抽屉。两个参数各管一件事。

### R5. 空结果与错误

| 情况 | 行为 |
|---|---|
| lookup `found=false` | 保持现状：弹框「未找到该基金」 |
| lookup 网络/5xx | 保持现状：弹框「查询失败」 |
| 输入不足 6 位 | 保持现状：弹框提示 |
| 表格因该代码查不到（如被彻底删除） | 空状态文案改为「该代码不在库中」，并保留清空搜索的入口 |

## Constraints

- 不新增数据库表、不改 ORM schema。
- 不改 `/bond?code=` 直达抽屉协议；不改经理页跳转链接。
- 搜索框仍不参与筛选 chip 的「维度计数」（`activeCount` 不含搜索态）。
- basePath 契约不变：前端只推相对路径，不写 `/funds` 前缀。
- 两个 tab 行为一致（债基 / 股基共用同一个搜索组件与同一个参数）。

## Acceptance Criteria

- [ ] AC1：`/stock` 搜索一个股基代码（如 `002910`）→ 列表只剩这一只、行高亮、**不弹抽屉**。
- [ ] AC2：点击该行 → 详情抽屉打开，内容与「筛选列表里点行」完全一致。
- [ ] AC3：`/bond` 搜索一个债基代码 → 同上（债基 tab 走 `RowDetailDrawerBond`）。
- [ ] AC4：搜索态下 URL 为 `/bond?search_code=003547`（无 `cleared`、无 `focus`）；刷新后仍是该结果。
- [ ] AC5：点 chip 的 × → 回到搜索前的筛选列表（筛选值不丢）。
- [ ] AC6：搜索一个不过阈值的代码（如规模 < 5 亿）→ 仍能搜到。
- [ ] AC7：`GET /api/funds/screen?code=003547&min_size_yi=999` → 仍返回该条（阈值被忽略）。
- [ ] AC8：`GET /api/funds/lookup/003547` → `path=/bond?search_code=003547`。
- [ ] AC9：`/bond?code=003547`（经理页徽章落点）→ 仍自动打开抽屉（回归不破）。
- [ ] AC10：后端 `pytest` 全绿；前端 `node --experimental-strip-types --test` + `tsc` + `build` 通过。

## Out of Scope

- 按名称模糊搜索（仍只支持 6 位代码精确查）。
- 搜索历史 / 最近查询 / 候选下拉。
- 经理页、夏普榜单、走势页的搜索框。
