# 任务1验证记录 · 2026-10-14

## 交付
住宅准入独立状态、人工撤销/排除/恢复/明确解锁、版本冲突检查与审计、旧目录幂等初始化、地图和评分共用有效住宅投影、现有管理页的最小操作入口。新来源建立主档保持待审；未启用新小区自动收录，未实施任务2列表聚合。

## 实际检查
- 先运行新增状态测试得到4个缺少 admission/decide_admission 的预期失败，实现后通过；新增API测试先因缺少map_status失败，再完成接口和地图接入。前端新操作组件测试先因组件未实现失败，再实现通过。当前类型更新测试先得到住宅≠别墅失败，修正非人工类型投影后通过。
- 后端最终全量：`.venv\Scripts\python.exe -m pytest --basetemp=.pytest-tmp-housing-residential-admission-final -q`，**393 passed**，23.06秒，退出0。
- 警告：2条既有Starlette/httpx/anyio弃用提示；既有TMSF CLI测试子进程stderr使用GBK解码出现线程警告。未修改与本任务无关的测试或依赖。初次全量391通过；中间一次沙箱内重跑停顿后中止，最终沙箱外全量393通过。
- 前端 `npm run lint`、`npx tsc --noEmit` 均退出0；`node --test tests/*.test.cjs` **44 passed**，退出0。
- 默认Turbopack构建被沙箱子进程限制中断；沙箱内webpack又遇EPERM。自动审批后执行 `npm run build -- --webpack`，编译、TypeScript、静态页面、构建追踪均成功，退出0。未更改正式构建配置。
- `git diff --check` 通过。task.py validate（实施/check清单）通过。

## 隔离浏览器
Playwright Chrome访问本地13007前端与8096后端。后端仅使用 `.pytest-tmp-housing-admission-browser`，未启动定时采集。
- 桌面：江汉路小区→移到待审核→排除→恢复待审核→确认排屋，UI动作与地图API同时验收。
- 地图记录数量：1→0→0→0→1；人工类型排屋正确传到地图。
- 手机390×844：人工再次撤销，地图0条，自动审核锁提示与操作可见可点击；已查看手机截图。
- 整个流程关联来源保持matched，不调用whole-community delete。最终页面console无错误，1条高德Canvas性能提示。最初QA后端漏挂租金来源路由曾404，补齐QA路由并重新载入后流程成功。

## 旧资料副本迁移
从本机backend/housing-map/data复制既有JSON/历史快照到 `.pytest-tmp-housing-admission-copy`；若有SQLite则用backup API复制。仅操作副本。
- 主档670、来源680、旧删除0；初始化收录450、待审120、排除100。
- 两次prepare后的主档、来源、删除集合与全部收录决定完全一致；原始JSON/价格快照文件SHA256不变。
- 合成旧SQLite测试另覆盖人工名称/别名、rejected、旧删除、local主档+TMSF来源ID，并验证重复迁移不增加事件。
- 此为本地资料副本数字，不是之前NAS在线目录398/873的实时对账；线上生产迁移未执行。

## 验收映射
- AA1：撤销后重采集/重启保锁测试；桌面/手机地图变空。
- AA2：排除/恢复保锁/人工确认；来源、资产轮次不变且新轮次不解除锁。
- AA3：共享map_status、缺/坏坐标、有效类型、静态合并组与范围保护；管理住宅集合允许缺坐标。
- AA4：BEGIN IMMEDIATE中版本检查和事件写入；409无状态改变；来源新建保持原子且新主档待审。
- AA5：现有SQLite和本地数据副本重复迁移；local-only不进入TMSF采集目标；历史身份加载与价格/租金/法拍回归通过。

## 后续边界
实现已通过本地质量门。未提交Git、未部署、未迁移NAS数据；Trellis状态保持in_progress以等待提交/归档。任务2可基于本记录和community-admission.md契约规划的接口继续，仍需用户明确开始。任务3必须使用admission_state和auto_review_locked，不能直接用source状态自动收录。
