# 设计：TMSF基本事实 + 高德主体地址

## 选择与边界

采用用户确认的自动方案。继续叠加浏览器重试不能解决证据依赖，人工补录已被取消。保留现有独立浏览器用于必要的新房主页读取，复用现有目录/地点/分类能力，不引入新服务。

## 1. 统一地址证据

在community_address中提供纯投影admission_address(community, records)，输出value/origin/evidence/valid/reason。按受保护历史人工实际地址、有效同身份来源实际地址、可靠高德主体地址的顺序选择。原始sources.address及预售证URL/证号/时间不改写；高德地址使用origin=amap_subject，附POI ID、当前项目身份指纹、区域、类型、坐标及证据时间。

高德兜底来自当前身份的matched/manual主体，必须通过现有可靠性/区域/类型/坐标校验且地址非空。仅坐标核对不提供地址；名称歧义、附属地点、区域或明确门牌冲突不提供兜底。已有人工位置确认不等于确认住宅用途，显式冲突不能被低优先级地址遮蔽。

eligibility、community_views、目录详情和地图共同使用此投影；租金/法拍只消费统一收录集合。前端标注地址来源，TMSF原始地址仍独立可查。身份或选中主体变化使派生证据失效，人工事实继续受保护。

## 2. 基本采集与可选补证分离

_project_detail显式区分基本模式与补证模式。普通目录更新/失败重试只获取身份、用途、状态及主页有效地址，不追预售证；事实缓存仍复用，缺地址不当网络失败。其他确有必要的补证调用使用显式模式，保持原名称/区域/证号校验。

身份可信且明确非住宅时结束住宅资料补证；统一类型口径精确识别字面非住宅，禁止按包含“住宅”判断。人工用途决定及冲突仍交由现有优先级矩阵。

## 3. 自动衔接与结果

基本资料保存后，为本轮新建/有效事实变化且需地点匹配的候选触发现有地点任务，再由现有分类投影产生结果。不在目录线程复制高德查询或命名算法。已有地点任务运行时复用其状态，记录待继续阶段，不并发启动第二套任务；原继续匹配/重试查询失败入口仍可接续。scheduler的价格刷新职责不扩大为新房采集。

复用qualification/workflow/position状态，不增加并行住宅准入状态机。仅新增必要的分阶段采集结果元数据：阶段、错误code、最后尝试时间及是否真正可重试。映射：基本事实完成但缺主体地址→待地点匹配；身份不符→身份冲突；明确非住宅→对应分类完成；普通超时→本项目网络待重试；验证码/服务不可用→暂停。

retryable_sources读取当前事实和阶段，旧address_error保留诊断但不一概触发浏览器重试。历史错误通过确定性投影兼容，不靠删错误让结果变好。保留请求预算、连续失败上限、验证冷却、取消及发布前快照校验；日志区分transport/protocol原始原因。

## 4. 规则启用与回退

registry meta使用独立admission_address_policy=amap-subject-address-v1标记；缺失时保持旧地址门槛，只对已激活collection-pipeline-v2对象启用高德兜底。GET/启动不自动启用。

正式启用前，只读打开生产快照模拟新策略，输出逐项前后地址来源、收录/排除/待处理及地图/租金/法拍资格变化。启用需审核当前预览、快照匹配、维护窗口和仓库外备份。回退关闭新地址规则重新投影，保留原事实/关联/用户后续写入，不整库覆盖。

## 5. 影响范围

- 基本采集：tmsf_property_type.py、directory_collection.py、community_enrichment.py。
- 共享地址/分类：community_address.py、directory_policy.py、community_admission.py、use_review_scope.py、use_review_policy.py。
- 衔接/API：directory_workflow.py、directory_workflow_routes.py、现有PositionJob及互斥机制。
- UI：DirectoryFlowWorkspace.tsx和现有目录详情/地址来源组件，不新增人工资料页面。
- 实现前重读最新筛选栏、候选卡片和继续匹配变更，不回退其他任务已发布功能。
