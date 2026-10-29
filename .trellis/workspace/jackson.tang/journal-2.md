# Journal - jackson.tang (Part 2)

> Continuation from `journal-1.md` (archived at ~2000 lines)
> Started: 2026-10-28

---



## Session 52: 归档地图数据补齐父任务

**Date**: 2026-10-28
**Task**: 归档地图数据补齐父任务
**Package**: backend/douyin-processor
**Branch**: `master`

### Summary

归档 10-16-map-data-backfill 父任务（按方案演进）：两个子任务已各自归档，但原跨子验收「线上出现 12 个 osm-building 轮廓」未达成——2026-10-28 核对线上为 160 展示小区、135 osm 轮廓、25 无轮廓且无任何 osm-building；交互式方案已由 10-28 接手实现，剩余线上补齐随其部署窗口处理。

### Main Changes

### Main Changes

- 归档 `10-16-map-data-backfill`（父任务），按方案演进归档。两个子任务 boundary-estimate-script（ef61c7d，cb5d871 重构为脚本与后台共用 boundary_estimate）与 boundary-upload-api（ffdef53，写入锁改用共享 boundary_publish 发布锁）已先各自归档。
- 父任务原跨子验收第 2 条「端到端 → 线上地图出现 12 个 osm-building 轮廓」**未达成**，已在 prd.md 与 task.json notes 中如实记录：2026-10-28 只读核对线上 /api/map/communities 为 160 个展示小区、135 个 osm 轮廓、25 个无轮廓，来源分布无任何 osm-building，即脚本 --apply 从未在生产执行；缺口已从 10-16 摸底的 12 扩到 25（期间新增 local-* 前缀新房/在建小区），原「补齐 12 个」目标本身已过期。
- 交互式生成/预览/确认应用/撤销已由 `10-28-housing-boundary-preview` 接手并实现（cb5d871，SQLite 覆盖层分层：基础层 + 人工确认覆盖层，后台重建不吞人工结果，撤销只删覆盖层），本父任务的脚本 + 上传接口方案在生产补轮廓上已被其取代，剩余线上补齐随 10-28 部署窗口处理。
- 本地 estimate_out 实跑记录：12 个无轮廓小区产出 11 个候选，朗庭(1024) 无建筑可聚类、兴耀鑫都汇(167483594) 仅 1 栋低置信，均未上传。探测线上用的临时 json 已删除，未改任何生产数据。

### Testing

- 本轮未新增代码改动，沿用已归档子任务的验证结果：后端全量 968 passed、前端 130 项/tsc/lint/build 通过。

### Status

[OK] **Completed** — 父任务按方案演进归档；线上补齐未完成的部分移交 10-28。

### Next Steps

- `10-28-housing-boundary-preview` 实现完成（cb5d871），遗留浏览器端手工 QA 与线上部署待授权；部署后可用其交互入口为线上 25 个无轮廓小区逐个生成并确认轮廓。
- `10-12-community-price-transactions` 仍在 planning，未动代码。
- `00-bootstrap-guidelines` 按 notes 保留进行中。


### Git Commits

| Hash | Message |
|------|---------|
| `ef61c7d` | (see git log) |
| `ffdef53` | (see git log) |
| `cb5d871` | (see git log) |

### Testing

- Validation was not recorded for this session.

### Status

[OK] **Completed**

### Next Steps

- None - task complete

---

## Session 53: 完成已收录小区多选合并

**Date**: 2026-10-28
**Task**: 已收录小区多选合并（10-28-community-merge-ui）
**Package**: apps/housing-map
**Branch**: `master`

### Summary

接手上一会话遗留的合并 UI 实现（代码已写、未提交、未验证），完成文案修正、隔离环境端到端验证、
提交与归档。线上水晶城 3 条重复记录由用户自行在页面合并，未触碰生产数据。

### Main Changes

- **修正合并预览文案（b19051e）**：后端 `_merge` 只补 `address/district/longitude/latitude/coordinate_system`
  这些 payload 字段，**不迁移 `amap_position`**（高德 POI 匹配结果）。原预览写"保留方缺失，将补入被并方定位坐标"
  与实际不符，改为按 `has_coordinates` 表述并加一行"高德 POI 匹配结果不随合并迁移"提示；
  另修 "无法拍记录" 语病为 "暂无拍卖记录"。
- **前端实现**（上一会话产出，本次提交）：`MergeDialog.tsx`（保留方单选 + 预览 + 逐条提交）、
  `DirectoryFlowWorkspace.tsx`（admitted 模式选择列、批量条、翻页/筛选清空选择）、
  `globals.css`（`.catalog-selectable.catalog-admitted` 8 列列宽、窄屏隐藏选择列）。
- **隔离验证环境**（`.tmp-merge-verify/`，验证后已删除）：`HOUSING_DATA_DIR` 指向副本 data 目录的后端 +
  `HOUSING_API_ORIGIN` 指向该后端的前端副本，造 5 条假小区（甲有坐标/new_house、乙无坐标、丙无坐标2来源、
  租甲/租乙各有 fang matched 来源）。
- **spec 新增** `guides/housing-map-merge.md`：合并语义表、admitted 硬门槛与"本地库已收录列表为空"的原因、
  隔离验证环境做法（Next dev 跨域保护、造数唯一约束、进程残留导致目录删不掉）、选择列列宽约定。

### Testing

- `pnpm lint` / `pnpm build` 通过（apps/housing-map）。
- 浏览器端到端（隔离环境，端口 3010/8099）：预选规则（有坐标优先于来源多）、混合市场状态警告与按钮文案、
  逐条失败（"两个小区都有租金来源"原样透出，失败项仍在列表）、成功合并（5→3 条、保留方别名含被并方名称与别名）、
  宽屏列宽 4/24/10/16/12/10/14/10、不收录 Tab 0 checkbox、窄屏 502px 卡片态不塌无横向溢出。
- 开发库与生产库数据未改动（主库 meta 与 admission 行核对一致）。

### Status

[OK] **Completed** — 任务归档至 `.trellis/tasks/archive/2026-10/10-28-community-merge-ui`。

### Next Steps

- 线上水晶城水晶澜轩 / 钱江水晶城 / 钱江水晶澜轩 三条由用户在「已收录」页自行合并（实施者不碰生产数据）。
- `10-12-community-price-transactions` 仍在 planning，未动代码。

### Git Commits

| Hash | Message |
|------|---------|
| `b19051e` | feat(housing-map): 已收录小区多选合并 |
| `5d0878d` | docs: 记录小区合并契约与隔离验证环境做法 |
| `003809e` | chore: 归档已收录小区多选合并任务 |


## Session 53: 补齐楼盘地点与类型全量更新

**Date**: 2026-10-29
**Task**: 补齐楼盘地点与类型全量更新
**Package**: housing-map
**Branch**: `master`

### Summary

新增更新全部/继续匹配/重试失败三个入口；refresh_all重新查询自动结果并保护人工决定，旧all保持补缺兼容。后端1093和前端169测试通过，lint/tsc/build通过，1440/390静态预览无溢出。用户已授权提交并推送，未部署。

### Main Changes

- Detailed change bullets were not supplied; see the summary above.

### Git Commits

随本次 housing-map 功能提交。

### Testing

- 后端1093与前端169测试通过；lint、类型检查和生产构建通过；1440/390静态预览无溢出。

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 54: 评级任务连续排队与队列实时展示

**Date**: 2026-10-29
**Task**: 评级任务连续排队与队列实时展示
**Package**: backend/douyin-processor
**Branch**: `master`

### Summary

废止评级 400 拒绝旧契约，改为运行中受理追加（append_codes 持久化、FIFO 派发、收尾窗口互斥）。前端单一轮询生命周期 + 队列面板（分区展示、每秒计时、逐股禁用）。后端 298、单测 13、e2e 18 全过；审查修复 _run_one 异常兜底防队列挂起（HIGH）。

### Main Changes

- Detailed change bullets were not supplied; see the summary above.

### Git Commits

| Hash | Message |
|------|---------|
| `ec68ff0` | (see git log) |
| `7e4262b` | (see git log) |

### Testing

- Validation was not recorded for this session.

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 55: 租金两个按钮收进同一区块并收尾任务

**Date**: 2026-10-29
**Task**: 租金两个按钮收进同一区块并收尾任务
**Package**: backend/housing-map
**Branch**: `master`

### Summary

housing-map：采集任务弹窗里「匹配租金来源」与「更新租金数据」收进同一「租金流程」区块（.directory-task-group），桌面与 390px 实测无溢出；前端 171 项测试、tsc、lint 通过。10-29-housing-rental-source-unification 归档，未完成项（R1 剩余验收、R2 通道级断点、R3 独立迁移工具、R4 全量上线）转入新任务 10-29-housing-rental-source-followup。

### Main Changes

- Detailed change bullets were not supplied; see the summary above.

### Git Commits

| Hash | Message |
|------|---------|
| `2f18938` | (see git log) |
| `98e3ddc` | (see git log) |

### Testing

- Validation was not recorded for this session.

### Status

[OK] **Completed**

### Next Steps

- None - task complete
