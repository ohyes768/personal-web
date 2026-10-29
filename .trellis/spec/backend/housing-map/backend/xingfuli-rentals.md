# 幸福里租金来源试点契约

> 2026-10-29：来源“发现”与“按需探查”已独立成 [发现与探查契约](./xingfuli-discovery.md)。本文件仍是采集器的口径：
> 真实 neighborhood_id 与 seed 的分工、provider 隔离、限速冷却与快照隔离不变。

## 1. Scope / Trigger
修改 `xingfuli_rentals.py`、`xingfuli_pilots.py`、`rental_reference/providers.py` 或租金刷新/查询/覆盖率前必读。幸福里为已确认小区的试点来源，不能作为 TMSF 住宅资格证据。

## 2. Signatures
- `XingfuliClient(timeout=20, directory=..., fetcher=None, delay=5, cancel_event=None)`；`crawl(source_id, seed_listing_id, *, community_name, property_type, max_pages=10, details=True, cancel_event=None) -> SeedRunResult`。
- `providers.active_sources(registry) -> {community_id: source_record}`；同小区优先 matched xingfuli，否则 matched fang，不混样本。
- `providers.same_source(entry, provider, source_id)`：provider + 真实来源小区 ID；缺失旧 provider 按 fang 兼容。
- `scripts/import_xingfuli_pilots.py --data-dir PATH` 默认只读预览；写入必须显式 `--apply --maintenance`，先停止服务和其他目录写入者。

## 3. Contracts
权威来源关系仍在 CommunityRegistry，identity=`source='xingfuli',kind='community',sid=<真实 neighborhood_id>`，另存字符串 `seed_listing_id`。列表 URL `/zufang/neighbor-house-list/hz-<种子房源ID>.html` 的数字不是 neighborhood_id。试点导入不创建住宅、不复活解除/ignored来源，保留原 Fang 关系用于显式回退。

只允许 HTTPS m.xflapp.com 的杭州列表/详情及 `/f100/api/search_api/rent` GET，拒绝 userinfo/异常端口/fragment，HTML入口拒绝 query。HTTP重定向不跟随；403/429/验证内容触发独立一小时冷却，持久化 `rentals/xingfuli_request_state.json`，使用独立 OS 锁保证同数据目录请求串行、至少5秒间隔，不自动处理验证码。假客户端可零延迟离线测试。

首屏 `script[name=pia-ssr-data]` 的 query.city=hz、query.id=seed；列表 `_list/_hasMore/_updateParams`。后续网页内部接口使用 channel_id=94349583687、house_id=seed、house_type=3、aid=1370、app_name=f100、count=20、refresh_type=2、offset/search_id、list_style=same_neighborhood_list。status=0 才成功，读取 items/has_more/offset/search_id。内部网页接口没有公共开放 API 的稳定性承诺。

所有房源 neighborhood_id 必须等于绑定 ID；大整数 ID 保持字符串。游标必须推进，重复末页、结构缺失、错误响应、上限截断都不能当作 complete。空列表还要核验种子详情归属，不能只根据 URL 回显宣称 empty_ok。种子下架核验失败保留旧数据。

只对整租条目读取并核验实际详情 query.id、neighborhood_id、月租单位、面积和整租方式；合租保留 shared_rental 供排除明细。property_type 来自当前权威目录的 effective_property_type，标记 property_type_origin=community_directory，不伪造幸福里用途证据；published_at 未证实则 null。详情失败=>partial_detail，不发布为完整新样本。现有 select_valid/detail_fetched、中位数、疑似重复、最少3条、过期30天口径不变。

缓存、失败保留、查询与覆盖率均比较 provider+source_id。publish_run.preserved_sources 接受 `(provider,sid)`；旧字符串仍代表 fang。同数字 ID 的其他平台快照不能保留或显示。解除幸福里后选择仍有效的 Fang，旧幸福里数据立即失效。公共 API 响应形状不变，source_links 指向真实提供方，前后端均白名单校验。

## 4. Validation / Error Matrix
| 条件 | 结果 |
|---|---|
| 小区不在当前已收录住宅 | 不采集、不导入 |
| 搜索 HTML 返回全市推荐、接口 params error | 未验证成功，禁止导入候选 |
| 归属错误/游标不前进/重复页 | list_failed，保留同来源旧快照 |
| 任一整租详情核验失败 | partial_detail，不采用该小区新批次 |
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
