# 验证与交付记录（2026-10-23）

## 已交付
已完成独立幸福里 HTTP 采集器（完整分页、实际整租详情、独立限速/冷却/取消）、每小区来源选择、共享刷新/原子发布、provider+ID 快照隔离、查询/覆盖率/安全来源链接以及默认只读的显式试点导入 CLI。没有修改生产关联、部署镜像或发起生产租金采集。

## 自动验证
- 相关后端最终结果：258 passed, 1 deselected。命令包括 test_xingfuli_rentals/pilots、test_rental_providers/api/sources/statistics/storage/refresh/association_flow、test_directory_flow 及3个 Fang 测试文件，`-k 'not test_newhouse_and_missing_position' --basetemp=.pytest-tmp-xingfuli-reviewed`。
- 排除项：共享工作区的并行新房任务收紧了项目在售证据，旧 `test_newhouse_and_missing_position` 只提供 project_id，缺 project_sale_status；全量最初209 passed/1 failed。没有修改该任务的实现或断言来掩盖它。本任务相关租金关联 fixture 补了符合现行目录契约的二手房 listing_count=3。
- 前端相关：rental-xingfuli、rental-reference、directory-flow 共19 passed。
- `npx tsc --noEmit` 通过；受影响5个组件/库及新测试 ESLint 通过。
- `npm run build` 通过。首次沙箱执行 Turbopack 因 CSS 编译子进程无法连接失败，使用正常进程权限执行同一构建成功，无配置或依赖绕过。恢复构建自动修改的 next-env.d.ts。
- 全量 `node --test tests/*.test.cjs`：57 passed / 3 failed。其中 rental-dashboard 与 rental-sources 仍引用 HEAD 已不存在的 RentalRefreshButton.tsx；community-management 的旧断言不允许当前 HEAD 已有的 details 元素。本任务新增测试单独通过，未恢复旧控件或删断言来制造全量通过。
- `git diff --check` 与 task context validate 通过。GitNexus 没有已索引仓库，因此 API 影响分析退回源码和实际调用方/回归测试。

## 真实网络验证
当日先前 NAS 低频完整分页：风雅52条/3页（42整租标记）；东方郡73条/4页（69整租标记），各组小区 ID 一致、跨页无重复、has_more=false。

新实现本地真实烟测仅2次HTTP，成功解析首屏与一条真实详情：source_listing_id=7680844815927754790，source_community_id=6581030816598458638，11800元/月、170.75㎡、4室2厅2卫、低楼层/20层，detail_fetched=true。只使用忽略的临时目录，不发布快照。没有用这个单样本作租金参考或收益排名。

## NAS 当前目录只读核查
使用 mode=ro SQLite 适配器和部署版本 eligible_communities，未写入数据库。

| 小区 | 内部 ID | 当前可采资格 | 位置证据 |
|---|---|---|---|
| 风雅钱塘世纪花园 | 10001039 | false，不导入 | GCJ02 120.20749,30.202261，与研究位置相同 |
| 欣盛东方郡 | 10004141 | true，可作为首个试点 | GCJ02 120.213999,30.197782，与研究位置相差约7米 |

本地数据目录与 NAS 当前数据不同；本地 CLI 预览两项均未满足唯一已收录住宅条件，正确返回 unverified，没有强绑。NAS 首批预计只导入东方郡；上线时必须在实际数据目录重新预览。

## 待上线
先按 scripts/XINGFULI_RENTALS.md 部署包含本次代码的版本，运行只读 preview，审阅 ready 行；停止后台服务及其他目录写入者后，在同镜像维护环境显式执行 --apply --maintenance。恢复服务并使用原“采集租金”入口验收。风雅资格及自动搜索不属于本次自动修复范围。

任务保留 in_progress，未 commit/push，未归档。共享工作区的新房任务改动及其临时输出不属于本任务，未回滚或提交。
