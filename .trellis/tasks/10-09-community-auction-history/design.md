# 技术设计

## 方案选择
采用小区详情页签：延续现有地图入口，用户无需重新找小区。独立全区法拍页增加导航与筛选范围；把法拍作为地图主价格容易混淆口径，留作后续选择。

## 服务边界
新增历史查询服务，负责匹配、去重、筛选、统计；继续复用auction_store与社区加载，不改采集更新身份。普通价格快照和评分保持独立。
人工配置建议data/auction_community_mappings.json，包含version、source、asset_id或auction_id、community_id、note。优先人工映射，再唯一名称/别名匹配；旧community_id也需核验。配置缺失为空配置，错误配置503，禁止静默误关联。

## API契约
GET /api/auctions/community-summary：批量返回各小区全部历史去重有效成交数、available、last_run。
GET /api/communities/{community_id}/auction-history：参数period=12m|24m|all，area_band=all|lt90|90to144|gte144，page、page_size。返回as_of、统计、分页记录、各房源轮次、来源和采集信息。未知小区404，非法参数422，存储/配置错误503。
统计字段deal_property_count、unit_price_sample_count、median_unit_price_yuan、min_unit_price_yuan、max_unit_price_yuan、latest_end_at、sample_warning；缺失null，计数0。
先选最近有效成交再筛选，日期相同时以auction_id稳定排序；各房源轮次保留其他状态供展开。available=false仅表示没有采集存储；已采集无记录仍true。complete不代表区域全量。
外部/api/map继续走既有nginx代理；不改变现有/api/auctions契约。

## 界面与请求
从page.tsx提取小区详情及CommunityAuctionHistory组件。保留概况页签，法拍页签依次为时间/面积筛选、统计卡、口径说明、分页记录及展开事实。
打开页签才加载详情；筛选重置页码，取消旧请求或使用请求版本防止响应覆盖。地图汇总失败不影响地图。移动端单列，键盘可操作页签和展开。
风险仅文本节点；外链限制http/https，另开页加noopener noreferrer。紧凑展示万元/万每㎡，展开可见准确元值。

## 验证与回滚
真实成交454711此前未匹配小区，需核验名录或选其他真实可匹配样本；禁止为了演示挂到错误小区。当前运行文件仅3条在拍记录，不能当作历史成交验收。
核验asset_id跨轮次稳定性。end_at仅拍卖结束，done不是付款/过户证明。
回滚移除新增入口和路由，不删除原始拍卖存储，无需迁移普通价格数据。
