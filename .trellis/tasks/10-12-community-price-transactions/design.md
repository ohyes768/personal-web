# 技术设计草案

新增Next.js独立路由 /communities/[communityId]/prices，来源参数source=auction|signed，默认auction；可选record参数突出引用法拍记录。卡片使用Link，来源切换同步URL，支持分享和刷新。页面显示小区名称、价格依据、来源切换及返回地图入口。法拍默认all/all，普通签约用月份列表。

不重组CommunityDetailTabs。复用法拍记录内容组件，避免两个界面形成不同成交口径。返回导航在会话中保存必要地图状态（选中小区、位置、筛选）；无返回上下文时进入地图并定位URL对应小区。只保存地图状态，不在URL或导航状态中传价格，详情以接口重新查询为准。

拟新增GET /api/communities/{id}/signed-history（前端/api/map）。success/data返回community_id、price_source_community_id、reference（单价、月份、采集日期、来源）、records（month/unit_price_yuan）、available。未知小区404、坏存储503、无数据正常响应，available契约实施前明确。

读取既有price_snapshots.jsonl，复用或提取现有价格选择和合并小区来源规则，选择与概况相同有效签约快照，再解析monthly_trend。校验ticks/line长度、月份及有限正价格，重复月份去重并倒序。无趋势返回reference，无签约不借挂牌冒充。仅使用当前快照已采集趋势，不拼接旧快照，不重抓外网。来源链接限安全http(s)。

统一纯格式函数：31882→卡片3.19万元/㎡、详情31,882元/㎡；4760000→476.00万元。只改显示，不改计算精度。详情进入及刷新重新查询接口，旧请求不能覆盖新小区。

共享风险文件page.tsx/globals.css/CommunityDetailTabs.tsx含其他任务租金改动，保留并适配。已有卡片“无跳转”测试需更新；法拍去重与最近成交口径不变。不迁移数据，回滚移除独立路由和卡片链接即可。
