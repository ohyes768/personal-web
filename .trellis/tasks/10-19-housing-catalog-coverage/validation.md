# 验证记录

- 后端相关回归：82 passed（directory_flow/catalog_filters/rental_statistics/rental_storage）。
- 后端全量：595 passed / 5 failed；失败均在依赖运行时小区数据的 test_api.py（列表为空、缺 transit、评分无数据）。新增覆盖测试全部通过。
- 前端相关 SSR/契约测试：15 passed。TypeScript 与 ESLint 通过。
- 前端全量曾有4个失败，其中定位用例硬编码旧列数已改为验证定位列唯一；其余3个为范围外旧测试失败，涉及 compact source 旧展示断言与已移除的 RentalRefreshButton 引用；未修改这些组件/测试。
- 默认 Turbopack 沙箱构建因子进程失败；Webpack 沙箱编译/类型检查通过但 standalone symlink 权限失败。沙箱外 `pnpm exec next build --webpack` 完整通过。
- Impeccable detector：[]。
- 浏览器：复用已有本地3007服务，拦截API生成35条示例数据（不调用采集/不写实际数据）；1440x1050与390x844截图通过，组合筛选、page2→筛选重置page1、法拍详情、租金失败保留数据及不收录空态通过。窄屏 documentElement.scrollWidth 不超过 innerWidth。
- 预览证据 desktop.png/mobile.png/mobile-confirm.png；browser-check.js 可复用。测试专用浏览器会关闭，已有预览服务保留。
- 未提交、未部署，任务保留用于审阅。现有其他窗口改动均未纳入。
