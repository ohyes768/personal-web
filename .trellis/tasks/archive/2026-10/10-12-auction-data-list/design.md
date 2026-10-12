# 技术设计

## 数据流与接口
独立auction_records.json → 查询服务 → GET /api/auctions → /api/map/auctions → 法拍列表 → 地图小区定位。
保留page/page_size/status/community_id及现有响应字段；新增q（去首尾空格，上限200字）、association=all/matched/unmatched，默认all。新增overall_total为未筛选累计记录数，total为筛选后条数。非法参数422，存储/映射异常503。
记录保留来源community_name，community_id按当前映射计算，补community_display_name、association_status。小区筛选使用当前关联。
搜索标题、地址、来源小区名和关联展示名；先过滤再分页。有效结束时间按上海时区降序，无效/缺失排末尾，source+auction_id保证稳定顺序。

## 共享关联与兼容
复用历史查询唯一名称/别名与人工asset/auction映射优先级。associate_records目前丢弃未关联记录，实施时提取共享单条解析或增加保留未关联模式；历史查询继续只消费成功关联记录。
不回写原始存储，无数据迁移；无效映射报错，不回退到旧ID。成交价格遵循done及正值规则；未知状态、缺面积记录保留。

## 前端设计
新增AuctionDataList及独立原始轮次类型，不混用带rounds的历史成交类型。筛选独立于普通房价筛选；AbortController及请求key阻止旧响应覆盖，错误可重试。
父页面新增auction页签及刷新版本，成功采集重拉列表和汇总；切回列表读取最新数据。失败/取消保留累计数据。
按小区ID从完整名录定位，解除遮蔽目标的地图条件，复用看板现有切地图/选中/聚焦逻辑。无法解析名录时提供提示。
桌面列表、移动适配卡片；复用已有金额/日期/安全外链实现，纯文本展示物业事实。

## 风险与回退
page.tsx、globals.css、CommunityDetailTabs.tsx已有租金任务并行改动，实施前读最新差异并增量修改。回归旧列表参数、历史聚合及详情一致性。
回退新导航/组件及接口扩展即可，无需回滚数据。沿用独立刷新job，不接定时任务。
