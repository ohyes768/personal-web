# Housing-Map 轮廓生成工作流契约

> 来源：10-28-housing-boundary-preview 任务。适用所有改"缺失地块轮廓生成/预览/确认应用/撤销"的代码。
> 与旧的批量导入接口（`/api/boundaries/import`，带 `HOUSING_ADMIN_TOKEN`）是两套东西，行为互不影响。

## 1. 两层数据模型

| 层 | 位置 | 谁能写 | 说明 |
|---|---|---|---|
| 基础层 | `data/binjiang_polygons_merged.json` | 旧批量导入、后台重建脚本 | OSM 住宅面匹配结果，**整体重写** |
| 覆盖层 | `data/boundary_workflow.sqlite3` 的 `overrides` 表 | 本工作流的应用/撤销 | 人工确认的估算轮廓，**独立存放** |

地图查询用"基础 + 覆盖"的有效视图（`boundary_workflow.effective_polygons()`）。
因此：后台重建基础层不会吞掉人工确认结果；撤销只删覆盖层，不把历史基础快照写回。

**缺口判定只有一处定义**：`boundary_workflow.is_displayable(entry)` —— 有 rings 且 `source != 'shp'`。
`routes.get_communities()` 的 `missing_boundary` 统计、前端 `BinjiangMap` 的问号占位、
CLI 的默认缺口筛选都必须用同一口径。历史 shp 条目属"有文件但不可展示"，也算缺口。

## 2. 有效轮廓视图改了哪些接口

`GET /api/communities` 现在下发**有效视图**（基础 + 人工覆盖）：

- 人工应用后该小区下发 `boundary` + `boundary_source='osm-building'`，问号占位消失。
- `stats.hidden.missing_boundary` 同步减少。
- `boundary_confirmed_at` / `boundary_meta` 等摘要字段可从 `GET /communities/{cid}/boundary-workflow` 取，
  `/communities` 保持既有 `boundary` / `boundary_source` 字段不变。

## 3. API 契约（全部公开，无登录无口令）

外部前缀 `/api/map`，后端 `/api`。浏览器**只提交 ID 与版本号，不提交任何几何**。

| 方法与相对路径 | 请求 | 响应要点 |
|---|---|---|
| `GET /communities/{cid}/boundary-workflow` | - | 有效轮廓摘要、revision、当前任务/候选、可撤销 operation |
| `POST /communities/{cid}/boundary-estimates` | `{regenerate?, refresh_buildings?}` | 新任务 **202**，复用任务/候选 **200**；返回 `job_id` / `candidate_id` |
| `GET /boundary-estimates/{job_id}` | - | 阶段 `phase` 与错误分类 |
| `GET /boundary-candidates/{candidate_id}` | - | 预览 rings、参考建筑、面积、提示、revision、可应用状态 |
| `POST /boundary-candidates/{candidate_id}/reject` | `{expected_revision}` | 幂等；不撤销已应用结果 |
| `POST /boundary-candidates/{candidate_id}/apply` | `{expected_revision, operation_id}` | 只应用服务端保存的候选 |
| `POST /communities/{cid}/boundary-reverts` | `{expected_revision, apply_operation_id, operation_id}` | 只撤销当前覆盖层 |

错误：`404` 不存在/不在展示集合、`409` 版本或候选状态冲突、队列满（`queue_full`）、
`422` 非法几何、`503` 工作流存储不可用。错误体为 `{"detail": {"code", "message"}}`。

`operation_id` 由客户端生成并在网络重试中复用：同 ID 同请求返回原结果，同 ID 不同请求 409。

## 4. 状态机

```
job:    queued → reading/fetching/estimating → succeeded | failed | interrupted
cand:   ready → applied | rejected | superseded | stale | reverted
```

- 重启时 `queued`/在途任务一律标 `interrupted`，**不自动重新向外网发请求**；前端提示可手动重试。
- 重新生成会把旧的 ready 候选置 `superseded`；旧候选即使新任务失败也不能再应用。
- 应用覆盖已有覆盖层时，旧的已应用候选置 `superseded`。

## 5. 版本判定（revision）

revision = `digest(基础条目 + 覆盖条目 + 有效定位/名称)`，**不用全文件哈希**，
无关小区改动不引起冲突。候选记录生成时的 `base_revision`，应用时若与当前基础层不符 →
`409 candidate_stale`；`expected_revision` 与当前有效层不符 → `409 revision_conflict`。

撤销的 `expected_revision` 表示用户当前已查看的状态：刷新后用新 revision 可显式撤销；
基础数据已变化则冲突，需重新核对。撤销不写回历史基础 JSON。

## 6. 几何校验（生成与应用两端都跑）

`boundary_geometry.validate_rings(rings)`：有限数值 → 坐标范围 → 环闭合且 ≥3 个不同顶点 →
有效非空多边形 → 全部点落在滨江/萧山接壤围栏 → 面积 ≤ 1 km²。
只允许服务端候选的固定结构字段，浏览器提交的 rings/meta 一律不接受。

## 7. 发布锁

`boundary_publish.publish_lock()`：基础层写入口（旧导入 `merge_boundaries`、后台重建
`build_merged_polygons`）与人工覆盖的版本判定共用。**联网与几何计算不持锁**，
锁只覆盖"读基础层 → 比对 → 写"的短窗口。重建先在锁外计算，锁内原子替换文件。

## 8. 生成来源与限流

- 数据源顺序：坐标匹配的本地快照 → 在线 Overpass。**快照文件存在不等于该区域已采集**：
  快照必须覆盖请求 bbox，否则照样走在线（`boundary_estimate.load_snapshot` 返回 `(elements, covered)`）。
- **全量建筑快照 `data/binjiang_osm_buildings_all_raw.json` 随仓库分发**（.gitignore 里专门开了例外），
  Dockerfile 把它复制进 `seed-data`，容器启动时落到数据卷。原因：**NAS 连不上 Overpass**
  （三个镜像实测 502 / 读超时），这份数据在那边无法重建，只能随代码走。
  改这条链路时要同时看三处：`.gitignore` 例外、Dockerfile 的 `COPY ... ./seed-data/`、CMD 的补齐拷贝。
  `test_dockerfile.py` 里有断言守着这条链。
- 缓存键含查询 bbox 与查询版本（`cache_key`），不能只按小区 ID；缓存放 `data/boundary_cache/`。
- 服务内请求起始间隔 ≥10s、单次 60s、**单任务总预算 240s（已强制）**：预算耗尽即放弃剩余镜像，
  单次请求超时还会被剩余预算压住。预算用 `budget_seconds` 参数注入，测试用假时钟验证。
- `refresh_buildings=True`（"重新获取建筑"）会**连本地快照一起绕开**，强制走在线；
  普通"重新生成"复用快照与缓存。在离线环境（NAS）这个操作必然失败，界面会显示网络错误。

## 9. 估算算法唯一实现处

`src/services/boundary_estimate.py` 是唯一算法实现处，CLI（`scripts/estimate_boundaries.py`）
与后台工作流共用。改动估算参数/算法时两边同时生效，**不要在脚本里另写一份**。

估算质量口径（前端展示用）：
- 参考面区分**建筑面**与**住宅用地面**，不一律叫"楼栋数"。
- 低置信（定位点未落在任何建筑簇内）只作提示，不伪装成准确率。
- 多簇时只取最大外环，必须给出"附近还有 N 个未纳入簇"的提示。
- 没有建筑就报 `no_geometry`，**不捏造矩形**当结果。

## 10. 前端契约

- `apps/housing-map/src/lib/boundary-workflow.ts`：类型 + 请求封装 + 展示层纯函数（可测）。
- `apps/housing-map/src/lib/use-boundary-workflow.ts`：状态与轮询（活动任务 2s 一次，终态停）。
  数据按小区 ID 存档，渲染时只取当前小区快照 —— 切小区后迟到响应不会叠加旧候选。
- **轮廓操作在小区详情弹框的第三个 tab「地块轮廓」里**，与「小区概况」「租金与收益」平级
  （`CommunityDetailTabs` 的 `boundary` 插槽，有内容才渲染这个 tab）。
  不要把轮廓内容再塞回概况页正文 —— 那是最初的写法，挤在价格评分中间，越加越乱。
  `BoundaryWorkflowPanel.tsx` 拆成两个 tab 内容组件：`BoundaryWorkflowSection`（状态 + 入口）、
  `BoundaryWorkflowPreview`（候选确认，就地展开，不另起抽屉）。
- `BinjiangMap` 的 `boundaryPreview` prop 是**临时候选图层**，与正式地块图层分开管理：
  候选高亮、参考建筑可开关、被预览小区的问号占位弱化；切小区/关闭预览即移除。
- 关闭弹框停止前端轮询，服务端任务照常跑完；重新打开会恢复任务/候选。
- 保存成功但地图刷新失败要显示"已保存，地图刷新失败"，**不能报成保存失败**。
- **任务失败原因必须在弹框里露出来**（线上踩过：任务已经 failed，弹框还显示"联网获取建筑中"，
  用户干等一整轮才知道失败）。`BoundaryWorkflowSection` 要渲染 `error` / `jobError`，
  并把按钮文案从"生成候选轮廓"改成"重新生成轮廓"。
- **异步动作的 busy 标志必须无条件复位**（线上踩过：`startEstimate` 成功路径漏了复位，
  按钮永久 disabled，"查看候选"点了没反应）。统一走 `runBoundaryAction`，
  成功失败都复位；错误判断用 (message, code) 形状判断而非 `instanceof`
  （转译到 ES5 时 Error 子类的 instanceof 会失效）。

## 11. 检查定位与候选操作

不在本流程新增地图拖点。`page.tsx` 的"检查定位"切到收录管理页并把
`positionFocus` 传给 `DirectoryFlowWorkspace`，由它按小区直接打开资料弹框（定位面板在弹框内），
复用现有的 `PositionPanel`，不引入第二套定位逻辑。

候选预览直接显示“应用此轮廓”（主操作）、“检查定位”“放弃此候选”“重新生成”（次操作），不增加“更多”菜单。“放弃此候选”仍调用 reject，不调整边界或训练算法。“重新生成”复用本地数据；前端不再提供“重新获取建筑”入口，地图数据后续手动打包更新。后端 refresh_buildings 能力保持兼容，不在本次界面精简中删除。

## 12. 已知坑

- 缺口判定散落在后端统计、前端图层、CLI 三处，任何一处改了都要同步。
- `data/boundary_workflow.sqlite3` 与 `data/boundary_cache/` 是运行时产物，已 gitignore。
- `fetchCommunities()` 返回 `ok` 标志：刷新失败时不要把小区列表清空。
- Windows 上 pytest 需 `--basetemp` 指到项目盘；读 UTF-8 文件要显式 `encoding='utf-8'`（locale 是 GBK）。
