# 单小区轮廓生成与确认设计

## 状态与决策

任务处于 planning。本文件是待评审技术方案，不代表已经实现。

已确认：所有能打开地图的人都可生成、应用和撤销，不添加登录、口令或用户系统。所有操作共同维护同一份地图数据。

推荐首版采用主地图预览与专用确认面板：小弹框内嵌地图不利于判断周边范围；独立批量审核页面会打断单地块操作。首版每个小区每次提供一个候选，不做多算法方案选择或拖点编辑。

## 已有代码与必须处理的差异

| 证据 | 对方案的影响 |
|---|---|
| BinjiangMap.tsx 占位 Polygon 已触发 onCommunityClick，徽标仅用于展示 | 沿用小区详情入口；保证徽标处的点击也实际命中入口 |
| page.tsx 内 CommunityPopup 展示价格与配套 | 加轮廓摘要与入口；进入预览时切换成独立面板，避免双弹层 |
| estimate_boundaries.py 支持快照、Overpass 缓存、建筑选择和合并 | 提取纯估算能力供 CLI 与后台调用，不能启动整批脚本再解析 stdout |
| 脚本直接读取 polygons JSON，而 load_polygons 兼容顶层与 polygons 包装两种结构 | 缺口判断统一复用标准加载，避免把包装键当小区 ID |
| 地图有轮廓但 source=shp 时不展示 | 缺口定义为“无可展示轮廓”，不是“无文件条目”；服务端与前端对齐 |
| build_merged_polygons.main 整体重写基础轮廓文件 | 人工确认结果应独立保存，查询时覆盖基础轮廓，避免重建吞掉人工结果 |
| boundary_import.merge_boundaries 仅有进程内锁，meta.update 可覆盖结构字段 | 新流程不接受浏览器直接提交 rings/meta；共用校验时结构字段必须由服务端控制 |
| 生产 nginx /api/map/* 直转后端 /api/*，Next 只做开发代理 | 不新增 BFF，不通过前端服务器注入管理 token |
| compose 当前未传 HOUSING_ADMIN_TOKEN，旧导入需此环境变量 | 新流程独立公开接口；旧导入保持原行为，不依赖其鉴权来完成确认 |
| Docker 当前启动单个 uvicorn worker | 首版单执行器配持久任务；不引入 Redis/Celery |

## 用户流程

1. 点击问号地块，现有详情展示“暂无地块轮廓”“生成候选轮廓”。正常看价格不启动任务。
2. 主动生成后返回任务 ID。显示实际阶段：等待处理、读取建筑、联网获取（仅需要时）、估算轮廓。没有可靠总时长时不显示假百分比。
3. 同一小区再次打开恢复任务或候选。弹框关闭不会取消；离开页面停止前端轮询，不取消服务端任务。
4. 成功后提供“查看候选”。点击进入主地图预览：自动定位到候选范围，确认面板取代普通详情；可以缩放平移。主地图临时突出候选并弱化该小区占位，其他地块仍可辨认。
5. 预览显示候选、定位点、周边正式轮廓，以及可切换的实际参考建筑。展示面积、参考面数量、数据来源/时间与 low_confidence 对应文字，不把住宅用地面数量一律称作楼栋数。
6. “应用此轮廓”明确保存；“范围不合适”将该候选拒绝并退出；关闭预览仅退出、不拒绝。已有低置信候选仍允许人工判断，但几何硬校验失败时禁用应用。
7. 成功应用后重新读取 communities 和当前小区状态，地图按价格配色，详情显示建筑估算与确认时间。保存成功但刷新失败时显示“已保存，地图刷新失败”，不误报保存失败。
8. 当前有效人工轮廓提供“撤销本次应用”。撤销移除本次人工覆盖，恢复应用前基础状态；基础数据已变化则提示冲突，需重新核对后以新 revision 显式撤销。
9. 范围不合适时提供“去核对定位”，跳转现有收录管理定位操作；不在本任务新增地图拖点。定位修改后候选过期，重新生成。重新生成默认复用原始建筑缓存并重新计算；“重新获取建筑”才跳过缓存。

桌面使用侧边确认面板，窄屏使用不遮满地图的底部面板。切换小区或页签移除临时图层，异步返回不得把旧小区候选叠到新小区。WebGL 底图退化时仍展示同一候选数据，不将样式差异视为轮廓缺失。

## 数据与持久化

新增 DATA_DIR/boundary_workflow.sqlite3，复用项目 sqlite3 存储习惯；不修改小区注册库身份及收录规则。连接忙等待、事务和启动初始化采用现有项目模式。

逻辑表：

- jobs：job_id、community_id、输入指纹、phase、error_code/message、创建/更新时间。
- candidates：candidate_id、job_id、坐标/名称/算法版本输入指纹、生成时基础/有效轮廓 revision、GCJ02 rings、实际参考建筑、面积、来源/快照时间、质量提示、状态。
- overrides：community_id 唯一、candidate_id、rings、source=osm-building、确认时间、递增 revision。
- operations：operation_id、community_id、apply/revert、对应 candidate、前后 revision、时间、用于幂等响应的结果。公开操作不虚构用户身份。

候选、任务完成状态同事务保存；应用/撤销、候选状态和操作记录同事务提交。正式地图查询使用“基础 load_polygons + overrides 覆盖”的有效视图，GET communities 仍保留现有 boundary/boundary_source 字段。摘要附带可选 boundary_meta（估算/确认时间及候选来源），完整参考建筑只通过候选接口读取。

基础文件只读适配两种已有格式；新流程不改写基础文件。后台重建仅更新基础层，人工覆盖持续优先；撤销回到基础层。原始 CLI 的正式导入保持原用途，不迁移历史数据。CLI 的默认缺口筛选改为使用有效视图，以免重新估算已确认项。

revision 对当前小区的基础条目、覆盖条目及有效定位/名称计算，不使用全文件哈希，避免无关小区修改引起冲突。候选应用前必须匹配候选 revision；定位或收录变化也使候选过期。确认结果不会因定位修改被静默删除，但详情标记“定位已变更，请核对轮廓”，撤销仍需新 revision。

所有服务内基础轮廓写入口（旧导入与重建发布）、新应用/撤销共用短时发布锁；联网和几何计算不持锁。事务内重新读取基础状态并比较 revision，再发布。重建先在锁外计算，锁内原子替换文件；手工离线脚本写基础数据必须停服务。首版明确单实例、单 worker；多实例调度不在范围内。

## 后台生成

服务层提供 estimate_one(target, source, progress, fetcher)，共享 select_buildings/build_boundary 等纯算法；CLI 保留现有参数与预览导出，API 不调用 CLI 的批量 main。

- 原始输入只接受 cid，由服务端读取当前可展示小区的名称及 GCJ02 坐标。shp 等隐藏轮廓作为合法待补对象。
- 单个执行器按 FIFO 串行运行，最多 20 个等待任务；同 cid 同输入在 queued/running 时返回同一 job。已有可用候选默认返回候选，显式 regenerate 才新建；新候选替换前旧候选可查看但不得并行应用。
- 优先坐标范围匹配的 7 天缓存，其次有明确覆盖范围的本地快照；快照缺失、不覆盖或无法生成时在线补查。滨江快照不可当成萧山已覆盖的证明。
- 缓存键包含实际查询 bbox 与查询版本，不能只按 cid 命名；旧 cid 缓存仅在可证明坐标一致时复用。
- 在线沿用固定 Overpass 镜像，服务内请求起始间隔至少 10 秒；每次请求上限 60 秒、每任务总预算 240 秒，预算内按固定镜像顺序尝试，限流不立即重复请求。
- WGS84 建筑输入、GCJ02 地图输出；实际参与选择的建筑转换为 GCJ02 供预览。多簇取最大外环的现有行为必须给出舍弃分簇提示，避免用户误以为完整覆盖。
- 失败保留错误类别，区分 timeout/rate_limited/no_geometry/invalid_geometry/interrupted/stale。没有建筑不捏造矩形作为“生成结果”。
- 启动恢复时 queued/running 标记 interrupted，不自动重新向外网发送请求；已有 ready 候选/应用结果保留。前端每 2 秒轮询活动任务，终态停止。

## API 契约

外部前缀 /api/map，后端 /api。新路由独立 boundary_workflow_routes，统一 success/data 信封。以下均公开，无管理凭证。

| 方法与相对路径 | 请求/响应要点 |
|---|---|
| GET /communities/{cid}/boundary-workflow | 当前有效轮廓摘要、revision、当前任务/候选摘要、当前可撤销 operation；不存在工作流库视为空状态 |
| POST /communities/{cid}/boundary-estimates | {regenerate?:boolean, refresh_buildings?:boolean}；新任务 202，复用任务/候选 200；返回 job_id/candidate_id |
| GET /boundary-estimates/{job_id} | 任务阶段及终态候选引用；跨 cid 的回包由 UI 校验 |
| GET /boundary-candidates/{candidate_id} | 预览 rings、参考建筑、来源、面积、提示、revision 和可应用状态 |
| POST /boundary-candidates/{candidate_id}/reject | {expected_revision}；仅处理当前 ready 候选，不撤销已应用结果 |
| POST /boundary-candidates/{candidate_id}/apply | {expected_revision, operation_id}；只应用服务器保存的候选，返回新 revision 与 operation_id |
| POST /communities/{cid}/boundary-reverts | {expected_revision, apply_operation_id, operation_id}；只撤销当前人工覆盖对应应用，返回有效状态 |

404 不存在或不在当前展示集合；409 输入/轮廓/候选状态冲突或队列满（附不同 code）；422 无合法坐标/非法几何；503 工作流存储不可用。旧 import 的 401/503 逻辑保持不变。状态读取也检查当前收录状态；不再收录的小区不能继续应用候选。

operation_id 由客户端一次操作生成并在网络重试中复用，服务端相同 ID/相同请求返回原结果；同 ID 不同请求 409。版本检查覆盖重复点击、双窗口应用、撤销后迟到的 apply。reject 幂等但不得把已应用候选改为 rejected。

任务状态为 queued → reading/fetching/estimating → succeeded/failed/interrupted。候选状态为 ready → applied/rejected/superseded/stale，应用后撤销改为 reverted；终态候选不能重新应用。重新生成时创建新的当前任务，并令旧 ready 候选 superseded，即使新任务失败也须生成新候选才能应用，避免旧预览误保存。GET 因定位/基础版本不匹配返回 stale 状态与原因，应用端始终独立重验；查看候选本身不重新计算。

撤销请求的 expected_revision 表示用户当前已经查看的状态，包括此时的基础层。首次应用时的旧基础层与当前基础层不同，则旧页面撤销必然冲突；用户刷新并重新查看撤销后的基础预览，再提交新 revision 后可以显式撤销。撤销只删除当前覆盖，不把历史基础 JSON 快照写回，避免覆盖后来更新的数据。

几何校验必须在生成和应用均执行：有限数值、合法 GCJ02 范围、闭环且至少 3 个不同顶点、有效且非空多边形、全部点在业务围栏、面积不超过现有 1km² 上限。仅允许服务端候选的固定结构字段，不接受浏览器 rings/source/meta。

## 范围与上线

不增加新账号体系、公开批量导入、自动应用、手工编辑或分布式队列。候选/操作持久保存，首版不加自动清理任务；记录数量与磁盘体积通过既有日志观察。

上线只新增数据卷内 SQLite 文件并增加代码，不批量生成、不修改线上轮廓。发布前只读核对当前缺口与快照；应用与撤销验证使用隔离数据。回退前备份 SQLite，旧版本只读基础层会暂时看不到新增人工覆盖，因此需恢复本功能版本才重新展示；基础数据始终保留。

## 评审状态

权限已由用户明确选择公开操作。其余方案已形成可评审草案，特别是独立人工覆盖层、任务中断重试、缓存刷新与撤销冲突规则，待用户整体确认后进入实现。
