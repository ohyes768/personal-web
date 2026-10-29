# 技术设计

## 现状和依据

- CommunityRegistry 为唯一关系权威，sources 唯一键为(source,kind,sid)，manual/rejected/ignored 优先。providers.active_sources 已按幸福里优先、否则Fang选择单一来源，不混样本。
- rental_reference/association.py 的 candidates_for/decide/prepare_sources 含 Fang-only 分支；eligible_communities 在目录 admitted 上额外筛滨江。目录模式统一取当前admitted，旧非目录回退资格规则单独兼容。
- refresh.py 已会采幸福里，但缺来源发现仍调用Fang discover；新绑定沿用下一轮采集边界。
- XingfuliClient 的请求锁、至少5秒间隔、独立一小时冷却和取消已存在；URL目前只允许租房列表/详情/分页，不能直接拿来请求小区页和搜索。
- RentalAssociationReview/RentalSourceManager 现有文案及候选类型偏向Fang，后者仍有粘贴表单。
- CommunityRegistry.auto_associate 存在唯一高相似度自动关联分支，不能未经证据预检直接用于幸福里自动绑定：本任务要求名称/别名及地址或可信位置都成立。
- 规范依据：rental-sources.md、xingfuli-rentals.md、community-directory.md、directory-flow.md、community-admission.md、名称匹配和租金统计指南。以本任务PRD覆盖旧“人工粘贴补充”产品方案。

## 实施前技术门：系统怎样找到主页

技术门已于 2026-10-29 通过，证据见 `research/probe-feasibility.md`。结论修正了本节原假设：

- **发现链完全在平台内，只依赖 `m.xflapp.com`**：名称搜索（多 channel）→ 候选 `neighborhood_id` → 读小区主页 `/xiaoqu/hz-<nid>.html` 取真实名称/地址/GCJ02 坐标与 `rentInNeighbor` 入口 → 房源详情 → 同小区列表核验。
- **原「生产服务不存在已验证搜索引擎连接」的前提不成立**：总小区身份可由二手房 channel 自行发现，不需要外部搜索引擎。**禁止**引入外部搜索供应商、付费 API 或广泛爬搜索结果。
- **原「m.99hdf.com 仅在技术门确认必要后限定使用」的前提同样不成立**：总小区页在 `m.xflapp.com` 直接可读。**禁止**引入 99hdf 域名。
- **搜索 channel 的身份语义不同**：二手房 house_type=2（channel 94349530167）返回小区级（总小区）身份但条目无地址坐标；小区 house_type=4（channel 94349530172）带地址坐标但可能只给分区身份；租房 house_type=3（channel 94349530177）给种子线索。发现必须覆盖多 channel，不能只依赖租房搜索。
- **候选身份必须读主页核验**：错误 nid 不会 404，只会渲染出另一个小区；名称/地址/坐标一律取自主页 `neighborhood_info`，不取自搜索条目。
- **不存在名称仍返回 status=0 且 items 非空**（二手房 channel 甚至 total=9514），HTTP 状态、status、查询词回显、items 非空四者都不能作为命中证据。
- 分区冲突按主页名称判定：主页名为「白金海岸(南区)」与内部「白金海岸」不构成同一身份，不自动绑定。

不要：硬编码白金海岸URL/ID或样本列表；把会话搜索工具作为后端依赖；把普通推荐当同一小区；擅自加入外部搜索供应商、付费API或广泛爬搜索结果。技术门已通过，但样本量有限（4 个名称），不得据此宣称全量命中率。

## 服务边界和数据

建议新增 xingfuli_discovery.py（平台搜索/主页解析/入口核验）和 rental_reference/probe.py（按需任务与决策）；XingfuliClient.crawl 继续唯一负责样本采集，不复制统计器。复用现有请求限速和冷却，抽取共享transport或注入严格验证器；新增路径只允许已验证API参数和小区页，不把现有fetch变成任意URL下载器。无需改TMSF专用browser_worker。

唯一来源关系仍在registry.sources。仅主页或尚无入口的候选放在registry.meta的租金工作流状态中，不能创建matched租金来源。候选/selected_page是工作流状态，不是第二份可写绑定台账。明确schema_version，兼容旧Fang review字段，不让新provider覆盖旧搜索尝试历史。

候选契约：
- opaque candidate_id / revision、provider=xingfuli、真实neighborhood_id（字符串）。
- 来源名称、独立地址/行政区、longitude/latitude/coordinate_system、分区标记及主页URL。
- evidence、evidence_gaps、请求名称/别名及验证时间；不同主页ID不按名称去重。
- 若已发现租金入口，另存seed_listing_id、verified_listing_url、验证到的neighborhood_id和时间。
- 拒绝对、查询/人工选择的fingerprint、selected_page及job_id。fingerprint覆盖身份/位置/分期/seed，不能接受过期确认。
- 写入前重新计算admitted、有效来源、ignored/rejected/manual保护；禁止普通读取触发发现或重绑。

## 两条执行流

### 常规更新：简单自动匹配

1. 取得admitted当前集合和active_sources，优先采已有来源，不自动换源。
2. 对未绑定且未受人工保护者，按主名/可信别名调用幸福里租房搜索；去重词，有界HTTP预算及真实负缓存。失败与无匹配、预算不足分开。
3. 搜索条目只生成暂存线索，按真实小区ID分组，读取少量详情确认名称/区域/可信位置；全市推荐即使回显查询词也丢弃。
4. 唯一完整名/可信别名 + 同区域 + 可靠独立地址一致或已知GCJ02点100米内 + 无分区冲突，才能自动绑定；位置不可靠/坐标系不明不能满足位置条件。
5. 多候选、分区或缺证据进待处理。新绑定标记待采集，下一轮使用现有采集器。Fang历史发现继续兼容，不重新设计其抓取器。

### 按需探查：主页选择后继续找入口

1. 点击“探查幸福里来源”，读取缓存候选或启动按小区有界job。后台查询主页和经过技术门验证的真实发现链；返回job_id，前端轮询。
2. 候选展示外部事实及与内部位置对照。多候选由人单选；唯一强证据可继续，单候选缺证据需确认。不自动把总区与分区混成一条。
3. 确认主页时提交candidate_id+revision，事务只保存selected_page人工决定，不保存租金matched；网络阶段重新占用同一请求任务槽。
4. 阅读主页租房模块，提取实际房源链接，不扫全站、不取其他小区推荐。逐个有界验证seed详情的城市/房源ID/小区ID；再检查同小区列表归属。URL中的数字始终是seed，不是小区ID。
5. seed失效可在同一选定主页的实际入口内尝试其他seed；不得跨ID悄悄“修复”。没有可信入口时保留主页选择、显示原因和“重试租房入口”。
6. 验证完成后通过既有租金edit/publish排他事务创建/更新真实xingfuli来源、保存seed和关联证据；复查资格/人工决定/revision/取消/当前active来源。新关联的provider和ID进入现有快照隔离和覆盖率逻辑。
7. 不直接触发全量采集；页面显示“已关联，待采集”，接现有采集入口。选择主页不得产生“0条租金”的假快照。

## 任务、API和并发（拟定契约）

沿用现有 /rentals/association-tasks 返回provider、workflow_stage、主页候选和selected_page的可选字段，历史前端字段保持兼容。最终URL在实现时与现有router核对：
- POST /communities/{cid}/rental-source/probe：启动/复用该小区主页探查（202，job_id）。
- GET .../probe：只读任务/候选/selected_page/status/revision；无网络请求或隐式持久化。
- POST .../probe/select：{candidate_id,revision}，保存主页选择并继续验证入口（202）。
- POST .../probe/retry：从当前已选主页重试入口，或在无主页时重新查找。
- POST .../probe/cancel：取消当前探查；保留已存在人工选择及旧绑定。
已有skip/reopen复用；既有绑定接口仅接已核验的租金候选，禁止把主页candidate当seed确认。主页候选确认用opaque ID，不接受客户端任意URL。
- 未收录/删除→404或409（依现有路由约定）；候选或revision变化/采集中→409；非法输入→422；上游异常放job可重试状态；持久化错误→503。冷却/无匹配不是成功绑定。
- 网络在事务外，最后短事务仍用RentalRefreshService.change_sources及RentalPublishLock。同一租金服务的start mutex协调refresh和probe，真实网络job不重入；waiting_selection不是运行中的网络job，不长期占槽。
- 同小区重复POST返回相同活动job；其他活动探查/refresh按共享槽返回可解释busy。即使互斥，最终事务仍防CLI/其他管理修改。
- 任务有限状态：searching_homepage→needs_homepage_selection→resolving_entry→bound_pending_collection；支路homepage_not_found/entry_not_found/upstream_failed/cooling_down/deferred/cancelled/interrupted。人工selected_page不因取消/重启清空。
- schema_version与revision持久化在registry.meta，重启只把未完成网络工作改interrupted；GET不恢复网络，重试才继续。预算按所有HTTP计，包括别名/主页/详情/列表验证。
- 默认单次自动发现不超过现有5次HTTP预算；手动单小区探查初定最多12次HTTP、总时长不超过5分钟，技术门根据真实链核对；达到上限返回deferred，不把未查项计失败。每真实请求至少间隔5秒，保留一小时冷却，不循环自动重试验证页。

## URL和页面身份

明确白名单 HTTPS m.xflapp.com 的已验证 `/f100/api/search`（租/二手/小区三 channel）、`/xiaoqu/hz-数字.html`、租房详情/同小区列表/既有分页。**不引入 m.99hdf.com**——技术门已确认总小区页在 xflapp 上直接可读，该域名无必要性。拒绝userinfo、异常端口、fragment和未验证重定向；查询参数仅API白名单字段，不接受任意用户URL。不获取经纪人个人资料，日志不记录HTML/headers/cookies/地图key。

## 前端

RentalAssociationReview 与详情来源区共用探查状态/候选选择组件；移除RentalSourceManager现有URL表单及Fang粘贴提示。列表未找到/失败/待处理都可进入探查，冷却时展示可重试时间；操作按钮显示任务阶段，支持取消。候选展示事实/位置对照/来源只读链接，不显示平台ID作为决策要求，不将最高相似度默认当人工选择。只读来源链接不是要求用户手动探查。
不受地图SDK加载失败影响，位置至少能展示外部地址及距离/坐标证据状态。绑定后触发housing-rental-data-changed并刷新summary/detail/coverage；失败和无入口不错误刷新旧样本日期。

## 兼容与回退

保留Fang和已导入幸福里关系、旧无provider=Fang兼容及provider+ID快照隔离。新字段增量落meta，无第二个映射库，不重新播种已解绑来源。停用发现/探查入口可回退新能力，不删除已确认来源或历史样本；禁止整库回滚覆盖人工操作。历史显式链接API暂兼容，不在UI引导；新探查接口不收URL。

## 风险和取舍

- 最大未知是主页发现覆盖，尤其白金海岸总ID。失败必须诚实显示；发现技术门和A5不能被“手工写已知ID”替代。
- 一期保持每小区单一租金来源；分区不自动汇总，无法确认对应范围就保留待选择/证据不足。
- 取严格自动证据，牺牲自动命中率；人工只做主页身份选择，后续技术核验仍由系统完成。
- 公开页面波动、seed下架和被拦截不会变成零房源；隔离测试覆盖恢复和保留旧值。
