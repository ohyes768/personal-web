# 实施计划

状态implementing。已按本计划改代码；未改 spec，未提交。task.json 在进入实现时已是 in_progress，本轮没有再跑 task.py start。

## 顺序与验收映射

0. [x] 用户要求实现后运行task.py start，加载trellis-before-dev、TDD及相关spec，核查工作区。
1. [x] 从仓库快照建立两处bbox合并fixture（目标way 614214443、邻区way 113467424），先写可检出坐标与别名错误的失败测试。（A1–A3）
2. [x] 提取公共坐标实现，保留服务和直接脚本兼容入口；增加独立固定控制值测试。（A1）
3. [x] 后台/CLI传递aliases，定义受约束名称规则与规范输入指纹。（A2、A4）
4. [x] 实现可信住宅面优先、建筑回退、邻区冲突及歧义提示；覆盖仅住宅面场景。（A2–A3）
5. [x] 加算法版本；修复ready复用、GET stale、apply重验、任务起始及发布前一致性；验证旧库兼容和覆盖撤销。（A4–A5）
6. [x] 按需调整预览来源/面类型文案，沿用现有tab和API。（A6）
7. [x] 隔离端到端与全量质量门；钱塘大观离线前后预览已记录。桌面/窄屏实机对照未完成：当前地图展示集为空。（A5–A7）
8. [ ] 更新boundary-workflow spec的坐标、匹配、指纹及历史兼容契约；记录结果，按Trellis结束流程收尾。提交需用户授权。

## 影响文件

- backend/housing-map/src/services/boundary_estimate.py、boundary_workflow.py。
- backend/housing-map/src/core/coordinates.py（建议新增）。
- backend/housing-map/scripts/estimate_boundaries.py、convert_osm_residential.py、convert_osm_transit.py。
- backend/housing-map/tests/test_boundary_estimate.py、test_boundary_workflow.py、新坐标测试与fixture。
- apps/housing-map/src/components/community/BoundaryWorkflowPanel.tsx及关联测试（按需）。

## 验证

从backend/housing-map执行，新增坐标测试也加入相关测试命令：

```powershell
./.venv/Scripts/python.exe -m pytest tests/test_boundary_estimate.py tests/test_boundary_workflow.py tests/test_boundary.py tests/test_boundary_import.py tests/test_boundary_refresh.py -q --basetemp=.pytest-tmp-boundary-accuracy-targeted
./.venv/Scripts/python.exe -m pytest -q --basetemp=.pytest-tmp-boundary-accuracy-full
```

从apps/housing-map执行（涉及前端修改时）：

```powershell
npm run lint
npx tsc --noEmit
node --test tests/*.test.cjs
npm run build
```

先运行失败回归再实现，全量在变更稳定后跑；无新变化/失败不重复扩大测试。所有测试和端到端使用项目盘独立临时目录，隔离DATA_DIR/SQLite，不联网、不接生产apply。核对桌面/窄屏定位、边界、参考面、来源、应用/刷新/撤销。临时运行产物不提交。

## 风险门

- 同源正反公式假通过：独立固定控制值把关。
- 名称过宽吞邻区：远处同名、异名区域、多匹配冲突用例把关。
- 旧候选绕过修复：复用、读取、应用、任务发布四处统一指纹检查。
- 算法版本锁死历史撤销：隔离旧库证明覆盖不变且可撤销。
- OSM非实地测绘：保留人工确认，不强制规则化、不自动替换历史结果。

本次任务是同一故障链的整体修复，无需拆分子任务。启动前检查PRD、design与本计划已审阅，避免直接进入实现。

## 验证记录（2026-10-28）

离线样本 20000561（钱塘大观 / 观邸国际寓所，GCJ02 120.133258, 30.181901）。正确反算 WGS84 为 (120.12850226078159, 30.1841956361507)。使用仓库快照抽出的两处查询框 fixture，没有联网、没有写生产库。

修复前（研究记录里的错误坐标 + 主名）：选中贺田尚城一带 49 个建筑面，约 8.33 公顷。修复后（主名 + 别名）：选中住宅面 way 614214443（观邸国际）；候选面积 10.53 公顷；与转换后的该住宅面面积差 0、IoU 1.0；定位点落在候选内。参考成员是这 1 个住宅面加面内 10 个建筑，不含 way 113467424。

局限：这次只证明候选贴住了 OSM 住宅用地面，没有对照实地围墙或产权界址。OSM 面不是测绘边界，也不是产权边界，仍要先预览再人工应用。来源文案和面类型由组件测试覆盖。spec 更新留到下一步。

页面核对（同日稍后）：本地 8096 与 3007 已重新拉起。打开 http://localhost:3007/map ，搜索「钱塘大观」，地图收录/展示为 0。`GET /api/communities` 同样是空列表。`community_views` 把 20000561 标成 excluded，原因是「实际地址资料缺失或待核实，暂不收录」。这是收录资格口径，不是这次轮廓算法的结果。因此没有在页面上生成或应用候选，也没有做桌面/窄屏对照。注册库 `data/community_registry.sqlite3` 的修改时间是 13:57，早于本次实现。

质量门：

- `backend/housing-map`：`./.venv/Scripts/python.exe -m pytest tests/test_boundary_estimate.py tests/test_boundary_workflow.py tests/test_boundary.py tests/test_boundary_import.py tests/test_boundary_refresh.py tests/test_coordinates.py -q --basetemp=.pytest-tmp-boundary-accuracy-targeted` → 92 passed
- 同目录全量：`./.venv/Scripts/python.exe -m pytest -q --basetemp=.pytest-tmp-boundary-accuracy-full` → 1010 passed
- `apps/housing-map`：`npm run lint`、`npx tsc --noEmit`、`node --test tests/*.test.cjs`（137 pass）、`npm run build` 均通过
