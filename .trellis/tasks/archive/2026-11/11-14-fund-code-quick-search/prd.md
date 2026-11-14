# 基金代码快速搜索

## Goal

四个基金 tab（债基·雪球三分法 / 股基·雪球三分法 / 债基·市场 / 股基·市场）的
header 右上角加一个**基金代码搜索框**：输入 6 位代码回车，自动跳到该基金所属
的 tab 并打开详情抽屉。同时支持 `/bond?code=xxx` 这类 URL 直达链接。

## 背景

现有能力：
- 四个 tab 页已支持 `?code=xxx` → 自动打开抽屉（`RowDetailDrawer` 的 `stub` 模式，
  纯 code 即可拉详情，不需要先有列表行）。
- 但用户必须自己知道那只基金在哪个 tab，手动切 tab 再翻列表找。

痛点：拿到一个代码，想快速看一眼，现在要猜 tab + 搜索/翻页。

## Requirements

### R1. header 搜索框

- 位置：`FundsHeader` 右侧槽位，「共 N 只」之前，与刷新/筛选按钮同一行。
- 仅四个基金 tab 显示（bond / stock / discovery-bond / discovery-stock）；
  经理页、夏普榜单、走势页不加（用户明确要求）。
- 输入限制：6 位数字（基金代码固定 6 位），`inputMode="numeric"`，maxLength=6。
- 交互：回车提交（不做输入即搜）；提交时禁用按钮防重复。
- 移动端（390px）不撑破 header：小屏可收起为图标按钮，点击展开。

### R2. 路由判定（后端）

新增只读接口 `GET /api/funds/lookup/{code}`，返回该代码应去哪个 tab：

```json
{
  "code": "002910",
  "name": "易方达供给改革混合",
  "found": true,
  "tab": "discovery-stock",
  "market_type": "stock",
  "in_yaml": false,
  "path": "/discovery-stock?code=002910"
}
```

判定优先级（**yaml 名单优先于 market_type**）：

| 判定 | tab | 理由 |
|---|---|---|
| 在 `funds.yaml`（债基名单 31 只） | `bond` | 该基金在债基精选名单里 |
| 在 `funds_stock.yaml`（股基名单 142 只） | `stock` | 该基金在股基名单里 |
| 不在名单 + `market_type='stock'` | `discovery-stock` | 市场 tab 覆盖全市场 |
| 不在名单 + `market_type='bond'` | `discovery-bond` | 同上 |
| 不在名单 + `market_type='other'` | `discovery-stock` | 兜底（混合类归股基市场，与现有 tab 口径一致） |
| 库内查不到该 code | `found: false`，`path: null` | 前端提示「未找到该基金代码」 |

- 两份 yaml 名单**无交集**（实测：31 / 142 / 交集 0），判定无歧义。
- 接口不返回基金详情（详情仍由各 tab 的抽屉自己拉），只做路由。

### R3. URL 直达

- 前端跳转用相对路径（`/discovery-stock?code=002910`），符合 basePath 契约
  （写 `/funds/...` 会被 Next 自动前缀成 `/funds/funds/...` 404）。
- 四个 tab 页已有的 `?code=` 协议**不改**，搜索只是新增一个入口。

### R4. 错误处理

| 情况 | 行为 |
|---|---|
| 空输入 / 非 6 位数字 | 不提交（按钮禁用或即时提示） |
| 后端 `found: false` | 搜索框下方轻提示「未找到 123456」，不清空输入 |
| 后端 5xx / 网络失败 | 提示「查询失败，请重试」 |
| 请求中 | 输入框禁用 + loading 态 |

## Constraints

- 不新增数据库表；判定只读现有 `funds` 表 + 两份 yaml 名单。
- 不改变四个 tab 的现有筛选/分页/URL 参数语义（只新增 `lookup` 接口 + 搜索框）。
- 搜索框不参与筛选状态（不写进 `?qs`），它是一次性跳转动作，不污染可分享的筛选链接。
- 移动端 `document.documentElement.scrollWidth <= 390` 不得因新增搜索框被破坏。

## Acceptance Criteria

- [ ] AC1：`GET /api/funds/lookup/002910` 返回 `tab=discovery-stock`、`found=true`、
      `path=/discovery-stock?code=002910`（实测该代码不在 yaml 名单、market_type=stock）。
- [ ] AC2：yaml 名单内的代码优先判到对应雪球 tab——
      债基名单代码 → `bond`；股基名单代码 → `stock`（即使 market_type 也能归到市场 tab）。
- [ ] AC3：不存在的代码（如 `999999`）返回 `found=false`、`path=null`、HTTP 200
      （不用 404，前端要好处理）。
- [ ] AC4：四个 tab 的 header 都渲染搜索框；经理页/榜单页/走势页**不渲染**。
- [ ] AC5：输入 6 位代码回车 → 跳到对应 tab 且抽屉自动打开（stub 模式拉到详情）。
- [ ] AC6：输入非 6 位、空值、字母 → 无法提交（按钮禁用或输入被过滤）。
- [ ] AC7：`/bond?code=003547` 直接访问 → 抽屉自动打开（现有协议回归不被破坏）。
- [ ] AC8：390px 无横向溢出；搜索框不撑破 header 布局。
- [ ] AC9：后端 pytest 全绿（710 基线 + 新增）；前端 node --test + tsc + build 通过。

## Out of Scope

- 按名称模糊搜索（只支持 6 位代码精确查）
- 搜索历史 / 最近查询
- 键盘上下选择候选（无候选列表，直接跳转）
- 经理页与榜单页的搜索框（用户明确只要四个基金 tab）
