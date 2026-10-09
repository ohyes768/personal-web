# 实施计划

## 批 1：契约测试安全网（纯加测试，生产代码零改动）

- [x] 1.1 盘点 18 个端点的现状行为：每端点记录「成功响应字段、失败语义、fetcher 依赖、save 目标」一份速查表（写入本任务 research/ 目录，作为契约断言依据）
- [x] 1.2 编写测试基础设施：fetcher mock 规范 + DataService 指向 tmp_path 的公共 fixture（可复用 test_daily_snapshot 的 `_make_service` 模式）
- [x] 1.3 按域补契约测试，每域一组文件：
  - [x] FRED 系：us-treasuries / vix / tga / ted-spread（`test_update_contracts_fred.py`，成功 payload + fetch 失败不落库）
  - [x] A 股系：dr007 / dr001 / volume / turnover / margin（`test_update_contracts_a_share.py`，成功 payload + fetch 失败不落库）
  - [x] 跨源系：exchange-rates / china-bonds / fund-flow / hibor（`test_update_contracts_cross_source.py`，成功 payload + fetch 失败不落库）
  - [x] 收尾系：commodities / indices / eu-bonds / jp-bonds / update（`test_update_contracts_final.py`，成功 payload + fetch 失败不落库）
  - 每端点断言：HTTP 200、`success=True`、`data` 字段结构、存储被调用、fetcher 失败 → 不落脏数据
- [x] 1.4 全量 `pytest tests/` 绿（217 passed）；遗留 `/update` 契约测试发现并修复 `_build_response_data_with_rates` 漏定义 `eu_m3` / `eu_y2`，这是批 1 唯一必要生产修复，除此之外未改生产行为。
- 验证命令：`cd backend/macro && python -m pytest tests/ -q`
- 检查点：批 1 完成后暂停，向用户汇报测试覆盖矩阵，确认后进批 2

## 批 2：管道抽取与端点迁移

- [x] 2.1 实现 `update_registry.py`（UpdateSpec + 18 条注册中的 1 条 FRED 源作为试点）
- [x] 2.2 试点迁移 us-treasuries 端点 → 薄壳；跑契约测试验证零行为变化；用户确认模板后铺开
- [x] 2.3 按设计 §5 的 4 小批迁移，每小批：迁移 → 全量测试绿 → 独立 commit（可单独 revert）
- [x] 2.4 注册表完整性测试 `test_update_registry.py`（联合类型双向校验 + 契约测试存在性扫描）
- [x] 2.5 演示拦截：临时注释一条联合类型登记 → 测试变红 → 恢复
- [x] 2.6 遗留 `/update` 总端点（routes.py:971）处置：包注册表循环或标记退役，写明结论
- [x] 2.7 scheduler 两个组各手动触发一次，确认 job 记录 success 与 CSV 更新时间
- 验证命令：`cd backend/macro && python -m pytest tests/ -q`；scheduler 手动触发后查 `scheduler` job 历史
- 回滚点：每小批一个 commit

## 收尾

- [x] 3.1 spec 更新：新增「更新管道」章节，§7 手工登记要求改为「注册表 + 完整性测试」机制描述
- [x] 3.2 前端兼容确认：刷新按钮实测一次（响应 shape 未变）
- [x] 3.3 commit / finish-work

## 批次间 review gate

- 批 1 → 批 2 之间必须向用户汇报并确认（测试矩阵 + 零生产改动的 diff 证据）
- 批 2 试点（us-treasuries）完成后第二次确认，模板认可后再铺开

## 2026-10-09 续做计划（按用户“继续完成”授权）

保留已确认的四阶段设计与响应兼容目标，补齐尚未完成的第二批。

- [x] RED：全部注册项必须有可执行阶段构造器；每个实际 HTTP 端点必须调用登记的构造器。
- [x] GREEN：分域提取阶段构造器至 update_sources/，注册表声明阶段、成功/失败消息；公共执行器统一锁与错误/no-op 响应，18 个路由均委托注册项执行。
- [x] 完整性：联合类型双向校验（显式解释历史响应/保留兼容类型）、按 pytest 实际收集的端点成功/失败用例校验，删登记和删测试用例的变异验证。
- [x] 验收：全量 pytest、两组真实 run_group 经 ASGI HTTP 调用实际端点，使用隔离 CSV 与外部源夹具验证保存/响应，不改 scheduler 配置与前端。
- [x] 同步 spec、设计偏差与完成记录，收尾仅限本任务。

## 最终验收记录（2026-10-09）

- 原实现提交：aac80e7；本轮完成其余 15 个可执行构造器迁移及公共响应/锁执行层。18 路由平均 3.6 行、最大 5 行。
- TDD：新增构造器与 HTTP 实际委托测试先见 30 failed / 12 passed；迁移后相关测试 114 passed。
- pytest 实际用例收集完整性测试先失败，补参数级 marker 后 74 passed；含 18 条注册删除、18 条联合类型遗漏和 36 条成功/失败用例删除变异。
- 全量后端测试最终 394 passed，1 个已有 Pydantic Config 弃用 warning；Ruff F 检查和新模块 I 检查通过，git diff --check 通过。
- 兼容性审计：迁移前提交 23ffeba 的原路由与本轮实现逐一运行，18 个完整 HTTP 成功响应（仅去请求时间/归一化日历日期）以及真实 CSV 内容完全一致。基准响应保存为 tests/fixtures/update_success_responses.json。
- 两组 scheduler：真实 SchedulerManager 手动执行 a_share_daily（7 源）/global_daily（8 源），真实 ASGI HTTP、真实 DataService/CSV 与真实 JSONL 历史均 success；只有外部源为夹具，未声称 NAS 实测。
- 网页：playwright-cli 点击现有“中美利差/汇率”的“更新数据”；请求 24/25/26 依次 POST 美债/汇率/中债，全部 HTTP 200 + success=true；请求 27 重载查询，localStorage 成功时间为 2026-10-09T07:18:37.358Z，按钮恢复且无错误文案。
- apps/macro、scheduler 配置与生产数据未改动。
- 计划偏差：批 1 曾因契约测试发现 eu_m3/eu_y2 漏定义而包含必要修复；本轮一次性补齐所有域，未伪造逐域独立提交或线上源可用性验证。
