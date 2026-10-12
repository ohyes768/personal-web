# Housing-Map 法拍采集合同

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
