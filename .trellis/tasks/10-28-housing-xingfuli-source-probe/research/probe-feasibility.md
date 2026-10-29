# 主页发现可行性验证（实施前技术门）

日期：2026-10-29，Asia/Shanghai。本机只读探测，未写生产关联、未触发生产采集、未改服务代码。
原始响应留在本机临时目录，不入库；本文只记录与小区身份、入口归属相关的事实，不含经纪人个人信息。

## 结论

技术门**通过**。存在一条完全在平台内、只依赖 `m.xflapp.com` 的可执行发现链：

```
名称搜索（多 channel）→ 候选 neighborhood_id
  → 读小区主页 /xiaoqu/hz-<nid>.html 验证身份 + 取得 rentInNeighbor 入口
  → 房源详情 /zufang/hz-<seed>.html 核验归属
  → 同小区列表 /zufang/neighbor-house-list/hz-<seed>.html 核验列表归属
```

`m.99hdf.com` **不需要**：总小区页在 `m.xflapp.com` 上直接可读（HTTP 200，含 `rentInNeighbor`）。
设计稿中「仅在技术门确认必要后限定 99hdf」的前提**不成立**，实现不得引入该域名。

白金海岸总小区 ID 此前只能靠会话外部检索得到；本次证明它可由系统链路自行发现（见下）。

## 1. 搜索接口的 channel 映射

从当前网页公开脚本 `8018.a306b660.js` 读取（`/f100/api/search` 的 channel 选择逻辑）：

| house_type | channel 常量 | channel_id | 语义 |
|---|---|---|---|
| 1 | `F_SEARCH_COURT` | 94349530162 | 新房 |
| 2 | `F_SEARCH_HOUSE` | 94349530167 | 二手房 |
| 3 | `F_SEARCH_RENT` | 94349530177 | 租房 |
| 4 | `F_SEARCH_NIGHBOR` | 94349530172 | 小区 |

全部走 `GET https://m.xflapp.com/f100/api/search`，公共参数 `city_id=1853`（杭州）、`offset`、`count`。
按 `full_text` 传名称，另带 `page_type`（`house_list` / `rent_list` / `neighborhood_list`）。无需登录、Cookie 或签名。

### 三个 channel 的身份语义不同（关键）

| channel | 条目里的 `neighborhood_id` | 条目自带地址/坐标 |
|---|---|---|
| 二手房 house_type=2 | **小区级（总小区）** | 否（`neighborhood_info` 的 name/address/坐标均为空串） |
| 小区 house_type=4 | **可能是分区身份** | 是（`name`/`address`/`gaode_lng`/`gaode_lat`） |
| 租房 house_type=3 | 种子线索来源 | 否 |

实测同一名称「白金海岸」：
- 租房搜索 → `total=0, items=[]`（漏查）
- 小区搜索 → 2 条，只有 `白金海岸(南区)` `7002863029444411406`、`白金海岸(北区)` `6598511715770433795`
- **二手房搜索 → 20 条全部 `neighborhood_id=6581009489657331972`，`core_info` 的「小区名」=白金海岸（总小区）**

即此前「总小区页只能靠外部检索得到」的障碍，实际是**搜索 channel 选错**，不是平台没有可发现链。

## 2. 各样本实测

### 2.1 正例

| 查询 | channel | 结果 |
|---|---|---|
| 璞悦湾 | 租房 | 20 条全部 `6584028761644073220`，total=24 |
| 璞悦湾 | 二手房 | 20 条全部 `6584028761644073220`，total=51，小区名「万科璞悦湾」 |
| 东方郡 | 二手房 | 20 条全部 `6854812199240614151`，total=133，小区名「欣盛东方郡」（= 现有试点 ID） |
| 白金海岸 | 二手房 | 20 条全部 `6581009489657331972`，total=39，小区名「白金海岸」 |

### 2.2 负例与歧义（必须过滤）

- **不存在名称仍返回成功且非空**：
  - 租房 channel：`status=0, total=29, items=20`，来自 10+ 个互不相关的小区。
  - 二手房 channel：`status=0, total=9514, items=20`，小区名含「幸福」「里」等偶然字样（「幸福人家」「臻珹幸福里」「亲亲家园(幸福里）」「中量畅享幸福里」…）。
  - 结论：HTTP 200 / status=0 / 查询词回显 / items 非空，四者**都不能**单独证明命中。必须按小区名严格匹配 + 读页核验。
- **分区身份 ≠ 总小区**：「白金海岸」的小区搜索只给南北区；读北区主页得到名称「白金海岸(北区)」、地址「金河弄88号」、坐标 (120.188251, 30.203543)；读南区主页名称「白金海岸(南区)」、地址「香溢路88号」、坐标 (120.188354, 30.201706)。两者与内部小区「白金海岸」是**分期/分区冲突**，不得自动绑定。

### 2.3 读页验证身份是必要的

对负例里的噪声 nid `6581010025748103431` 读主页 `https://m.xflapp.com/xiaoqu/hz-6581010025748103431.html`：

- HTTP 200，不是 404，页面正常渲染；
- 主页 `neighborhood_info.name` = **「幸福人家」**，地址「岳家湾89号」，坐标 (120.177664, 30.268853)；
- `rentInNeighbor.total = 0`。

即错误 nid 不会报错，只会给出一个**别的**小区。只看搜索条目无法分辨，必须读页取真实名称与坐标。

## 3. 主页解析契约（已验证）

小区主页 `https://m.xflapp.com/xiaoqu/hz-<nid>.html`：

- SSR 数据在**内联脚本** `window._SSR_DATA = {…};`（不是 `pia-ssr-data`，那是房源页的格式）；
- 路径：`data.loadersData["@neighborDetail_<nid>"].data`；
  - `neighborhood_info`：`id` / `name` / `address` / `gaode_lng` / `gaode_lat`（GCJ02）/ `pricing_per_sqm` 等；
  - `rentInNeighbor`：`total` / `items[]` / `has_more` / `offset` / `search_id`；
- `rentInNeighbor.items[]` 的 `id` 就是**房源种子 ID**，`title` 形如「整租 白金海岸」，`subtitle` 形如「3室2厅/136平/低楼层」，`pricing` 为「5350元/月」；`url` 字段为空，详情 URL 由种子拼装；
- 该模块的条目**不含 `neighborhood_id`**，归属必须靠后续详情页核验；
- 分区页（南/北区）`rentInNeighbor.total = 0` → 属「主页无有效入口」，不是「无房源」。

房源页（种子）沿用现有采集器格式 `<script name="pia-ssr-data" type="application/json">`：

- 详情 `/zufang/hz-<seed>.html`：`query.city=hz`、`query.id=<seed>`，数据内 `neighborhood_id`；
- 同小区列表 `/zufang/neighbor-house-list/hz-<seed>.html`：`query.id=<seed>`、`data._list[]`、`data._hasMore`、`data._updateParams`。

## 4. 白金海岸端到端复现（本次实测，未硬编码）

链路每一步都由上一步的结果推导：

1. 二手房搜索 `full_text=白金海岸` → `neighborhood_id=6581009489657331972`（来自 `neighborhood_info.id`）；
2. 读主页 `/xiaoqu/hz-6581009489657331972.html` →
   - `neighborhood_info`：`name=白金海岸`、`address=香溢路88号`、坐标 (120.188369, 30.203001)；
   - `rentInNeighbor`：`total=31`、`items` 10 条，首条 `id=7406856173871235098`；
3. 详情 `/zufang/hz-7406856173871235098.html` → `query.id=7406856173871235098`，`neighborhood_id=6581009489657331972`；
4. 同小区列表 `/zufang/neighbor-house-list/hz-7406856173871235098.html` → `query.id=7406856173871235098`，`neighborhood_id` 全部为 `6581009489657331972`。

第 3、4 步的 ID 均由第 2 步的 `rentInNeighbor.items[].id` 推导，未在实现中写入常量。

## 5. 东方郡的额外事实

二手房 channel 对「东方郡」只给出**一个** nid `6854812199240614151`（小区名「欣盛东方郡」，地址「春晓路198号」，坐标 (120.213989, 30.197716)），其主页 `rentInNeighbor.total=59`、`items` 10 条。
这与现有试点 ID 一致。**但**租房 channel 此前对同一名称给出东区 `6584040808926675214`、西区 `6584031446065742093` 两个身份，说明不同 channel 的索引口径不一致——**不能**因为二手房 channel 只返回一个身份就断定覆盖关系，仍须按分区冲突规则处理。

## 6. 仍未验证 / 已知边界

- 只测了 4 个名称样本（1 正 1 歧义 1 漏查 1 噪声），**不能**据此外推全量 155 个小区的命中率。
- 未验证种子下架后的恢复路径；`rentInNeighbor` 条目数（10）是首屏条数，不是合格整租样本数。
- 未验证 `house_type=1`（新房）channel 的用途——它返回的是楼盘而非小区，不能当住宅来源。
- 搜索接口是网页内部接口，无稳定性承诺；参数与响应可能随前端发版变化。实现必须对 `status`/字段缺失做失败而非降级处理。
- 本轮请求间隔 ≥6 秒，未做长时连续压测；生产实现须沿用现有 5 秒间隔与一小时冷却。

## 7. 对设计的修正（需回写 design.md）

| design.md 原文 | 实测结论 | 处理 |
|---|---|---|
| 「生产服务不存在已验证搜索引擎连接」，主张外部搜索是唯一出路 | 不成立：二手房 channel 即可发现总小区 | 删去外部搜索依赖，改为多 channel 平台内搜索 |
| 「m.99hdf.com 仅在技术门确认必要后限定使用」 | 不必要，总小区页在 xflapp 可读 | **禁止**引入 99hdf 域名 |
| 「主页搜索只返回分区身份」 | 只对 house_type=4 成立 | 发现需覆盖租/二手/小区三类 channel |
| 候选身份靠搜索条目 | 搜索条目无地址无坐标（二手房 channel） | 强证据统一取自主页 `neighborhood_info` |
| 租/二手搜索可能返回分区身份 | 已观察到（东方郡） | 分区冲突规则保留，按主页名判定 |
