# 统一待审核小区与管理页面

## 候选模型
新增review_candidates与review_members，沿用sources唯一身份；candidate_id持久、version及existing_cid，记录成员和终态。每个来源最多一个当前候选归属；已收录来源只作主档资料，无需重复排队。

聚合复用完整名称/别名+同区+地址或gcj02位置证据，不用同名/纯距离/链式传递合并。确定同组才聚合，不确定分行并生成推荐。旧主档review状态作为existing_cid候选；split与成员选择保留来源身份及人工拒绝。

## 统一操作
新增GET reviews/详情/summary及POST decision/split/restore；调用任务1准入事务服务。admit建立/复用主档+确认住宅+批量绑定，merge目标必须有效admitted住宅且检查Fang/既有关联冲突，exclude记候选决定并复用锁。旧低层API不绕过共同规则。

## 法拍与租金
复用auction_association.identity/groups、StoreLock与已保存auction_records；成功发布后同步，失败needs_sync可重试；缺asset独立记录计数、资产提升/旧轮次冲突不丢人工决定。排除不复用ignored误删/跳过法拍。老法拍待关联组件转统一管理来拍筛选。RentalAssociationReview业务任务保持独立，原始Fang未关联来源纳入但仍一对一。

## UI与读模型
拆分CommunityManagement列表、审核详情、来源证据与公共类型；按PRD列，库存summary/过滤分页同口径；事务成功刷新住宅/待审/地图并清理过期详情和空末页。已排除状态筛选可恢复。详情包含确认理由、法拍资产/轮次、安全来源URL与成员拆分；手机不挤掉审核原因。

## 迁移与输出
在任务1schema上增量幂等迁移，历史同步只有读取已有法拍文件，不启动网络采集。提供稳定候选/成员/revision、疑点原因、自动引擎可调用的同一事务决定接口供任务3使用。

## 实施契约（2026-10-14）
- ReviewWorkspace统一候选、summary和事务。review_candidates(id,payload)/review_members(rid,candidate_id)，master-{cid}/review-ID持久化，meta.review_schema_version=1。
- 成员指纹排序稳定，更新资料版本变化；完整名称+同区+地址/位置，组内任意两成员一致才聚合。人工拆分/恢复/排除不被刷新覆盖。
- Registry逻辑抽出_decide_admission/_associate/_merge，公共签名不变。API可在同一事务中拆分并处理选定成员；页面先显式拆分，再独立审核。
- GET reviews/detail/summary，POST decision/split/restore/sync。旧来源绑定/建档不能越过人工锁。详见community-review.md。
- UI拆为CommunityWorkspace/DirectoryCards，复用任务1动作；法拍旧入口打开来拍筛选。库存与来源计数分开，租金业务清单独立。
- GET刷新已有目录候选投影但不导入法拍JSON；历史显式sync、成功发布后同步、失败资料保留可重试。任务3自动收录未启用。
