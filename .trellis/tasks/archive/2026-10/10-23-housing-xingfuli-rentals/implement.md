# 幸福里租金试点实施计划

用户已批准实施。使用 writing-plans 整理计划，遵循 Trellis inline 流程，当前工作区存在并行新房任务，禁止覆盖其代码或文档。

1. [x] 先新增 tests/test_xingfuli_rentals.py，构造 pia-ssr-data 首屏、API分页与详情最小 fixture，运行红灯测试。
2. [x] 新增 src/services/xingfuli_rentals.py，实现 URL/JSON/归属校验、低频 GET、详情核验与 SeedRunResult 输出；以 `crawl(..., max_pages=10, details=True)` 暴露给刷新。
3. [x] 新增 rental_reference/providers.py 的 active_sources 与 same_source；写跨来源同 ID、优先级与解除测试，再改刷新、缓存、storage 和 query/coverage 消费。旧 source 缺失按 fang 读取。
4. [x] 新增显式 scripts/import_xingfuli_pilots.py（默认 preview），通过现有 Registry 事务导入、限制住宅资格、人工拒绝及关联冲突；测试 preview无写入与apply幂等。
5. [x] 修改必要前端来源链接/文案，在原有组件内复用 safeSourceLink；新增幸福里链接和恶意域回归，无新界面设计。
6. [x] 运行 backend/housing-map/.venv/Scripts/python.exe -m pytest tests/test_xingfuli_rentals.py tests/test_rental_refresh.py tests/test_rental_sources.py tests/test_rental_api.py tests/test_rental_storage.py tests/test_rental_statistics.py tests/test_rental_association_flow.py tests/test_directory_flow.py --basetemp=.pytest-tmp-xingfuli；失败定位后修复。
7. [x] 前端 node --test tests/*.test.cjs、TypeScript、受影响文件 ESLint 与构建；使用隔离 HOUSING_DATA_DIR 检查导入和查询/刷新链路。
8. [x] 读回变更、按 trellis-check 自检、同步租金来源契约和任务进度，交付使用方式及部署边界。不自动 commit/push。

## 回退
代码未部署前不影响生产。上线后可解除试点幸福里关联回到原房天下；不能把历史幸福里快照当房天下。保留生产来源和原数据，不进行整库替换。

## 最终验证记录
见 verification.md。相关后端258通过、1项并行新房测试显式排除；前端相关19通过，类型/ESLint/生产构建通过；全量前端57通过、3个既有失败。尚未部署、未写生产关联；任务保留 in_progress 待上线与验收。
