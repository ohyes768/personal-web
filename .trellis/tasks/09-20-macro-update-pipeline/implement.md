# 实施计划

## 批 1：契约测试安全网（纯加测试，生产代码零改动）

- [ ] 1.1 盘点 18 个端点的现状行为：每端点记录「成功响应字段、失败语义、fetcher 依赖、save 目标」一份速查表（写入本任务 research/ 目录，作为契约断言依据）
- [ ] 1.2 编写测试基础设施：fetcher mock 规范 + DataService 指向 tmp_path 的公共 fixture（可复用 test_daily_snapshot 的 `_make_service` 模式）
- [ ] 1.3 按域补契约测试，每域一组文件：
  - [x] FRED 系：us-treasuries / vix / tga / ted-spread（`test_update_contracts_fred.py`，成功 payload + fetch 失败不落库）
  - [x] A 股系：dr007 / dr001 / volume / turnover / margin（`test_update_contracts_a_share.py`，成功 payload + fetch 失败不落库）
  - [x] 跨源系：exchange-rates / china-bonds / fund-flow / hibor（`test_update_contracts_cross_source.py`，成功 payload + fetch 失败不落库）
  - [x] 收尾系：commodities / indices / eu-bonds / jp-bonds / update（`test_update_contracts_final.py`，成功 payload + fetch 失败不落库）
  - 每端点断言：HTTP 200、`success=True`、`data` 字段结构、存储被调用、fetcher 失败 → 不落脏数据
- [x] 1.4 全量 `pytest tests/` 绿（217 passed）；遗留 `/update` 契约测试发现并修复 `_build_response_data_with_rates` 漏定义 `eu_m3` / `eu_y2`，这是批 1 唯一必要生产修复，除此之外未改生产行为。
- 验证命令：`cd backend/macro && python -m pytest tests/ -q`
- 检查点：批 1 完成后暂停，向用户汇报测试覆盖矩阵，确认后进批 2

## 批 2：管道抽取与端点迁移

- [ ] 2.1 实现 `update_registry.py`（UpdateSpec + 18 条注册中的 1 条 FRED 源作为试点）
- [ ] 2.2 试点迁移 us-treasuries 端点 → 薄壳；跑契约测试验证零行为变化；用户确认模板后铺开
- [ ] 2.3 按设计 §5 的 4 小批迁移，每小批：迁移 → 全量测试绿 → 独立 commit（可单独 revert）
- [ ] 2.4 注册表完整性测试 `test_update_registry.py`（联合类型双向校验 + 契约测试存在性扫描）
- [ ] 2.5 演示拦截：临时注释一条联合类型登记 → 测试变红 → 恢复
- [ ] 2.6 遗留 `/update` 总端点（routes.py:971）处置：包注册表循环或标记退役，写明结论
- [ ] 2.7 scheduler 两个组各手动触发一次，确认 job 记录 success 与 CSV 更新时间
- 验证命令：`cd backend/macro && python -m pytest tests/ -q`；scheduler 手动触发后查 `scheduler` job 历史
- 回滚点：每小批一个 commit

## 收尾

- [ ] 3.1 spec 更新：新增「更新管道」章节，§7 手工登记要求改为「注册表 + 完整性测试」机制描述
- [ ] 3.2 前端兼容确认：刷新按钮实测一次（响应 shape 未变）
- [ ] 3.3 commit / finish-work

## 批次间 review gate

- 批 1 → 批 2 之间必须向用户汇报并确认（测试矩阵 + 零生产改动的 diff 证据）
- 批 2 试点（us-treasuries）完成后第二次确认，模板认可后再铺开
