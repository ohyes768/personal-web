# 幸福里租金试点设计

采用独立 XingfuliClient + 共享发布链路。直接替换 FangClient 会破坏原解析器；独立脚本不接查询则无法供页面使用，均不采用。

## 来源和数据流
Registry.sources → rental_reference.providers 选择每小区一个来源（已确认幸福里优先，其次房天下）→ 现有 RentalRefreshService 分派 → CommunityBatch → publish_run → 现有查询/覆盖率/前端。真实小区 ID 不带人为前缀，所有匹配同时比较 source，旧未标 source 数据兼容视为 fang。

XingfuliClient 只允许 m.xflapp.com 的 Hangzhou 列表、详情及已验证 GET 分页路径；首屏 JSON query.id 必须等于 seed_listing_id，query.city 必须 hz。每条 neighborhood_id 必须等于绑定 ID；分页必须有可推进的 offset/search_id，has_more=false 才 complete。单次请求有超时与可取消间隔，不自动重试验证页。

详情基于 data.info.card_info，验证 query.id、小区真实 ID，读取价格、面积、户型/楼层；整租样本必须完成实际详情读取，合租保留排除标记。property_type 来自已收录目录用途，记录 property_type_origin，不能宣称来源页提供用途。时间是采集时间，发布时间未知保持空。

保持旧 Fang 路径以免破坏现有客户端注入和测试。刷新先执行幸福里计划，再执行原 Fang crawl_runs，共同生成批次。缓存命中、最终目录资格与关联复核由共享 selector 决定。所有失败不切指针；混合发布只沿用同来源旧条目。房天下 cooldown 不阻止独立幸福里请求。

## 启用和回退
试点 CLI 默认预览，显式 apply 才写权威 Registry。入口以真实 neighborhood_id 存 identity、seed_listing_id 存采集入口，仅匹配当前已收录且名称/地址或位置证据充分的住宅。拒绝、ignored、已绑定其他小区等状态不覆盖。记录一次导入标识，已解除的历史来源不重绑。

保持原 Fang 关联供回退；解除幸福里关联后下次刷新选择 Fang，旧幸福里快照立刻从查询中失效。部署/生产 apply 单独执行，当前仅本地实现与隔离数据验证。

## 测试边界
测试使用最小脱敏 JSON fixture，无公网自动请求。覆盖 URL、类型/单位、ID、大整数字符串、分页完整性、错误响应、取消、详情核验、provider优先级/隔离、导入幂等/拒绝、API安全链接、统计与覆盖率。两来源当日完整分页实测记录见 research-validation.md，不将动态数量写成网络测试断言。
