# 实施清单

前置：design.md 已定稿；后端数据已下发双区（567 小区）。

> 执行记录（2026-10-02）：7 改动点全部完成并验证。两处与 design 的偏差：
> ① 默认视野弃用 `setBounds`——高德 JS API 2.0 实测同 bounds 多次调用 zoom 在 9.1–9.6 摆动，
>    改为固定 `zoom: 11` + `scopeBounds()` 推导中心（zoom 11 垂直视野 ~22km 刚好覆盖双区 21km 紧约束）；
> ② 看板板块下拉顺带补上遗漏的"滨盛"（91 小区），optgroup 化时发现。
> 性能观察：567 小区（含轮廓）渲染流畅，区筛选/板块筛选切换即时响应，console 无错误（仅高德 SDK 内部
> canvas willReadFrequently 提示）。移动端 375px 布局正常（底部 tab + 抽屉筛选），无横向破版。

## 步骤

1. **binjiang-boundary.ts 双围栏**（design §1）
   - Python 从 `backend/housing-map/src/core/boundary.py` 生成 `XIAOSHAN_BORDER_BOUNDARIES` TS 字面量粘贴
   - 新增 `isInXiaoshanBorder` / `isInScope`；文件头注释注明同步来源
   - 验证：tsc 无错；`isInScope(120.25, 30.235)`（盈丰腹地）= true、`isInScope(120.17, 30.30)`（围栏外）= false

2. **区筛选 chips**（design §2）
   - page.tsx：`districtFilter` state + 过滤链 + 控制面板"区域"chips（置于"POI 图层"上方）
   - 验证：切"萧山"后图例计数只剩萧山小区

3. **默认视野**（design §3）
   - BinjiangMap.tsx：`scopeBounds()` + 初始化 `setBounds`；类型面补 `Bounds`/`setBounds`
   - 验证：dev 预览首屏同时可见滨江与宁围北界

4. **文案 + mock**（design §4）
   - layout.tsx title/description、types.ts 注释 + 3 处 mock、page.tsx 注释
   - 验证：grep 无误导性"仅滨江区"残留

5. **market_reference 降级文案**（design §5）
   - MarketOverviewPage 中性化 + "萧山待补录"说明行

6. **看板板块下拉 + 区标识**（design §6）
   - optgroup 8 板块；萧山 tag `.tag-xiaoshan`；globals.css 加样式
   - 验证：看板筛"宁围"仅萧山小区且 tag 为暖色

7. **构建与预览**（design §7）
   - `pnpm build` 通过
   - dev 预览（复用已有 server 惯例）：默认视野/区筛选/POI 围栏/看板全链路走查，记录性能观察
   - `npx tsc --noEmit`（项目若有）或依赖 build 内置检查

8. **收尾**
   - 提交（feat(housing-map): 前端双区化——围栏/区筛选/默认视野/文案）
   - 归档任务 + 推送；parent 任务（10-02-housing-expand-xs-border）验收归档

## 回滚

纯前端改动，单 commit revert 即可；无数据/后端迁移。
