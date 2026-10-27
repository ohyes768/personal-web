# 技术设计（已批准实施）

## 1. 数据流与边界
TMSF名单/详情事实 → 统一收录规则 → 已收录住宅ID集合 → 独立高德定位和租金采集。
来拍区域原始轮次 → 名称/地址身份匹配已收录住宅 → 已关联统计或法拍待关联。
保留 community_registry 为唯一身份/人工决定账本，community_admission 为决定/审计承载；不新增第二套可写映射表。用途、名单资格、位置状态、租金状态、法拍关联是独立字段，不再复用一个pending表达所有问题。

## 2. 名单规则
在community_admission/community_listing复用既有挂牌、新房、地址与人工保护门槛，提取所有读写路径共同使用的TMSF资格计算：eligible、condition_failed、facts_incomplete，投影为已收录或不收录+资料状态。同一小区多来源/分期先验证身份，不能仅同名创建或合并。
收录计算仅采用有效TMSF用途/项目事实，保留旧Fang分类器供历史诊断但不再控制住宅、地图或采集目标。旧AutoReview不能与新规则并行写入，替换其名单职责/入口并禁用冲突自动回调，保留必要历史查询。
收录条件、人工排除优先级、未知挂牌不视0、有效旧事实失败保留、新房挂牌豁免按现有硬约束验证。缺坐标只影响地图位置，不影响住宅资格；高德地址不作为TMSF实际地址证据。

## 3. 四类后台任务
- TMSF复用directory_collection/DirectoryJob，完成每批有效事实后分类；不要再触发可创建多来源住宅的通用自动审核。
- 高德新增已收录住宅批量任务，复用AmapClient.search_name/normalize_poi及坐标投影，不能直接调用包含TMSF刷新的enrich_source实现独立高德动作。请求预算/限速、单小区错误、同名/分期歧义、合法边界/坐标、前后快照校验、原子发布、日志脱敏、进程重启中断及关闭回收均需实现。默认跳过有效/人工坐标；缺失/失败目标独立持久化状态。
- 租金复用RentalRefreshService与association-tasks；收敛目标选择到相同已收录集合，保留编辑/发布互斥及来源唯一性。房天下名称查询存在忽略关键词限制，必须诚实报告，不能把全城结果当匹配或承诺百分百可采。
- 法拍复用auction_refresh及auction_association，独立区域采集不变，仅匹配目标收紧为当前已收录集合；手动绑定不经过住宅admit。原始拍卖身份、资产轮次、人工解绑/拒绝优先。
现有REST接口尽量复用；新增高德任务状态/启动/取消接口及法拍绑定专用接口若既有路径不能复用时才新增。实施前固定命名/响应契约到spec。旧入口作为同一任务调用方，不能创建两套worker或统计。共享资格写入与采集发布有事务/锁保护，运行期名单变化须重新校验，不整段持有网络请求事务。

## 4. 前端
CommunityWorkspace顶部四来源任务卡，显式提示高德/租金“仅已收录住宅”。保留各任务原进度含义，不用区域页数伪装小区完成百分比。列表为已收录、不收录、法拍待关联；不收录显示主因、资料状态和重试入口。法拍行显示房产/轮次/原始地址、建议目标和关联操作；无住宅创建按钮。租金异常面板继续独立放置。清除旧AutoReview启用/预演对日常名单操作的要求。详情仍可看历史初始化与人工操作，不把它们拼进当前原因。

## 5. 线上迁移
1. 离线快照预演：SQLite backup API及相关price/rental/auction文件的一致备份，记录文件校验和、schema/rule版本、事务快照及当前活动任务。
2. 对快照生成计划，不能调用会写业务的prepare_directory/ReviewWorkspace.refresh充当只读预演。列出每个主档旧状态、TMSF事实、拟定新状态、原因码、人工保护、旧混合成员以及地图/租金/法拍影响。
3. migration/旧自动资料以TMSF有效事实重算；不清空admission/events历史。历史固定reason退出业务原因投影；新原因独立存储/计算。旧人工决定有冲突时单列，禁止静默重置。
4. 原通用队列拆成业务视图：TMSF资料问题归不收录资料状态，Fang归租金关联，laipai归法拍待关联；混合记录逐成员处理，不删除整个小区及来源。
5. 确认具体报告后执行；检查活动写任务/快照未变化，备份后写事务和schema标记，保证重复执行不产生新ID、重复事件或恢复删除记录。
6. 校验有效住宅数、资料待补数、人工保护数、法拍已关联/未关联、租金映射、地图资格及价格历史；保存前后报告。备份数据回滚仅在停写/维护窗口操作，避免覆盖执行后的新数据；优先按迁移审计定向回滚。

## 6. 影响文件
后端：community_admission、community_review、community_auto_review、residential_classifier、directory_collection及routes、community_enrichment/amap任务、rental_reference/source/refresh、auction_association及routes。前端：CommunityWorkspace、DirectoryCards、AutoReviewPanel替换入口、RentalAssociationReview、page/header采集状态复用。新增迁移/预演脚本及针对性测试。
不改仓库全局Trellis包注册，不操作其他服务。迁移执行与上线是独立生产动作，本任务规划不含授权。

## 实施落点
使用directory_policy、directory_workflow、directory_position和directory_migration承载新流程；新增workflow路由与DirectoryFlowWorkspace。directory_flow_version迁移标记是上线边界：迁移前新管理页禁用任务，原地图仍沿用旧判断；迁移后所有资格投影切换到TMSF规则，旧审核写接口拒绝绕过。主档原admission只作历史/人工保护，不因重算重写。生产备份与维护窗口要求见backend/housing-map/docs/directory-flow-migration.md。
