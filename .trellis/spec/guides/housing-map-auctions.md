# Housing-Map 法拍采集合同

> 2026-10-14：未关联法拍小区进入 [统一小区审核](../backend/housing-map/backend/community-review.md)。旧入口跳到管理页来拍筛选；原始轮次记录仍独立保存。

适用：法拍脚本、查询API、手动采集job，未来新增定时任务也须复用collect_auctions。

- 来源是来拍公开辅助数据，source=laipai，auction_platform单独保存。不得标为阿里直接采集。
- upstream BASE=https://api.faeping.com/api/webV1，client: PC；searchObject列表count有整数/数字字符串两种返回形态。
- 先筛杭州住宅，再按area_code=330108取详情，详情核验ID/地区/用途。法院所在地不是标的所在地。
- 状态todo/doing/done/pause/failure/break/revocation/debt，未知保留source_status并显示unknown。只有done+正deal_price才保存成交价。
- auction_id为拍卖轮次身份，asset_id为object_id；以source+auction_id更新，不能按小区或房产ID覆盖不同轮次。
- 上游评估价字段appraise_price；金额整数元。面积优先结构字段，再调查表/公告明确建筑面积；缺失null。end_at表示拍卖结束，不承诺法院确认或付清尾款。
- 独立data/auction_records.json，版本1。失败/取消不写盘，限量增量合并保留旧数据并complete=false；不影响price_snapshots.jsonl及评分。
- OS侧车文件锁覆盖整次事务、跨CLI/API互斥；不能删除运行中锁文件。线程取消后等待线程真正退出才释放锁。服务关闭须await shutdown_refresh。
- HTTP POST/GET/DELETE /api/auctions/refresh，启动202、冲突409；GET /api/auctions分页查询。nginx外部前缀/api/map。不接受任意上游URL或输出路径。
- 不保存完整含姓名/电话/账号的公告，只保留物业事实白名单；后续前端按纯文本显示。风险缺失不代表无风险。
- 测试：tests/test_auctions.py，Windows pytest --basetemp=.pytest-tmp-auction。无浏览器依赖，复用curl_cffi；定时采集未接入scheduler。

说明：backend/housing-map/docs/auctions.md。实测2026-10-09：CLI和API均限量采集3条；454711成交价4760000、面积149.3。分页列表会变化，complete只代表当前遍历完成，不保证区域全量覆盖。

## 小区历史成交查询（2026-10-12）

- auction_history.py 查询时重算关联：与采集共用community_name_index，唯一精确名称/别名才自动匹配；显式映射按source+asset_id优先，其次source+auction_id。不信任旧community_id替代名称证据。
- auction_community_mappings.json受版本管理（version=1、mappings数组），每条只允许一个身份字段；非法小区ID/重复键报503，缺文件视为空配置。修改后历史记录即时生效。
- 先全局按source+asset_id取最近有效done成交，再筛选community_id和日期/面积，防止小区归属变化造成汇总和详情不一致。缺asset_id按auction_id退化，并标识无法跨轮次去重；不按地址合并。
- period=12m/24m/all，默认12m；上海时区，向前日历月截断月底，排除无效/未来日期。面积档lt90/90to144/gte144分别<90、[90,144)、>=144；all保留缺面积房源。
- 单价由正成交总价/正有限建筑面积重算，中位数用未取整数值，偶数取中间均值，展示ROUND_HALF_UP。缺面积不计单价样本，但计成交房源；统计不受分页影响。
- GET /api/auctions/community-summary批量counts；GET /api/communities/{id}/auction-history返回stats/records/total/page/as_of/available/last_run。404未知小区、422参数、503坏数据。前端路径仍/api/map。
- 页面独立详情页签，打开才请求，AbortController及请求key阻止旧响应覆盖；切小区以community_id重挂载。地图一次批量请求，失败不影响普通地图；风险按文本、外链仅http(s)。
- 检查：tests/test_auction_history.py；前端node --test tests/auction-history.test.cjs、pnpm lint/build。真实样本454711→10001742：476万元/149.3㎡=31882元/㎡，样本1、非全量。

## 法拍数据列表（2026-10-12）

### Scope / Trigger
修改独立法拍列表、筛选、计数或地图联动时适用。

### Signatures
GET /api/auctions?page=1&page_size=20&status=todo&community_id=ID&q=关键词&association=all；前端/api/map/auctions。

### Contracts
association为all/matched/unmatched，q最多200字、去首尾空格后不区分大小写匹配标题/地址/来源及关联小区名。响应新增overall_total（累计轮次条数）、记录community_display_name/association_status；total为筛选后条数。查询时按历史规则重算community_id，keep_unmatched=True保留未关联记录；不修改存储。有效结束时间降序，无效排末尾，source+auction_id稳定排序；先过滤后分页。
列表成交价仅done+正值显示，缺值不转0。成功采集驱动列表/汇总刷新，失败取消不清空。列表小区定位使用完整名录并清除遮蔽目标的地图条件。

### Validation & Error Matrix
非法association、q超过200字或非法页码→422；存储或映射坏数据→503；未采集→available=false；筛选空→total=0但overall_total保留。

### Good / Base / Bad Cases
Good：人工映射修改即时体现在列表和历史；Base：未关联照常展示，无地图按钮；Bad：坏映射报503，禁止回退旧community_id。

### Tests Required
test_auction_list.py断言未关联保留、映射即时生效、组合过滤分页及累计计数/参数错误；auction-list.test.cjs断言非成交隐藏成交价、缺面积、纯文本、安全外链和空状态。回归历史聚合测试及地图定位。

### Wrong vs Correct
Wrong：把matched称为去重房产套数，或用历史成交过滤器生成全局列表。
Correct：本次命中N条、累计N条拍卖记录；列表保留轮次和非成交记录，地图按既有有效成交房产规则去重。

## 最近法拍成交概况卡片（2026-10-12）
- 小区概况新增第五张stat-cell，最近指已采集、有效成交中最新一套，不是最低价或中位数。复用历史接口period=all&area_band=all&page=1&page_size=1，不新增API/存储字段。
- 主值成交单价（万元/㎡，两位小数），辅值结束日期与建筑面积；最新记录缺面积时显示单价空值及面积未知，禁止退回更早有面积的成交。无记录、未采集、加载/错误分别显示，切小区及成功采集刷新遵循请求key/取消规则。
- 本轮仅展示卡片，不添加法拍卡片或签约均价跳转。桌面五列、480px以下三列，卡片价格单位需完整可读。
- tests/auction-card.test.cjs断言最近值不取中位数、缺面积/空状态、无导航链接；复验倾城之恋31882元/㎡、2026-09-29、149.3㎡。pnpm lint/tsc/build。

## 法拍手工待关联（2026-10-14）

### Scope / Trigger
适用于auction_association.py、采集发布、统一目录身份升级及AuctionPendingAssociations。

### Signatures
- sync_records(Path) → records/identities/matched/automatic/pending/ignored；调用方持有StoreLock。
- POST /api/auctions/associations/sync → success/data同步报告，无上游请求。
- GET /api/auctions/associations/pending?q&page&page_size → items,total,page,needs_sync；每项record_id/name/address/source_kind/source_id/reason/candidates/rounds。
- CommunityRegistry.promote_auction_source(asset_id,auction_ids)保留单个旧auction来源记录的id、绑定和拒绝关系。

### Contracts
成功写入累计法拍JSON后同步统一目录；source+asset_id归组，无asset_id退化source+auction_id。同名不同房产不合并。已有目录人工绑定/拒绝/解绑/忽略优先，空小区名仅以标题显示且auto_association_disabled阻止自动关联。多个旧轮次身份有独立决定时禁止自动归一，association_identity_conflict持续待人工核对。普通GET不写来源目录。旧数据通过显式sync补入，已同步身份缺新轮次ID时needs_sync=true。
前端法拍“手工待关联”显示按房产归组列表、候选证据、目标搜索和确认绑定；复用/directory/sources/{rid}/associate，允许null成功响应。成功刷新法拍列表、地图汇总和详情，空页回退到有效页。

### Validation & Error Matrix
同步与采集互斥409；非法分页/过长搜索422；数据、SQLite或文件故障503。法拍JSON与SQLite不共享事务：同步失败保留已保存法拍并返回association.error；job.phase仍done、job.error提示关联未完成，支持只重试同步。

### Good / Base / Bad Cases
Good：两轮同asset只显示一处待关联，绑定后两轮均归入目标。Base：缺名/缺证据保留待处理，缺asset仅绑定已知轮次。Bad：数据库故障不能宣称关联成功，反复同步不能复活删除项。

### Tests Required
测试轮次归组、重复同步、人工绑定/拒绝/删除、无名标题禁止自动绑定、身份升级、多旧身份冲突、API绑定即时生效/互斥、同步失败后法拍保留；前端验证null成功与错误消息、桌面/390px历史同步和绑定闭环。

### Wrong vs Correct
Wrong：法拍按名字猜测归属或要求额外重新采名称才能手工绑定。Correct：已保存法拍直接同步目录，充分证据自动关联，其他按持久来源身份人工确认。
