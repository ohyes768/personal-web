# 房天下退役技术设计

## 决策与边界

本任务只退役房天下运行能力。幸福里是唯一当前租金来源；CommunityRegistry 继续是关联权威。保留历史库、样本、快照、人工审核及事件，不新增数据库迁移、退役开关或第二份映射表，不自动部署或重跑生产批次。

旧库兼容定义为“能启动、能保留、不会误用”，不再保证旧房天下独立采集模式可运行。既有人工准入决定原样保留；今后的自动用途判断不采用 Fang 证据。仅有 Fang 的未决记录不会凭空变成住宅，保持待核对。现行 TMSF/高德审核规则、区域、新房排除和统计阈值不变。

## 模块与数据流

```text
CommunityRegistry matched Xingfuli
  → providers.active_sources（只选幸福里）
  → 原 eligible_communities / 新房排除
  → XingfuliClient / XingfuliTransport
  → select_valid / CommunityBatch / publish_run
  → 同 provider + neighborhood_id 快照
  → summary / detail / directory_coverage
```

### 1. 共用采集类型

新增 `backend/housing-map/src/services/rental_reference/crawl_types.py`，迁入 `SeedRunResult`、`RentalCrawlCancelled`、`CrawlProgress`。保留字段、默认值、构造参数、`snapshot()` 和取消异常的 `completed`/`partial` 语义，避免改变进度与取消协议。先更新 xingfuli_rentals、xingfuli_transport、probe、discovery_checkpoint、refresh 和保留的 association 调用，再删除 Fang 模块。类型虽有 detail_cache_hits 等旧字段，若当前响应/fixture 使用则本任务保留，禁止为清理名称额外改响应协议。

### 2. 唯一租金 provider 与查询

- `providers.active_sources(registry)` 只选择 matched、有效 community 的 `xingfuli`；保留同 provider 重复关联检查。移除 `xingfuli_only` 参数与所有调用点。
- `same_source(entry, source, sid)` 只有显式 `source == 'xingfuli'` 且 entry 的 provider 与 ID 都相同才命中；缺少 provider 不补为幸福里。ID 仍为字符串，不将 seed ID 当 neighborhood_id。
- `source_url` 仅生成幸福里来源链接，遇到不支持 provider 明确拒绝，不构造 Fang URL。
- `refresh.py` 去除 FangClient、FangRequestPolicy、FangDetailCache、crawl_runs 和缺来源自动 Fang 搜索，保留幸福里采集、缓存、原子发布与任务状态恢复。缺来源由既有独立 matching 流程处理。
- 无 registry 时 refresh 没有可采集计划，沿用无来源错误语义，不读取 rental_sources.sqlite3 或映射 JSON 去采集。summary/detail 返回原协议的 unmapped/无当前数据，不能回退到历史 Fang 样本。
- `_mapped_entry` 保留显式幸福里 provider+ID 的跨历史内部社区 ID 查找，删除 Fang regional samples 合成快照分支。coverage 与 API 使用同一 provider 筛选。
- `storage.publish_run` 不再接受旧字符串 preserved_sources 身份：仅接受显式 `(xingfuli, sid)`；旧字符串或非当前 provider 明确 ValueError，在替换 current 指针前失败。load_current 仍能解析历史快照，读到不等于展示或复用。
- 统计模块的通用数学能力保留；运行入口负责过滤 provider，不把 select_valid 变成历史数据擦除器。

### 3. 来源接口与前端

所有路径下表省略后端 `/api` 前缀；前端仍用 `/api/map` 代理。

| 接口 | 最终行为 |
|---|---|
| GET `/rentals/sources` | 保留响应形状，仅返回当前幸福里 mapping，candidate_count 为当前有效值（无旧候选时为 0） |
| GET `/communities/{id}/rental-source` | 保留 community、mapping、candidates 形状；mapping 仅幸福里，旧 Fang candidates 不返回 |
| DELETE `/communities/{id}/rental-source` | 只解除当前幸福里关联；保留互斥与人工保护，绝不自动回退 Fang |
| POST `.../rental-source/search` | 保留轻量 410，不创建 SourceStore、不读取旧库、不发请求；合法旧请求仍为 410 |
| PUT `.../rental-source` | 同上，410 引导使用幸福里主页选择 |
| DELETE `.../rental-source/candidates/{source_id}` | Fang 候选专用旧入口改为无副作用 410 |
| association-tasks、matching、probe 系列 | 保留；bind 继续 410，skip/reopen 和幸福里 probe/select 行为不变 |

保留旧 search/confirm 输入模型的最小校验，避免本次清理额外改变畸形请求的 422 行为。410 壳不引用已删除采集代码。

`sources.py` 保留精简的 registry 适配层（get/all_mappings/pending_counts/remove/序列化），删除 Fang 网络发现、SQLite 映射写入、种子导入与候选 confirm/reject 实现。无 registry 的来源管理调用明确 503“目录尚未准备好”，不静默建立第二份数据库。community 不存在仍为 404。

前端删除未使用的 `SourceCandidate`、PUT 确认状态与 search notice 分支，保留幸福里 mapping 展示、解除与 XingfuliProbe。`RentalSource.source` 收窄为显式 xingfuli；safeSourceLink 删除 Fang 主机，幸福里 HTTPS/路径/端口/凭据约束保持。目录来源与人工用途历史页可继续显示“房天下（历史）”，但不提供启用、确认或采集动作。

### 4. 匹配、目录与用途

- `association.py` 保留 eligible_communities、PREFIX、read_review 和 skip/reopen 所需元数据；删除 Fang candidates_for、reviews、prepare_sources 等专属发现实现，调用方同步清理。fingerprint/save_review 等先以 matching/probe 的真实引用为准，仍有公共用途则保留。
- `directory_collection.py` 删除 fang_names 与 ADAPTERS 的 fang 项。API 发现来源仍只接受 tmsf，不新增可选模式。
- `community_directory.prepare_directory` 保留 TMSF/法拍等初始化，停止把旧 Fang 映射/候选写入 registry；已存在 registry 不改写。旧文件可以被原备份流程复制，但不读取为当前来源。
- `residential_classifier.py` 去除 Fang 样本参与 classify/classify_sources/classify_directory 的逻辑与 CLI --fang-samples；保留 TMSF 分类、共用常量和普通住宅名称归一化的必要语义。`scripts/filter_residential_communities.py` 同步更新。
- auto_review 不以 Fang 为新增用途证据；Fang 历史成员不得自动合并、准入或成为住宅来源，保留只读审计。手动 admission payload、rejected/ignored、skip、删除与人工锁不变，不在启动时批量重审旧决定。
- `CommunityRegistry` 通用 associate/create 等写入口显式拒绝 source=fang（ValueError→既有 409）；不能通过通用目录 API 绕过租金入口。读取、历史事件和显式 unlink/ignore 继续可用。合并唯一性只检查当前幸福里来源，历史 Fang 不阻塞当前合并。
- 历史迁移报告中的 preserved_rental_sources、目录 source 过滤、历史用途标签可以保留 Fang 身份；明确历史计数，不将其当当前覆盖数。已有迁移 marker 不修改，不自动调用迁移。

### 5. 删除与保留清单

删除：`src/services/fang_rentals.py`、`fang_detail_cache.py`、`fang_request_policy.py`、`scripts/fetch_fang_rentals.py`、`scripts/FANG_RENTALS.md`，以及已失效的专属测试。旧采集 spec 改为退役说明并移出必读索引，避免留下可执行旧命令。

保留：数据文件、历史关联/快照、人工决定、任务归档、journal、最小 410 路由、只读历史标签和必要的来源隔离测试。Dockerfile 删除旧 rental_community_mappings seed COPY；仓库数据文件暂不删除。其他 seed 和行情/法拍/定位能力不变，不按字符串匹配批量删除文件或依赖。

现行规范更新范围：backend housing-map index、rental-sources、xingfuli-rentals、xingfuli-discovery、community-directory、community-auto-review、directory-flow 中与退役冲突的段落，以及 guides/housing-map-rental-reference、housing-map-fang-rentals。当前 directory-flow.md 有其他未提交工作，必须保留，实施时只合并相关段落。

## 失败、兼容与回滚

无 registry：来源管理 503，租金查询按现有无映射状态，采集无来源可启动；旧库不再作为运行依赖。损坏历史 Fang 文件不应阻断新服务，损坏权威 registry 仍报错，禁止伪装为空。

取消后不发布，任务重启后保留现有 interrupted/恢复语义；历史已结束 Fang job 可作历史状态显示，但继续操作不得复活 Fang 计划。缓存版本如因结构变化需失效，只失效派生缓存，不清审核决定。

实施只改代码与文档，数据库 schema 不变。回滚代码可恢复旧版本读取能力；不需要恢复数据库，也不把恢复 Fang 采集当正常退役后的入口。未来部署需单独执行；如部署时有在途任务，应等待结束或正常取消再换版本，本任务不替用户操作。

## 验证矩阵

| 场景 | 预期 |
|---|---|
| Fang/Xingfuli 相同 sid；快照缺 provider | 仅显式幸福里快照命中，禁止跨来源复用 |
| 旧内部 cid，但同幸福里 provider+sid | 保持合法复用，解除/重绑后立即失效 |
| 已关联两种来源，解除幸福里 | 无当前 mapping，不回退 Fang |
| 只有旧 Fang JSON/SQLite，含损坏文件 | 不请求、不导入、不创建映射库，不阻断正常目录初始化 |
| 目录未初始化/权威库损坏 | 明确无来源/503，旧权威库错误不静默吞掉 |
| Fang 历史样本证明住宅或冲突 | 不参与新用途判断；已保存人工决定不变 |
| 通用目录 API 尝试关联 Fang | 409 且库记录不变；历史读取与人工解绑仍可用 |
| 幸福里 full/incremental、探查确认、10套抽样、限流、取消/重启 | 保持当前协议与实际行为，无 Fang 请求 |
| 410 旧入口、GET 来源、DELETE 幸福里来源 | 无副作用退役、当前页面照常工作、互斥仍 409 |
| 发布失败、无效 preserved_sources | current 指针不变、旧快照原子性保持 |

测试全部用脱网 fixture 和隔离目录。浏览器以 390px/1440px 检查来源弹窗、未关联状态、解除、维护列表与历史标签。真实公网、生产数据和部署不属于本轮验收。
