# 幸福里来源发现与按需探查契约

> 2026-10-29 建立。系统的“找来源”能力：平台内多通道搜索 → 读小区主页验证身份 → 主页内找真实租房入口 → 核验后绑定。
> 关键结论：**搜索响应永远不是身份证据**，身份只来自小区主页；**平台内可执行，不需要外部搜索引擎**。

## 当前网页入口（2026-10-29）

- `GET/POST/DELETE /rentals/source-matching` 独立查询、启动/继续、取消来源匹配；POST为202。SourceMatchingService顺序执行幸福里probe，保存小区级remaining/outcomes和计数到rentals/source_matching_job.json；绝不采集整租样本或发布租金快照。人工跳过、拒绝、已有幸福里来源不自动重做。
- 网页`/rentals/refresh`明确启用`RentalRefreshService(xingfuli_only=True)`，只采已关联幸福里的合资格小区，不运行任何来源发现；零关联返回422并提示先匹配。历史默认构造器保留独立旧库测试/工具兼容，不能作为网页运行配置。
- 匹配、租金采集、单小区probe共用task_lock与busy检查，不能并发网络执行。取消保留未处理队列；未取消的在途任务可在服务启动时恢复；GET不启动网络。当前断点粒度为小区，中断中的小区可能重查。
- 旧Fang搜索、链接导入、候选确认及review bind写入口返回410；来源待处理清单按幸福里probe状态投影。人工选择主页仍走probe/select，不复用旧Fang候选确认。
- 来源绑定在发布锁下复查资格、取消和人工跳过；自动匹配不绕过人工拒绝，显式单小区探查保留重新处理语义。

## 1. Scope / Trigger
修改 `xingfuli_transport.py`、`xingfuli_discovery.py`、`rental_reference/xingfuli_sources.py`、
`rental_reference/probe.py`、`rental_source_routes.py` 的探查路由，或 `refresh.py` 的幸福里自动发现前必读。

## 2. Signatures
- `XingfuliTransport(timeout, *, directory, fetcher, delay, cancel_event, validate)`：共享的限速/冷却/取消/大小限制/验证页检测；
  `xingfuli_rentals.XingfuliClient` 与 `xingfuli_discovery.XingfuliDiscovery` 都继承它，两者共用 `rentals/xingfuli_request` 锁与
  `xingfuli_request_state.json` 冷却状态。
- `XingfuliDiscovery.search(name, channel) -> {neighborhood_id: {name, seeds}}`；`homepage(nid) -> dict`；
  `listing_owner(seed) -> str|None`；`listing_owner_from_list(seed, nid) -> bool`。
- `parse_homepage(html, expected_id)`：小区主页 `window._SSR_DATA` → `data.loadersData["@neighborDetail_<id>"].data`
  的 `neighborhood_info`（名称/地址/GCJ02）与 `rentInNeighbor`（`total` 与 `items[].id`=房源种子）。
- `rental_reference.xingfuli_sources.evaluate(community, candidate) -> {evidence, gaps, conflicts, strong}`；
  `bind_source(registry, community, candidate, *, seed, method, evidence, allow_reprocessed=False)`；
  `auto_discover(registry, client, communities, *, budget, cancel)`，返回
  `{checked, matched, pending, missing, failed, deferred}`（按小区计，不按尝试计）。
- `rental_reference.probe.ProbeService.start/status/select/retry/cancel`；状态存 `community_registry.meta` 的 `rental_probe:{cid}`，
  含 `schema_version` 与单调递增的 `revision`；自动发现的轮转游标存 `rental_xingfuli_auto_cursor`。

## 3. Contracts

### 搜索通道的身份语义不同（最容易搞错的一点）
`GET https://m.xflapp.com/f100/api/search`，`city_id=1853`，channel 来自前端公开脚本：

| house_type | channel_id | 语义 | 条目里的 neighborhood_id |
|---|---|---|---|
| 1 | 94349530162 | 新房 | 楼盘，不是住宅小区 |
| 2 | 94349530167 | 二手房 | **小区级（整小区）** |
| 3 | 94349530177 | 租房 | 可能按分区拆分；条目自带 `id`=房源种子 |
| 4 | 94349530172 | 小区 | 可能只给分区身份；自带地址与坐标 |

- **二手房通道给的是整小区身份，租房通道可能给分区身份**。找整小区必须用二手房通道优先。
- 搜索条目本身没有地址坐标（二手房通道），身份必须读主页核验。

### 身份规则
- 自动绑定要求：**精确名称** + （地址一致或已知 GCJ02 点 100 米内）+ 无分期标记 + 无区域冲突。相似度只用于排序。
- 平台名称带括号分期标记（`白金海岸(南区)`）时与目录小区**冲突**，人工也不能强绑。
- 平台地址出现其他行政区（如萧山区）与目录区域冲突，同样不能强绑。
- **不存在名称也会成功**：HTTP 200 + status=0 + items 非空 + 查询词回显，四者都不能证明命中
  （实测二手房通道对不存在名称返回 total=9514）。

### 入口与绑定
- 主页 `rentInNeighbor.items[].id` 是房源**种子**；种子不是小区 ID。
- 绑定前必须核验：种子详情页的 `neighborhood_id` 等于目标小区，且同小区列表归属一致。
  **自动绑定同样必须核验**：搜索条目给出的种子只是线索，未经核验的种子会把别的小区的租金挂到本小区。
- 主页无 `rentInNeighbor` 或 `total=0` 属「主页无有效入口」，**不是**「无房源」，不创建绑定，保留已选主页供重试。
- 主页选择与租金绑定是两个状态：`selected_page` 存在 `rental_probe:{cid}`，只有核验通过才写 `sources`。
- 来源身份 = `source='xingfuli', kind='community', sid=<真实 neighborhood_id>`，种子另存 `seed_listing_id`。
- 平台地址存 `platform_address`，**不占用来源记录的 `address`**：平台写法与目录写法不同，
  放进 `address` 既会触发注册表“同名异址”的自动否决，又可能变成小区自身的地址证据（租金资料不得改变用途与地址）。
- `registry.auto_associate` 的通用相似度分支会把分区变体绑上去，幸福里来源必须带 `auto_association_disabled` 并走本契约的证据判断。
- 人工决定在写入前重查（见 `xingfuli_sources._human_veto`）：拒绝对、准入锁、审核锁、来源已有其他有效关联。
  注册表的“同名异址”自动否决对幸福里不适用（地址不在 `address` 字段），由本契约的地址或位置证据判断。
- 自动发现**不**碰人工处理过的小区（`rejected` 或已有有效来源）；人工点“探查”是显式重新处理，
  可以重新关联被解除的来源，但被拒绝的那一对仍然拒绝。

### 请求面
- 白名单：`m.xflapp.com` 的 `/f100/api/search`（参数限 `city_id/house_type/channel_id/full_text/count/offset/page_type`）、
  `/xiaoqu/hz-数字.html`、`/zufang/hz-数字.html`、`/zufang/neighbor-house-list/hz-数字.html`。
- **不要引入 m.99hdf.com**：总小区页在 xflapp 上直接可读。
- 搜索与探查共用同一限速/冷却槽（`RentalPublishLock(rentals/xingfuli_request)`），至少 5 秒间隔，一小时冷却。
- 预算按真实 HTTP 计：自动发现每轮 5 次，手动单小区探查最多 12 次；超限记 `deferred`，不记失败。
- 自动发现的预算只够看几个小区，因此按 `rental_xingfuli_auto_cursor` 轮转：没有游标就会每轮重复查同一个小区，
  其余小区永远轮不到。预算耗尽的小区保留位置，下一轮优先。

### 产品面
- 流程只有“点探查 → 选主页”，**不接受用户粘贴链接**，UI 不出现“去外部找链接”的引导。
- 自动发现在 `RentalRefreshService(auto_discover=True)` 时才启用（生产已开启，默认关闭以便离线运行与回退）。
- 待处理清单包含**没有租金来源的小区**（`reason='missing'`），否则管理页无法触达探查。

## 4. Validation / Error Matrix
| 条件 | 结果 |
|---|---|
| 小区已有租金来源 | 拒绝探查/自动发现（ProbeInvalid 422） |
| 候选 revision 过期 | 409，提示刷新重选 |
| 候选带分期或区域冲突 | 422，不可绑定 |
| 未找到任何主页 | `homepage_not_found` + 重试 |
| 主页无租房入口 | `entry_not_found` + 保留已选主页 |
| 上游要求验证/冷却 | `cooling_down` / `upstream_failed` + 重试 |
| 预算耗尽 | `deferred` + 重试 |
| 探查中重复点击 | 返回同一个活动任务；`select`/`retry` 在有任务运行时 409 |
| 取消 | 停止网络，保留已选主页与旧绑定；取消后不再落库绑定 |

## 5. Good / Base / Bad
Good：目录“万科璞悦湾”自动命中平台同名小区，地址一致 → 自动绑定，下一轮采集。
Base：目录“白金海岸花园”对应平台“白金海岸”，名称不完全一致但位置相差约 12 米 → 不自动绑定，
人工选主页后系统核验入口并绑定。
Bad：把搜索返回的推荐房源当成命中；把白金海岸(南区)绑到白金海岸；把 URL 里的种子当小区 ID；
为省一次请求跳过入口归属核验。

## 6. Tests Required
`test_xingfuli_discovery.py`：URL 白名单、主页解析、通道形状、分期标记与行政区读取。
`test_rental_probe.py`：单候选自动绑定、多候选待选、分期/区域冲突拒绝、无主页与无入口区分、
归属不符不建绑定、过期 revision、运行中拒绝第二个任务、冷却状态、解绑后可重新探查、API 状态码。
`test_rental_xingfuli_sources.py`：强证据自动绑、位置证据（平台地址写法不同）仍可绑、
种子归属不符不绑、负例不绑、预算与轮转、刷新流程接线。
沿用 `test_xingfuli_rentals.py`、`test_rental_providers.py`、`test_rental_association_flow.py`、
`test_rental_refresh.py`；前端 `rental-probe.test.cjs` 与既有 rental 套件。

## 7. Wrong vs Correct
Wrong：`if search_response['status'] == 0: bind(search_response['items'][0])`。
Correct：搜索只用来点名要读哪个主页，身份、地址、坐标、入口全部来自主页与房源页。
Wrong：`source_id = url.split('hz-')[1]`。Correct：`source_id` 是 neighborhood_id，种子单独存 `seed_listing_id`。
Wrong：搜索条目带一个种子就直接绑定。Correct：种子必须经详情页与同小区列表核验后才可绑定。
Wrong：把平台地址写进来源的 `address`。Correct：写 `platform_address`，租金资料不得变成小区地址证据。
