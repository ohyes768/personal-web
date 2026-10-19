# 验证记录（2026-10-18）

## 结果

- 后端相关回归：203 passed，2 条已有 FastAPI/Starlette 依赖弃用警告。
- 前端相关回归：35 passed。
- TypeScript `npx tsc --noEmit` 与 `npm run lint` 均通过。
- `git diff --check` 通过；仅有 Windows LF/CRLF 转换提示。
- 独立只读审查发现的“仅列表成功就重置验证退避等级”已修复；新增失败复现测试确认修复。审查未发现其他阻塞项。

## 命令

后端目录：`backend/housing-map`

```text
.venv/Scripts/python.exe -m pytest tests/test_fang_resilience.py tests/test_rental_refresh.py tests/test_rental_sources.py tests/test_rental_api.py tests/test_rental_statistics.py tests/test_rental_storage.py tests/test_directory_collection.py tests/test_rental_association_flow.py tests/test_fang_rentals.py tests/test_fang_rentals_run.py -q --basetemp=.pytest-tmp-fang-final
```

前端目录：`apps/housing-map`

```text
node --test tests/rental-dashboard.test.cjs tests/rental-sources.test.cjs tests/rental-reference.test.cjs tests/directory-flow.test.cjs
npx tsc --noEmit
npm run lint
```

## 重点覆盖

- 跨客户端共享最小间隔、锁等待可取消；真实超时最多一次重试，后续请求本轮停止。
- 三级冷却跨重启保持；首次详情验证即停；冷却中的第二轮实际网络请求为 0、失败数为 0、未尝试数单列。
- 详情 TTL、来源隔离、动态价格不被覆盖、过期/损坏缓存清理；同一列表第二轮只请求列表。
- 6 小时全复用不发布、不改原时间；混合发布保留复用小区；改绑后失败不带入旧来源样本。
- 已关联来源先于新来源发现；已有冷却不更新来源 searched_at 或虚增失败。
- API 旧任务兼容与共享前端文案；相关统计/来源/目录行为回归。

## 浏览器 QA

使用真实 CollectionControls 的静态渲染和当前全局样式，隔离模拟缓存/冷却/未查询状态；通过临时本地 Next 服务打开。桌面文案可读；390px × 844px 下 dialog 宽约 358.4px，document.scrollWidth=390，无横向溢出。模拟文件验证后删除，未请求真实上游、未写生产数据。

## 交付边界

业务代码和规范已更新；用户已授权本次提交与推送。未部署 NAS、未触发生产全量刷新。NAS 上线后的低频真实烟测仍待执行。任务保留 in_progress，便于后续提交/部署与归档；其他并行任务的脏文件保留。
