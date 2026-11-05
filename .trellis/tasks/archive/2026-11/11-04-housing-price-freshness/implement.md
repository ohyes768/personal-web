# 实施清单

- [x] 新增政策回归测试：上海当前月6/7个月边界、双价、未知月份、超过30天、来源换绑与合并。
- [x] 新增 price_policy.py；调整 data_loader、tmsf_fetcher、API 与租售比日期，保留兼容字段；测试先红后绿。
- [x] 新增采集测试：仅收录、缺轮廓仍采、missing 去重、撤销/换绑、部分失败/全失败/无价、取消、原子发布/CSV失败。
- [x] 改 refresh 与 RefreshLimit、GET/POST 路由，持久化状态、独立套数、定时复用默认 all。
- [x] 新增前端 SSR 行为测试；实现双价时间/历史/状态组件、两个刷新入口，挂接页面和看板。
- [x] 更新旧测试中冻结日期及新任务统计契约，保持原业务含义；跑相关及全量回归。
- [x] 同步价格契约和任务进度，检查 git diff，不自动提交或部署。

## 实施记录（2026-11-04）

三批次实施 + trellis-check 质检完成。后端全量 1372 passed（--basetemp=.pytest-tmp-price）；前端 200/200、lint/tsc/build 通过。质检自修复 3 项：scoring.py 顶层 deal_count 断裂改走 counts 槽（超30天/无采集时间套数退出评分）、test_newhouse_collection 旧签名同步、refresh 进度改按主小区递增。契约已写入 .trellis/spec/backend/housing-map/backend/price-freshness.md。按任务约束未 commit、未部署。

## 验证命令

后端在 backend/housing-map 使用 .venv/Scripts/python.exe -m pytest --basetemp=.pytest-tmp-price（Windows专用目录）。先跑 tests/test_price_freshness.py、test_refresh.py、test_tmsf_fetcher.py、test_tmsf_price_snapshot.py、test_data_loader.py，再跑全部 tests。确认失败属于新增行为而非环境后实现。

前端在 apps/housing-map：node --test tests/price-freshness.test.cjs，再 node --test tests/*.test.cjs、npm run lint、npx tsc --noEmit、npm run build。使用隔离测试数据检查桌面和390px；不得真实刷新上游。

## 关键检查

all 与 missing 复用同一资格函数，计数与请求目标一致；每轮主快照只发布一次。时间默认由上海日期统一提供，测试注入固定日期，不依赖执行当天。历史成交不进入当前价/租售比。JSONL发布与CSV警告边界真实，取消不会声称撤回已发布数据。价格详情旧任务只兼容，不增加页面范围。
