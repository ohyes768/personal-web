# 住宅收录状态与人工撤销

## 模型与契约
新增community_admission（cid、state、decision_kind、住宅类型、证据/理由、revision、auto_review_locked、锁定理由/时间）。人工移回/排除不可用现有whole-community DELETE代替，避免关联来源ignored导致法拍误隐藏。

提供共享有效住宅/身份查询与map eligibility服务。确认/移回/排除/恢复在SQLite事务内更新状态、锁与事件，version避免覆盖并发决定。人工确认优先，新冲突提示；自动收录主档出现真实用途冲突可回审，但不能覆盖人工确认。

API可复用总设计communities/{cid}/review、exclude，增加admit/restore-admission与显式allow-auto-review动作；后者不能与普通恢复混同。旧source关联/新建接口不等于住宅收录，不绕过准入。读接口返回map_status与锁定原因。

地图复用住宅集合与有效用途。历史业务提供身份全集lookup；独立采集继续原策略，不能把地图过滤传播为价格采集目标过滤。高德gcj02验证数值/行政区/范围，旧失准保护保持；协调静态合并drop与有效主档。

旧主档按现有有效证据初始化，记录migration来源，与运行时新候选自动收录区分。schema_version、sqlite一致备份、隔离HOUSING_DATA_DIR，两次迁移/重启对账，原始JSON/历史ID保留。

## 提供给任务2/3
共享状态服务、事务动作、revision、人工自动处理锁、住宅查询/map_status与有效类型读取。任务2复用，不另建第二套收录/撤销规则；任务3自动写入必须先检查锁和人工决定。

## 实施契约（2026-10-14）
- `community_admission` 使用 cid 主键和 JSON payload，与现有主档存储风格一致；schema_version 持久化在 meta。人工动作入口为 registry.decide_admission，SQLite事务内版本检查、写状态和事件。
- 状态为 admitted/pending/excluded；`admission` 保留已保存决定，`admission_state` 是结合当前用途证据后的有效状态。任务2的住宅列表、审核数量和任务3规则输入必须用有效状态，不能直接用来源 residential_state 或 sources.matched。
- POST communities/{cid}/admit|review|exclude|restore-admission|allow-auto-review，body revision/reason/property_type；普通恢复不解锁，解除锁仍待审。通用路由放在旧 restore/merge 后面。
- community_views 为共享展示投影，load_display_communities 用于地图/评分，load_communities 保留完整历史/采集身份。手工确认类型优先，非人工收录的类型使用当前证据。
- 本阶段新主档始终 pending；地图状态与收录状态分开。原两个tab布局暂时保留，详情加入动作，最终列表归任务2。
