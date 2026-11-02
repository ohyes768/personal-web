# 归档复验（2026-11-02）

- 状态：代码已提交并合入 master；本轮只做收尾复验、规范同步与归档，不再改动产品代码。
- 复验范围：小区审核筛选缓存与来源索引
  - backend/housing-map：`1359 passed`（`pytest -q`，basetemp 独立目录）
  - backend/dividend-select：`332 passed / 3 skipped`
  - backend/index-trends：`151 passed`
  - apps/housing-map：`npm run lint` 通过、`tsc --noEmit` 通过、`node --test tests/*.test.cjs` 199 passed、`npm run build` 通过
  - apps/index-trends：`node --test lib/candleData.test.ts` 9 passed、`tsc --noEmit` 通过、`npm run build` 通过
- 规范同步：本轮补齐的规范见提交 d2633465（宽基周线契约、采集任务弹框紧凑行契约）；其余知识已在各任务提交中写入 spec。
- 归档时仍未完成、需另行授权的事项：生产部署与冷热耗时实测（validation.md 已注明 NAS 未安装 LIVE_CACHE_NOT_INSTALLED）。
