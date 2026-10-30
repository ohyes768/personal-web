# 幸福里来源发现与按需探查契约

> 2026-10-29 建立。系统的“找来源”能力：平台内多通道搜索 → 小区资料API验证身份 → 选定后按需获取租房入口API → 双归属核验后绑定。
> 关键结论：**搜索响应永远不是身份证据**，身份来自小区资料API（旧版本为主页HTML）；**平台内可执行，不需要外部搜索引擎**。

## 关联入口列表API提速（2026-10-30，替代下文双HTML核验默认路径）

- 默认 ProbeService 在刷新小区资料和租房入口后，调用 `DiscoveryCheckpoint.verified_rental_seed(seed,nid)`，由 `XingfuliDiscovery` 单次请求 `/f100/api/search_api/rent` 的固定同小区第一页。与租金采集共用 `rental_list_api_url`；发现白名单仅允许固定参数和offset=0，无额外、重复或分页参数。
- 此API必须status=0、有效data、items列表及布尔has_more；非空列表每行必须有数字字符串id和与目标nid严格一致的neighborhood_id。空、缺身份、混归属、坏结构不关联。旧入口种子可能不在第一页：绑定种子必须从本次已核验列表选择，不直接绑定入口种子。nid仍是来源ID，seed单独保存。
- 核验不读写成功步骤缓存，每次真实HTTP继续检查预算、取消、共享3秒间隔与冷却；验证码/限流冷却直接结束，不能误报“无入口”或继续下一种子。新鲜资料/当前目录用途、分期、区域和人工决定复查及发布锁不变。
- 人工选择默认3请求（资料+入口+列表核验），唯一强候选冷启动4请求（另加搜索），比上一版各少1请求。兼容注入的旧客户端没有新方法时，Checkpoint沿用旧详情+列表双核验及独立预算；默认网页客户端不走HTML。独立旧auto_discover兼容实现仍保留原接口。
- 前端在运行态展示current_step（资料核对/入口读取/列表归属），终态优先stage；新select/retry清空旧步骤及诊断。GET状态不启动请求。
- 实测上线前基线为4请求/约12秒，8.9秒为限速等待；新链路的3请求由真实适配器测试验证，预计省3～4秒，实际时延须部署后测量，不能把测试次数当线上性能结论。
- `test_xingfuli_source_api.py`覆盖3/4请求、实时列表种子替换、空/混归属/缺归属/坏ID、预算、取消、冷却、未缓存核验与URL白名单；旧probe/matching及租金采集回归保留。

## 完整名称唯一候选自动绑定（2026-10-30，替代下文网页入口的强位置证据门槛）

- ProbeService 的自动决策允许：资料API中的完整名称与目录主名/别名一致、已查询通道搜索完整且仅一个相关候选、无区域/分期冲突。地址写法不同且坐标缺失或坐标系无法比较时，不再仅因“缺少一致地址或位置证据”要求人工选择。
- `evaluate(community,candidate,allow_name_only=True)`仅由ProbeService启用；默认False，独立旧auto_discover仍要求地址或位置一致，不能把它缺少候选完整性保护的路径一起放宽。候选strong表示本策略下可自动确认身份，真实地址/位置evidence仍只按实际比较结果生成。
- 可比较GCJ02坐标超过100米且地址不一致时，不自动绑定；地址文字不同本身不是明确冲突。相似名称、多候选、搜索/资料失败或截断仍待选。唯一性限定于完整查询过的通道，不表示全平台唯一。
- 缓存恢复后的资料刷新、落库前当前目录身份复核均采用同一策略；入口和实时列表归属核验、预算、取消、冷却、发布锁、人工保护继续生效。已有待选结果需重新探查或全量匹配；GET不触发自动绑定。
- 回归：`test_rental_probe.py`覆盖缺坐标/坐标系不可比、显式及批次自动搜索、多候选/截断/远距离/相似名、恢复刷新；`test_xingfuli_source_api.py`覆盖四API请求真实适配器及核验期间目录改名后禁止落库。

## 当前网页入口（2026-10-29）

- `GET/POST/DELETE /rentals/source-matching` 独立查询、启动/继续、取消来源匹配；POST为202，接受`mode=full|incremental`（详见下方提速契约）。SourceMatchingService顺序执行幸福里probe，保存remaining/outcomes和计数到rentals/source_matching_job.json；绝不采集整租样本或发布租金快照。人工跳过、拒绝、已有幸福里来源不自动重做。
- 网页`/rentals/refresh`明确启用`RentalRefreshService(xingfuli_only=True)`，只采已关联幸福里的合资格小区，不运行任何来源发现；零关联返回422并提示先匹配。历史默认构造器保留独立旧库测试/工具兼容，不能作为网页运行配置。
- 匹配、租金采集、单小区probe共用task_lock与busy检查，不能并发网络执行。取消保留未处理队列；未取消的在途任务可在服务启动时恢复；GET不启动网络。成功搜索与主页步骤持久化，中断的小区复用有效步骤，绑定前仍重新核验入口。
- 旧Fang搜索、链接导入、候选确认及review bind写入口返回410；来源待处理清单按幸福里probe状态投影。人工选择主页仍走probe/select，不复用旧Fang候选确认。
- 来源绑定在发布锁下复查资格、取消和人工跳过；自动匹配不绕过人工拒绝，显式单小区探查保留重新处理语义。

## 1. Scope / Trigger
修改 `xingfuli_transport.py`、`xingfuli_discovery.py`、`rental_reference/xingfuli_sources.py`、
`rental_reference/probe.py`、`rental_source_routes.py` 的探查路由，或 `refresh.py` 的幸福里自动发现前必读。

## 2. Signatures
- `XingfuliTransport(timeout, *, directory, fetcher, delay, cancel_event, validate)`：共享的限速/冷却/取消/大小限制/验证页检测；
  `xingfuli_rentals.XingfuliClient` 与 `xingfuli_discovery.XingfuliDiscovery` 都继承它，两者共用 `rentals/xingfuli_request` 锁与
  `xingfuli_request_state.json` 冷却状态。
- `XingfuliDiscovery.search(name, channel) -> {neighborhood_id: {name, seeds}}`；`community_info(nid) -> dict`；`rental_entry(nid) -> dict`；
  `listing_owner(seed) -> str|None`；`listing_owner_from_list(seed, nid) -> bool`。
- `parse_homepage(html, expected_id)` 仅保留作历史解析/对照测试，不进入当前匹配默认路径：小区主页 `window._SSR_DATA` → `data.loadersData["@neighborDetail_<id>"].data`
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
- 搜索条目本身没有地址坐标（二手房通道），身份必须用小区资料API核验。

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
- 自动发现**不**碰人工处理过租金来源的小区（`rejected` 关联的来源为 `fang`/`xingfuli`，或已有有效来源）；高德、透明售房网、法拍来源的解绑/拒绝不属于租金决定，不得排除租金匹配或阻止绑定。统一使用 `providers.rejected_rental_communities(db)`，通过 `rejected.rid = sources.id` 判断来源类型，不能仅按 `rejected.cid` 全局屏蔽小区。人工点“探查”是显式重新处理，
  可以重新关联被解除的来源，但被拒绝的那一对仍然拒绝。

### 请求面
- 白名单：`m.xflapp.com` 的 `/f100/api/search`（参数限 `city_id/house_type/channel_id/full_text/count/offset/page_type`）、
  `/f100/api/neighborhood/info`（仅neighborhood_id）、`/f100/api/same_neighborhood_rent`（neighborhood_id/city_id=1853/offset=0/count=10）、`/zufang/hz-数字.html`、`/zufang/neighbor-house-list/hz-数字.html`。旧`/xiaoqu/hz-数字.html`只保留只读对照入口。
- **不要引入 m.99hdf.com**：总小区页在 xflapp 上直接可读。
- 搜索与探查共用同一限速/冷却槽（`RentalPublishLock(rentals/xingfuli_request)`），至少 3 秒间隔，一小时冷却。
- 预算按真实 HTTP 计：自动发现每轮 5 次，手动单小区探查最多 12 次；超限记 `deferred`，不记失败。
- 自动发现的预算只够看几个小区，因此按 `rental_xingfuli_auto_cursor` 轮转：没有游标就会每轮重复查同一个小区，
  其余小区永远轮不到。预算耗尽的小区保留位置，下一轮优先。

### 产品面
- 流程只有“点探查 → 选主页”，**不接受用户粘贴链接**，UI 不出现“去外部找链接”的引导。
- 自动发现在 `RentalRefreshService(auto_discover=True)` 时才启用（生产已开启，默认关闭以便离线运行与回退）。
- 待处理清单包含**没有租金来源的小区**（`reason='missing'`），否则管理页无法触达探查。
- 网页“采集任务”弹窗里“匹配租金来源”与“更新租金数据”是同一条租金流程的两步，收进**同一个区块**
  （`.directory-task-group`，标题“租金流程”）而不是平铺成两个互不相干的任务行；两个动作互斥，一个运行时另一个按钮禁用。

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

## 来源匹配提速契约（2026-10-29）

### Scope / Trigger
修改`matching.py`、`probe.py`、`discovery_checkpoint.py`、发现客户端或来源匹配按钮时适用。保留共享3秒限速、冷却、任务锁与发布锁。

### Signatures
- `SourceMatchingService.start(mode=None, *, _startup=False)`；POST请求`{"mode":"full"}`或`{"mode":"incremental"}`，非法模式422，互斥409。省略请求体/模式兼容原先自动续跑行为。
- GET增加`incremental_count`、`mode`、`current_community_name`、`current_step`及`diagnostics`；GET仅查本地状态，不启动网络。
- `DiscoveryCheckpoint`以`community_registry.meta`的`rental_discovery_steps:{cid}`保存版本、身份指纹及结构化成功步骤；不保存HTML、Cookie或核验授权，不建立第二个关联库。

### Contracts
- full清除本轮目标的派生断点，重查所有合资格且缺来源小区，包括待选择/未找到/失败；incremental处理remaining、新增未查和失败，跳过已完成待选/未找到。history保留以往完成结果，避免一次空增量丢掉历史。
- 人工跳过/拒绝及现有来源始终保护。恢复在途服务只恢复保存的remaining，不追加新小区；用户点继续才追加新增/失败项。
- 名称按normalized去重，主名加最多一个别名；完整检查当前通道所有相关候选后，只有一个候选且strong才提前结束。主页读取失败、竞争候选、预算/候选上限截断、搜索满20条或total超过返回数，均不得自动绑定。
- 只能证明已查询通道内唯一，不能证明全平台唯一。`HOUSING_XINGFULI_EARLY_STOP=0`关闭提前结束；仍保留不完整证据不可自动绑定的安全修复。
- 每个成功搜索/主页步骤先落SQLite，再进入下一步。有效空搜索也保存24小时；失败/验证页/冷却不保存。身份指纹包括名称/别名/地址/区域/坐标；身份、版本变化或步骤过期/损坏后重查。缓存按小区隔离，身份判定每次重算。
- `HOUSING_XINGFULI_DISCOVERY_CACHE=0`关闭缓存读写。缓存不计HTTP预算；每个真实请求（包括列表核验）之前检查取消与预算；真实传输继续检查冷却/限速。
- 恢复/选择时刷新主页租房入口，然后重新执行详情和列表两次归属核验。新鲜主页与绑定时的当前目录信息重新评估：搜索自动决策须strong；人工选择允许证据缺口但不得有冲突。不要用`automatic=False`推断“用户已经选过”：显式单小区搜索也属于自动决策。
- `diagnostics`统计本次启动的requests、cache_hits、wait_seconds、http_seconds、elapsed_seconds；probe另记early_stop。每个HTTP步骤更新，批次汇总当前及已完成小区。新点击启动时请求诊断重置，恢复保留业务结果计数。

### Validation & Error Matrix
|情况|行为|
|---|---|
|未知mode|422，不启动任务|
|增量0项|按钮禁用；API允许空任务，不发HTTP|
|成功空搜索|缓存24小时；继续不反复查已完成未找到项|
|主页/搜索读取失败或截断|不自动绑；有候选留待选，无候选记失败，可增量重试|
|预算耗尽|deferred，不越预算核验列表|
|取消/进程退出|保留已成功步骤；恢复重做未成功步骤及入口核验|
|坏缓存/过期/身份变化|重查，不伪造成功空结果|
|权威数据库读取失败|失败关闭，不继续绑定|

### Good / Base / Bad
Good：首通道完整、唯一强候选，1搜索+1主页+2核验，共4请求。Base：证据不足继续通道/别名或人工选择。Bad：第一个strong出现就绑定、忽略读取失败的竞争候选、复用旧详情归属直接绑定。

### Tests Required
`test_matching_speed.py`覆盖6→4请求、唯一/竞争/截断、缓存有效空/过期/损坏/输入变化、失败不缓存、强制进程退出、恢复刷新入口/双核验、预算、模式及API、启动恢复不扩队、累计请求与功能关闭；原probe/split/discovery/source套件继续执行。前端directory-flow验证两个mode的点击、空增量/运行/租金更新互斥，position-status断言限定高德任务行，不能误判租金说明。

拒绝来源隔离回归：`test_matching_speed.py` 验证高德解绑后 full/incremental 均重新入队且成功绑定，原高德拒绝记录仍保留；Fang/Xingfuli 解绑后仍不入队且绑定被拒绝。`test_rental_xingfuli_sources.py` 验证自动发现也能为有高德解绑历史的小区绑定来源。

### Wrong vs Correct
```python
# Wrong: cached strong identity means entry is safe to bind.
bind_source(registry, old_community, cached_candidate, seed=old_seed)
# Correct: refresh homepage entry, re-evaluate current identity, then check both owners.
info = client.community_info(candidate['neighborhood_id'], fresh=True)
entry = client.rental_entry(candidate['neighborhood_id'])
# Recompute evaluate(...), verify detail + same-neighborhood list, then recheck under publish lock.
```


## 来源匹配资料 API 与按需入口（2026-10-29，替代上述主页读取实现）

- `XingfuliDiscovery.community_info(nid)`：单次GET `/f100/api/neighborhood/info?neighborhood_id=...`，验证status=0、目标ID和杭州city_id=1853、名称/地址字段、有限GCJ02坐标。`district_name`作为额外区域证据，和地址中的区域分别检查，任一冲突均禁止自动/人工绑定。
- `XingfuliDiscovery.rental_entry(nid)`：单次GET `/f100/api/same_neighborhood_rent?neighborhood_id=...&city_id=1853&offset=0&count=10`，验证items/total/has_more。只提取去重的数字种子；条目无neighborhood_id不等于归属已证明，若字段存在且冲突则拒绝。
- 搜索候选只查资料，`rent_total=null,seeds=[]`表示入口尚未查询，不是零房源。有竞争、不完整或冲突时不预取入口。唯一完整强候选或人工选择后才获取入口；真实成功空入口记entry_not_found并保留选择，失败记upstream_failed，验证/限流持久化冷却并映射cooling_down。
- 绑定前保留详情与同小区列表双核验。搜索条目种子不能替代新鲜入口。来源绑定/拒绝、候选revision、前端业务stage、full/incremental和互斥语义不变，资料和入口进度分别沿用homepage/resolving_entry显示。
- `DiscoveryCheckpoint.VERSION=2`，缓存键按search/community_info/rental_entry分开；旧版homepage缓存失效，不重写来源或人工决定。成功步骤逐个持久化，失败不缓存。选择/恢复必须fresh=True刷新资料，按当前身份重新evaluate；入口每次解析绑定都刷新，历史入口不是绑定授权。每个API请求单独检查预算/取消并计诊断，不允许组合两请求只检查一次。
- 当前3秒共享间隔来自列表抽样任务；本任务不再修改限速、冷却或浏览器容器。租金采集仍按独立列表API抽样契约。
- 性能边界：唯一强候选冷启动由原4次变成5次（搜索+资料+入口+详情核验+列表核验）；多候选待选不取入口。不得把接口响应更轻等同于总耗时必然更快。真实小批对照记录API/HTML请求数、等待和HTTP耗时，不能以测试绑定成功声称全量性能达标。
- 必要回归：`test_xingfuli_source_api.py`覆盖真实适配器五请求/无主页HTML、待选不取入口/选择后只取目标、逐请求预算2/3/4边界、空入口与API失败区分、跨小区种子拒绑、新鲜区域冲突、旧缓存迁移/损坏/过期、取消/验证冷却和严格URL参数；既有probe/matching/split/source回归继续执行。
