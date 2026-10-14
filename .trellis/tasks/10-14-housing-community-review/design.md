# 技术设计

## 方案选择
- 只改文案/来源过滤：代价小，但聚合、用途未知旧主档、地图同源问题未解决。
- **推荐采用：保留SQLite主档/来源身份，新增住宅收录状态与持久审核候选。** 共享聚合/决定服务，地图复用准入，价格/租金/法拍原ID不变。
- 重建数据库和全链路：影响大，无必要。本任务规划第二种方案，尚未实施。

## 数据模型
- communities/sources/rejected/events/meta继续维护身份/关联/历史，来源唯一键不变。sources.matched/pending/ignored不替代新的审核状态。
- community_admission：cid主键、state(admitted/review/excluded)、decision_kind(auto/manual)、确认类型/理由/证据引用、更新时间与revision。
- review_candidates：稳定candidate_id、可选existing_cid、state(pending/admitted/excluded)、名称/区域/地址、审核原因、决定/target_cid、version。已处理保留历史，不进待审。
- review_members：candidate_id与source_record_id关联，每个来源最多一个当前归属。法拍asset/auction身份与auction_ids保持原模型。
- schema_version迁移，成员关联/状态/事件同事务；服务建议community_review.py、community_admission.py，模块规模可在实施中细化。

## 聚合及准入
1. 已有有效cid先聚合；旧主档按有效证据分类为住宅/待审/排除，旧删除与合并重定向不复活。
2. 未关联来源复用精确名称/别名、同区、地址一致或GCJ02近距100米、唯一完整名称候选规则。位置不能单独证明身份，manual/rejected优先，不丢分期后缀。
3. 候选之间同样须完整名称与区/地址/位置证据；纯同名只是疑似目标。组内每个成员须满足代表身份证据且无冲突，不用距离链传递聚合。缺名法拍单独待审。
4. 可信匹配已收录住宅的来源自动补资料，不新增小区数；新候选明确住宅且无已有主档/其他候选重复疑点才自动创建并收录。
5. Amap仅线索；TMSF/Fang住宅确认沿用分类器。法拍单套房的住宅/商铺用途不能直接当整小区用途。公寓/其他/冲突待审，明确非住宅可排除并记规则理由。
6. 自动确认后出现真实小区用途冲突回待审并撤出地图；人工确认保存证据与事件，冲突提示但不自动撤销。候选ID、成员、版本和决定持久化；新ID同历史排除名称只提示复核。

## API及事务
保留success/data、422/404/409/503与/api/map/directory前缀；建议新增接口：

| 接口 | 功能 |
|---|---|
| GET residential-communities | 住宅列表及确认方式、来源标签、map_status |
| GET reviews | 候选列表，status=pending/excluded、区/来源/原因/名称过滤，按候选分页 |
| GET reviews/{id} | 成员资料/类型证据、目标推荐、法拍资产/轮次、version |
| POST reviews/{id}/decision | admit/merge/exclude，version、成员选择、目标/住宅确认/标准名/理由 |
| POST reviews/{id}/split | 成员拆分，新候选保持可追踪身份 |
| POST reviews/{id}/restore | 排除回待审 |
| POST communities/{cid}/review或exclude | 主档移回审核或撤销收录，保留ID |
| GET summary | 同一过滤口径库存统计与独立来源采集报告 |

- admit复用existing_cid或创建local-ID，住宅确认、所选成员关联、事件、候选终态一次保存。
- merge目标为有效admitted住宅；其他cid关联冲突、独立人工决定冲突、Fang一对一冲突返回409并全部回滚。主档合并沿用重定向与别名逻辑，同时更新准入与候选。
- exclude只改住宅准入/候选决定，不调用ignore_source/whole-community DELETE连带删除来源；已排除可恢复，旧ignored不重新解释。
- stale version或新增成员返回409重新核对影响范围；重复提交返回同一既有结果或409，不重复建主档。保留旧低层接口供详情/兼容，不能绕过住宅准入。

## 更新时机与法拍
- ingest、用途更新、关联/解绑/合并/删除/恢复后更新受影响候选/准入；批处理收尾汇总。GET不触发网络或隐式写入。
- 法拍复用sync_records/StoreLock：保存发布后同步sources再更新候选，失败保留needs_sync和重试；迁移同步历史记录，不另开上游采集。
- 先asset聚合轮次，再按小区身份聚合。数量区分唯一资产与拍卖轮次；缺asset显示“X处已识别房产，另Y条身份未明确记录”，不能把Y直接当套数。
- 候选排除保留auction_records和法拍未关联展示，不用ignored导致独立法拍采集误跳过；旧删除仍按旧契约生效。新轮次/asset身份提升保持历史人工决定，冲突继续待审。
- 法拍旧待关联组件跳转统一管理来拍筛选，旧API可兼容但用同一决定源。
- RentalAssociationReview是租金绑定任务，保持独立；Fang原始未关联来源纳入候选但保留一对一与快照隔离约束。

## 地图同源
- 地图/看板复用有效住宅集合；历史身份解析可单独提供全集lookup，不为保历史把待审送回地图。
- 地图物业类型读取有效来源/人工确认；property_types.json仅按TMSF源ID提供未整合事实回退，不能与管理分类分叉。
- 共享map eligibility与map_status：住宅有效、道路过滤、合并重定向、坐标合法及覆盖范围；协调静态MERGE_DROP_IDS与主档合并，不能静默丢掉仍计数为住宅的记录。
- 新高德gcj02坐标验证行政区、合法数值及范围，不因地址缺“滨江区”字符串全部误弃；保留旧错位点防护。缺坐标住宅保留，标待补。
- 价格沿用TMSF源ID，租金沿用映射，法拍沿用显式asset/auction身份；local-only不能请求TMSF详情。
- 审核排除改变业务住宅展示，不删除历史；独立采集范围须显式保持原策略，不能顺手将load_communities过滤传播为采集范围缩小。

## 前端
- 拆分CommunityManagement的列表、审核面板、来源证据与共用类型；列按PRD。
- tab数字来自库存summary，决定后刷新列表/统计/地图并修正空末页；默认待审，已排除在状态筛选恢复。
- 审核详情显示多来源原始事实、地图位置、法拍资产/轮次；三种决定、排除原因、成员选择/拆分及影响范围确认。
- 手机折叠详情/可横向滚动，不能挤掉审核原因；来源URL沿用safeDirectoryLink，ID仅详情诊断。
- 最近采集报告标时间和来源条单位，与库存分区显示，保留取消、用途失败与高德截断原因。

## 迁移及回滚
- 用HOUSING_DATA_DIR隔离副本演练；sqlite backup取得一致备份，不直接复制活跃DB单文件；JSON/原ID/历史全部保留。
- 幂等schema迁移及分类，生成原/新cid、候选成员、原因、准入、法拍asset/round差异账目；原身份可解释为住宅/待审/排除/旧删除/合并重定向。
- 两次迁移/重启结果相同，不重跑prepare_directory覆盖meta.prepared或人工决定。
- 生产需另行实施授权：冻结写入/采集，备份，迁移对账后开放。回滚前保护切换后新增审核决定，不能静默丢失。
- 更新community-directory.md及housing-map-admission.md的旧全量展示约定，保留独立采集与历史查询边界。

## 拆分后的责任与补充规则
总设计保留为方向，具体实现归三个子任务，父任务不新增第四块开发。任务1提供状态/人工锁/地图及最小操作入口，任务2复用完成候选/统一审核/完整列表，任务3消费两者先预演再执行。

人工移回/排除设置auto_review_locked；恢复不解锁，主动确认或显式允许自动审核才解除。自动审核先检查锁/拒绝/旧删除，预演固定本地快照不写业务；执行重新核对锁、revision和成员。江汉路小区道路疑点/仅高德标签不自动收录，自动决定记录依据/时间/规则版本。
