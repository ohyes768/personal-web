# 技术设计

## 现状证据

`rental_reference/association.py::eligible_communities` 仍在admitted上限制滨江；candidates_for/decide/prepare_sources含Fang-only逻辑。`refresh.py::_execute` 已能按providers.active_sources采幸福里，但缺映射时仍统一创建Fang客户端并调用Fang discover。应扩展发现和审核边界，而非再造采集器。

依据：rental-sources.md、xingfuli-rentals.md、directory-flow.md及前置任务verification.md。共享工作区存在前置未提交修改，实施时重新检查，禁止覆盖或重复提交。

## 第一阶段技术门

低频测试幸福里页面实际搜索请求，记录脱敏响应、requested/actual keyword、真实候选身份字段及有效种子获得方法。用正负例证明没有返回全市推荐。不能把已知种子列表采集冒充名称搜索。

搜索成功才接自动发现适配；不可用则记录能力限制，支持现有来源和受控人工公开链接候选，自动发现明确未完成。接口形态未验证前不虚构URL/签名；不买付费搜索或绕过验证。

## 数据与适配边界

CommunityRegistry仍是唯一关系权威。统一候选含provider、真实source_community_id、source_name、外部address/district/location、source_url、幸福里seed_listing_id、关键词应用证据及时间，所有大整数ID为字符串。

审核按registry record_id确认，唯一性按provider+source_id；指纹覆盖provider/身份/种子及决定性位置证据。不能跨平台按相同数字ID合并。复用现有严格自动关联规则，相似度只排序，身份缺证据人工处理。

现有meta rental_review:{cid}需兼容旧Fang记录，新增按provider搜索状态和尝试时间，防止幸福里失败覆盖Fang进度。小区级API汇总可以继续复用，底层不能仅留最后一条字符串。

## 执行流

1. 统一admitted快照建立全量目标，去掉目录模式额外滨江过滤，旧非目录回退路径另行兼容。
2. 复用active_sources，先采现有映射，保持原provider优先级和独立冷却。
3. 缺来源先复用候选/人工保护，再按能力可用性与预算请求幸福里；Fang既有发现能力保留，不能因首个平台失败启动无界连环重试。
4. 网络在事务外，落候选与绑定前重验目标、拒绝关系、唯一性和完整revision；取消不落库。
5. 强证据自动绑，其余待选择；新绑定显示待采集，下一轮采。采集发布前重验当前provider+ID/资格/取消，失败只沿用同来源旧快照。

## 任务与展示

沿用有界搜索与每来源限速，预算按HTTP计数，包含别名和身份详情。优先从未查询及上轮deferred，真正empty才负缓存24小时，不在读取时滑动searched_at。重启标记interrupted，下一轮恢复未处理目标；不放宽5秒间隔或冷却来追求一轮完成。

复用更新入口与association审核面板，扩展provider能力、候选和未采原因。保留旧stage/association字段兼容，未知新字段前端默认处理。金额与样本数只能来自实际采集结果，刚绑定不显示零房源。

API扩展现有 /rentals/association-tasks 和来源搜索/确认/skip/reopen，无第二个租金更新入口。公开链接只接受受支持HTTPS白名单和路径，服务端核验重定向与归属，导入仅成候选。

## 兼容与回退

缺provider的旧数据按Fang兼容，既有映射不重绑。停用新发现适配即可回退搜索功能；保留已确认关联、事件、拒绝和历史样本，不能整库回滚。前置采集器未交付前，本任务不能独立声称生产全量可用。

上线前只读报告admitted数、现有来源、缺来源、待审核、保护项及预算估计；只对明确审阅的范围进行真实烟测，不在本规划中部署或写生产。
