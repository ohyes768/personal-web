# 设计草案（规划中）

## 路径
名称采集 → community 名录＋project 索引 → 保存候选 → 获取/校验详情 → 发布证据 → 身份关联/住宅资格投影 → 现有小区管理 → 独立高德定位。

索引：https://www.tmsf.com/include/hzweb/index_search_center_property.js 。项目链接使用索引的 siteid/propertyid，不能拼二手房 ID。

## 身份与消费者兼容
- 新来源采用 tmsf/project/propertyid，与 tmsf/community/communityid 隔离。现有 sources 唯一键含 source/kind/sid，优先复用，不预设需要建新表。
- directory_collection 当前 existing 缓存只用 source_id 作键，必须改为至少 (source_kind, source_id)，历史事实兜底也要类型隔离。
- 审计单项 enrich/retry、价格/楼龄刷新、关联/迁移、定位与历史资料等所有把 tmsf source_id 当 ESF ID 的消费者；project 来源不得走 ESF URL。
- 优先关联证据一致的唯一已有小区，不以项目 ID 自动证明主小区身份。人工关联保护、分期歧义待处理，避免自动物化重复主小区。

## 详情获取
- 索引走现有轻量 HTTP，详情先识别真实正文。错误区分 challenge/timeout/identity_mismatch/missing_facts/truncated_address。
- 用户本机 Chrome 成功不等于 NAS 成功。浏览器 worker 为待验证方案：隔离进程/容器、低并发、会话复用、超时及取消，遇人工验证码暂停该项并报告；不可无限刷新。
- 抽查用途位于 house_float_price_name/house_information_price_residence，状态位于 house_float_name_tips_greenlight；按具体语义区块解析，避免拿到推荐楼盘字段。旧 grey/grey999 选择器不能是唯一依据。
- basicinfo 页不保证地址完整。实际项目地址、售楼处地址和地图地址独立保存；省略号文本不能满足完整地址条件。
- 网络在写事务外，发布时重验来源/人工保护/快照；失败保留已有有效证据。

## 市场、准入及展示
- ESF 挂牌与新房销售证据分开保存，管理“新房”按有效项目证据投影；现有单值 market_state 需要兼容策略。
- community_views 当前两种 market 并存会返回 unknown；listing_gate 当前仍会排除混合小区的 ESF 低挂牌。这两处需联合验证，不能只增加 project 来源。
- 只有确认同一身份且住宅/有效实际地址/新房状态完整的证据才能提供新房豁免。售完后重新按 ESF 规则投影，保留来源、历史和小区身份。
- source-only inventory 也应统一投影 market_state，服务器筛选/总数/分页与主小区一致。
- 沿用现有入口和“不收录中的资料待补”语义，显示新房索引/详情进度及具体失败原因；不增加平行管理页面。
- 缺定位走现有独立任务，高德地址不能反向成为实际地址证据。

## 发布与回滚
先隔离库测试，再只读预览新增、关联、排除和资料不足项，以及对地图/租金/法拍资格的影响。生产执行前备份并核对预览仍有效，执行另行授权。回滚追踪本次来源/关联，不整库覆盖后续业务写入。浏览器失败不能阻断已有二手房采集。

## 审核状态
Q1 已于 2026-10-23 确认为“保留资料待补”。NAS 浏览器及完整地址来源尚未验证，按 implement.md 第 2 步执行。任务已批准实现（2026-10-23 用户确认开工）。
