# 实施计划与完成状态

状态：2026-10-28 实现完成,规划文档已按评审意见落地。下列勾选反映**实际完成情况**,
未做的项保留未勾选并写明原因。

## 1. 固化现状与测试数据

- [x] 只读访问线上 communities,统计有定位无可展示轮廓、无定位、隐藏 shp；摘要写入
      `research/01-current-gap-and-snapshot.md`。线上 160 个展示小区中 **25 个**无可展示轮廓,已列全表。
- [x] 核对数据卷快照：快照是 gitignore 的运行时产物,**NAS 上很可能不存在**,生产默认走在线；
      本地全量快照覆盖滨江全域(30.10–30.26/120.10–120.28),旧具名快照只覆盖核心区。
- [x] 阅读 housing-map backend index、定位契约、Windows 测试环境契约与前端现有测试模式。
- [x] fixtures 覆盖两种基础 JSON 结构、隐藏 shp、多簇、空建筑、定位变化与并发版本：
      `tests/test_boundary_workflow.py` 覆盖 shp/版本冲突/队列满/重启中断/幂等,
      `tests/test_boundary_estimate.py` 覆盖快照覆盖与否两种结构。

## 2. 提取单小区估算能力

- [x] 新增 `src/services/boundary_estimate.py`；CLI 与 API 共用算法,保留 CLI 参数与输出兼容
      （`scripts/estimate_boundaries.py` 改为薄封装,旧模块名继续导出）。
- [x] 统一有效缺口判定：`boundary_workflow.is_displayable()` 是唯一口径,
      `routes.get_communities` 的 `missing_boundary` 统计、CLI 默认筛选、前端图层三处对齐。
- [x] 修复快照覆盖判定：快照文件存在但不含该点时返回 `covered=False`,转在线补查。
- [x] 坐标变更缓存键：`cache_key()` 含 bbox 与查询版本,不再只按 cid 命名。
- [x] 输出实际参考几何、GCJ02 轮廓、面积/来源/时间及质量提示（区分建筑面与住宅用地面）。
- [x] 实现可注入 fetcher/clock、全局请求节奏（≥10s）、单次 60s、单任务 240s 预算常量。
- [x] 验证离线 fixture 生成、坐标往返、分簇提示、在线故障分类、缓存命中；测试不依赖真实 Overpass。

## 3. 持久任务、候选及人工覆盖层

- [x] 新增 `boundary_workflow_store.py`（jobs/candidates/overrides/operations 同库事务）与
      `boundary_workflow.py`。
- [x] 单执行器有界队列（20）、重复合并、重启中断标记、终态持久化。
- [x] `load_polygons` 之外新增 `effective_polygons()` 合成基础+覆盖层；不改写基础 JSON。
- [x] 计算单小区输入/轮廓 revision,应用/拒绝/撤销遵循状态约束与幂等规则。
- [x] 新增共用发布锁 `boundary_publish.publish_lock()`；旧导入与重建只在最终发布时持锁。
- [x] 覆盖层在旧导入/重建之后仍保留（E2E 已验证）；撤销基础变化时返回冲突。
- [x] 检查所有基础文件写入路径：`merge_boundaries` 与 `build_merged_polygons` 均已接入发布锁。
- [x] 验证崩溃/重启、事务失败、双窗口应用、重复请求、迟到请求、定位与收录变化。

## 4. HTTP 接口与有效数据投影

- [x] 新增 `boundary_workflow_routes.py`、`main.py` 挂载,使用既有 `/api` 前缀。
- [x] 新流程路由全部公开；旧 token 导入接口及行为保留（回归测试已覆盖 401）。
- [x] 只接受 cid/候选 ID/revision/operation ID,不允许前端自带任意几何。
- [x] 生成与应用复用严格几何校验（`boundary_geometry.validate_rings`）。
- [x] `communities` 返回有效视图（基础+覆盖）,保留 boundary/boundary_source 字段。
- [x] 接口测试覆盖状态码、候选归属、失效、幂等、队列容量、无口令完整操作及旧鉴权回归。

## 5. 地图交互

- [x] 新增 `lib/boundary-workflow.ts`、`lib/use-boundary-workflow.ts` 与
      `components/community/BoundaryWorkflowPanel.tsx`,未继续在 page.tsx 内堆任务实现。
- [x] `BoundaryWorkflowSection` 只增摘要与入口；进入预览切换到 `BoundaryWorkflowPanel`。
- [x] `BinjiangMap` 接受 `boundaryPreview` props,图层与正式地块分开管理,卸载即清理。
- [x] 查看/隐藏参考建筑、候选范围定位、加载/空态/错误态、保存后刷新失败提示。
- [x] 切换小区阻止迟到响应（数据按小区 ID 存档）；活动任务轮询、关闭停止前端轮询、重开恢复。
- [x] 应用后更新列表和 selectedCommunity；撤销后恢复占位或最新基础轮廓。
- [x] 核对 PositionPanel 现有打开方式,实现去管理定位的预选小区跳转
      （`positionFocus` → `DirectoryFlowWorkspace` 按 cid 直接打开资料弹框）,未新增第二套定位逻辑。
- [ ] 浏览器端手工 QA（问号徽标本体点击、键盘焦点、窄屏地图操作）未做：
      自动化测试覆盖纯函数与面板渲染,地图层依赖高德 JS API 无测试基建,需要人工在浏览器确认。
      2026-10-29 收尾复核仍未做,如实留空。

## 6. 验证与交付

- [x] 后端新增 `tests/test_boundary_workflow.py`（22 例）,全量回归 **968 passed**。
- [x] 前端新增 `tests/boundary-workflow.test.cjs`（13 例）；`npm run lint`、`npx tsc --noEmit`、
      `node --test tests/*.test.cjs`（130 passed）、`npm run build` 全通过。
- [x] 隔离数据端到端：?→生成→关闭重开→预览→应用→刷新→撤销 **29/29 通过**,
      证据见 `research/02-e2e-transcript.txt`。
- [x] 异常路径覆盖：无建筑（`no_geometry`）、镜像失败（`network`）、低置信提示、过期定位
      （`candidate_stale`）、双窗口冲突（409）、保存成功刷新失败提示、重建后保留覆盖层。
- [x] 前后端重启后恢复 ready/已应用状态,活动任务明确中断（`interrupted`）,手动重试可继续。
- [x] 文档与 PRD 验收逐条对应；已更新 `.trellis/spec/backend/housing-map/backend/boundary-workflow.md`。
- [ ] 部署、线上正式应用、Git 推送未执行,按用户后续授权进行。
      2026-10-29 收尾回填：Git 推送已执行（cb5d871 + 44beb07 + 31ff320 + 44a4259 + e4197f4，均在 origin/master）；
      **仍未做**：NAS 重新部署后的线上离线生成验证、线上正式应用候选、浏览器手工 QA。

## 已知遗留

- 生产环境大概率没有 OSM 快照,首次生成会走在线 Overpass（单任务最长 240s）。
  前端按真实阶段展示进度,不显示假百分比。
- 线上 25 个缺口中,有 3 个（朗庭、春来晴翠园、泊玺骏庐）本地快照下无建筑,需联网补查,
  仍可能失败并报 `no_geometry`。
- 浏览器端手工 QA 未做（见第 5 节）。

## 回退

停用新 UI/新路由即可停止新操作；SQLite 文件保留并备份,基础 JSON 不需逆向迁移。
旧版本不展示覆盖层的限制需在发布说明注明。不要删除 SQLite 来执行用户撤销,撤销必须走单小区版本检查。
