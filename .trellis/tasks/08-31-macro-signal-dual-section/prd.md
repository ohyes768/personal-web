# 宏观信号页去除月度/日频切换改为双区块单页

## Goal

去掉宏观信号 Tab 的月度/日频模式切换，改为单页双区块：月度信号(4卡+档位刻度)与日频信号(3卡+日变化)上下并行展示，各自带轻量时间选择器，挂载时并行请求。减少用户操作——常用路径(看最新状态)零点击。

## 背景与现状

`apps/macro/src/app/modules/economic/components/MacroSignalTab.tsx` 目前是 `'monthly' | 'daily'` 两个互斥模式，靠左上角 toggle 切换：

- 月度：`loadSnapshot` → 4 张 GroupCard(评分+档位刻度)，MonthSwitcher 选月
- 日频：`/api/macro/daily-snapshot` → 3 张 DailyCardGrid(最新值+日变化)，DailySwitcher 选日，懒加载(切到日频才首拉)

用户要同时看月频与日频指标必须来回切换。

## Requirements

1. **去掉模式切换**：删除 `SignalMode` 状态与 toggle 按钮组，月度与日频内容同屏展示。
2. **双区块布局**：
   - 区块一「月度信号」：区块头(标题 + MonthSwitcher) + GroupCardGrid(4 卡)
   - 区块二「日频信号」：区块头(标题 + DailySwitcher，默认日期文案体现「截至」语义) + DailyCardGrid(3 卡)
3. **并行加载**：组件挂载时月度、日频两个请求同时发出(日频不再懒加载等切换)。
4. **默认值零操作**：月度默认上个完整月(现有 pickDefaultMonth 逻辑不变)；日频首拉不带 date 参数，由后端 15:00 规则推导(现有逻辑不变)。
5. **状态独立**：两区块的 loading / error / 数据状态互不影响；切月只重拉月度、切日只重拉日频。
6. **纯前端改动**：不改后端接口、不改数据契约；GroupCard / DailyCardGrid / MonthSwitcher / DailySwitcher 组件尽量复用，只重构容器层 MacroSignalTab。

## Out of Scope

- 不合并月频/日频指标到同一张卡(方案 B 已否)
- 不改各卡片内部渲染逻辑(档位刻度、日变化、跳转曲线按钮等)
- 不改后端 macro 服务

## Acceptance Criteria

- [ ] 页面无月度/日频 toggle；月度 4 卡与日频 3 卡同屏可见
- [ ] 挂载即并行发起 `/api/macro/months` + `loadSnapshot` + `/api/macro/daily-snapshot`(首拉不带 date)
- [ ] 月度区块：切月只重拉月度快照，选择器行为与现状一致(默认上个月、当月可选、无数据月回退)
- [ ] 日频区块：默认显示后端推导日期，切日期显式传 date；卡头/回退标注行为与现状一致
- [ ] 任一区块请求失败只影响本区块的错误提示，另一区块正常渲染
- [ ] `pnpm build`(apps/macro) 与 `pnpm lint` 通过；无 console.log

## Notes

- 轻量任务，PRD-only。实现集中在 `MacroSignalTab.tsx` 容器层重构，可能新增一个区块头小组件(标题 + 选择器一行)。
- 日频懒加载注释「仅切到日频模式才首拉」的语义随之删除。
