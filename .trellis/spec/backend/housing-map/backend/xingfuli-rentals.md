# 幸福里租金来源试点契约

> 2026-10-29：来源“发现”与“按需探查”已独立成 [发现与探查契约](./xingfuli-discovery.md)。本文件仍是采集器的口径：
> 真实 neighborhood_id 与 seed 的分工、provider 隔离、限速冷却与快照隔离不变。

## 1. Scope / Trigger
修改 `xingfuli_rentals.py`、`xingfuli_pilots.py`、`rental_reference/providers.py` 或租金刷新/查询/覆盖率前必读。幸福里为已确认小区的试点来源，不能作为 TMSF 住宅资格证据。

## 2. Signatures
- `XingfuliClient(timeout=20, directory=..., fetcher=None, delay=3, cancel_event=None)`；`crawl(source_id, seed_listing_id, *, community_name, property_type, max_pages=10, details=True, cancel_event=None) -> SeedRunResult`。
- `providers.active_sources(registry) -> {community_id: source_record}`；同小区优先 matched xingfuli，否则 matched fang，不混样本。
- `providers.same_source(entry, provider, source_id)`：provider + 真实来源小区 ID；缺失旧 provider 按 fang 兼容。
- `scripts/import_xingfuli_pilots.py --data-dir PATH` 默认只读预览；写入必须显式 `--apply --maintenance`，先停止服务和其他目录写入者。

## 3. Contracts
权威来源关系仍在 CommunityRegistry，identity=`source='xingfuli',kind='community',sid=<真实 neighborhood_id>`，另存字符串 `seed_listing_id`。列表 URL `/zufang/neighbor-house-list/hz-<种子房源ID>.html` 的数字不是 neighborhood_id。试点导入不创建住宅、不复活解除/ignored来源，保留原 Fang 关系用于显式回退。

只允许 HTTPS m.xflapp.com 的杭州列表/详情及 `/f100/api/search_api/rent` GET，拒绝 userinfo/异常端口/fragment，HTML入口拒绝 query。HTTP重定向不跟随；403/429/验证内容触发独立一小时冷却，持久化 `rentals/xingfuli_request_state.json`，使用独立 OS 锁保证同数据目录请求串行、至少3秒间隔，不自动处理验证码。假客户端可零延迟离线测试。

租金更新首屏直接请求列表 API（offset=0，不需要 search_id），不读取 HTML。API 使用 channel_id=94349583687、house_id=seed、house_type=3、aid=1370、app_name=f100、count=20、refresh_type=2、offset/search_id、list_style=same_neighborhood_list。status=0 才成功，读取 items/has_more/offset/search_id。内部网页接口没有公共开放 API 的稳定性承诺。

所有房源 neighborhood_id 必须等于绑定 ID；大整数 ID 保持字符串。游标必须推进，重复末页、结构缺失、错误响应、上限截断都不能当作 complete。租金更新不请求详情；空列表无法证明小区归属时记 list_failed，保留旧数据，不伪造 empty_ok。来源匹配的入口核验继续保留详情与列表检查。

租金更新仅用列表字段筛选整租，排除疑似隔断、无效租金/面积/户型及重复。property_type来自权威目录，property_type_origin=community_directory，published_at未知仍为null。采用下述显式列表证据后允许进入统计；中位数、分组至少3条、过期30天不变。

缓存、失败保留、查询与覆盖率均比较 provider+source_id。publish_run.preserved_sources 接受 `(provider,sid)`；旧字符串仍代表 fang。同数字 ID 的其他平台快照不能保留或显示。解除幸福里后选择仍有效的 Fang，旧幸福里数据立即失效。公共 API 响应形状不变，source_links 指向真实提供方，前后端均白名单校验。

## 4. Validation / Error Matrix
| 条件 | 结果 |
|---|---|
| 小区不在当前已收录住宅 | 不采集、不导入 |
| 搜索 HTML 返回全市推荐、接口 params error | 未验证成功，禁止导入候选 |
| 归属错误/游标不前进/重复页 | list_failed，保留同来源旧快照 |
| 列表结构/分页/归属不能验证 | list_failed，不采用该小区新批次 |
| 冷却内再启动 | 不请求，不延长冷却，deferred |
| 取消发生在响应返回后 | 丢弃该请求结果，不发布 |
| 试点已导入后解除 | protected，重跑不重新关联 |
| 名称不唯一/地址与位置证据不足 | unverified，禁止强绑 |

## 5. Good / Base / Bad
Good：东方郡已确认幸福里来源，翻到 has_more=false，再用原统计发布；其他小区 Fang 不受其冷却影响。Base：种子下架，保留原快照和原采集时间，报告失败。Bad：用52条挂牌数当52条合格整租、用 URL 种子当小区ID、将“元/月起”当整租均价、忽略来源只比数字ID。

## 6. Tests Required
`test_xingfuli_rentals`：真实JSON形状、ID/城市/单位、错误页、分页、空列表身份、重复末页、详情、取消、独立冷却。`test_rental_providers`：优先级、解绑、跨平台同ID、混合原子发布、全缓存第二轮、查询/覆盖率隔离。`test_xingfuli_pilots`：只读预览字节不变、幂等、解除不复活、错地址。沿用 rental API/storage/statistics/refresh/association 和 Fang 测试；前端 rental-xingfuli/reference/directory-flow、TypeScript、ESLint、生产构建。公网验证为手动低频，不进入自动测试。

## 7. Wrong vs Correct
Wrong：`entry.source_community_id == mapping.source_id` 就复用；Correct：`same_source(entry, mapping.source, mapping.source_id)`。
Wrong：`source_id = URL数字`；Correct：存真实 neighborhood_id，同时独立记录 seed_listing_id。
Wrong：对 full_text=璞悦湾 的 HTTP 200 全市列表进行自动关联；Correct：搜索未验证成功，当前仅显式试点导入。


## 列表API抽样契约（2026-10-29）
- 替代租金更新原逐套详情核验和10条详情早停；来源匹配/探查的身份和入口核验不变，不新增模式开关。
- 首屏和后续均GET `/f100/api/search_api/rent`：house_id=已确认种子、channel_id=94349583687、house_type=3、aid=1370、app_name=f100、count=20、refresh_type=2、list_style=same_neighborhood_list，offset从0开始。分页续传服务端offset/search_id，禁止自行推算。
- `_sample`逐行检查真实neighborhood_id和元/月单位，包括配额之后的行。显式样本证据 `verification_method=XINGFULI_LIST_API_EVIDENCE`（值xingfuli_list_api_v1），detail_fetched=false；property_type_origin=community_directory，住宅类型和有效户型为列表证据准入必要条件。
- quota=10按统一select_valid过滤后的有效数计算。合租/疑似隔断/缺失正值/无效户型/相同ID和疑似重复不占配额，依返回顺序补位，无额外面积门槛。floor=null沿用现有疑似重复键，不能声称完全去除同实体挂牌。
- 满10不再翻页；本页配额后的非重复行仍留诊断，quality_flags含outside_sampling_quota，统计排除该标记。真实耗尽不足10记complete、保留实际数；上限10页仍记truncated。无归属证据的空列表失败保留旧快照。
- `quality.sampling={mode:'list_api',quota:10,qualified:<select_valid数量>,sampled:<实际检查的非重复行数>}`。详情计数保持0，不伪造detail_success。样本和快照证据不追溯改写，旧详情快照仍可读，6小时复用仍按旧证据展示。
- API沿用sampling字段透传；前端依据mode显示“列表抽样：最多10套整租，未经逐套详情核验”，包括筛选后no_samples状态；旧sampling无mode保留原说明。
- 幸福里传输、discovery/probe/matching/refresh默认和最低真实间隔统一3秒；Fang仍5秒，假fetcher可0秒，一小时冷却和共享OS请求锁不变。
- 回归：test_xingfuli_rentals覆盖首屏仅API、配额/补位/分页/错误/取消/冷却/全入口默认3秒；test_rental_statistics验证显式列表证据准入、未知证据与其他provider拒绝；test_rental_split验证快照元数据；rental-reference测试新旧说明。

## 继续采集（数量）契约（2026-10-30）
- **采集范围只有一个来源**：`RentalRefreshService._scope()` = 已收录住宅 × 已关联来源（`xingfuli_only` 时只取幸福里）。
  待采集数量与“继续采集”共用这份名单，数量与实际下手的对象不许各算各的；`start()`/`_execute()`/数量统计都从它取。
- **完成判定**：当前来源与快照一致 + 快照状态可采用（complete/empty_ok）+ 最近一次采集也成功且已发布
  （快照 captured_at 与采集结果一致）。没有快照、采集失败（list_failed/truncated/partial_detail）、采完没发布、
  换过来源，都算待采集；**已查完但无房源（empty_ok）算完成**，不重复采集。
- 每个小区的采集结果记在 job 的 `community_outcomes`（来源、状态、captured_at），跨任务保留；换来源后旧结果不再算数。
- `POST /rentals/refresh` 接受 `mode=all|continue`；`continue` 只补待采集小区，已完成的按 `preserved_sources`
  保留原快照数据，不重爬也不重发。`GET /rentals/refresh` 始终返回快照并带 `continuable`（算不出时为 null，不假装 0）。
- 数量按台账/快照文件指纹缓存，状态查询不重算台账；台账或快照变了才重算。
- 回归：`test_rental_continue` 覆盖数量归零、只补缺的那些、失败保留旧数据但仍待采集、换来源重采、数量与 continue 同源；
  `test_rental_api` 覆盖无任务时也返回数量；前端 `directory-flow` 覆盖按钮数量、禁用条件与 continue 请求体。
