# 实施计划

1. 确认 PRD 的 Q1，审阅设计及当前 directory-flow、community-enrichment、directory-position 规范后再激活实现。
2. 隔离验证 NAS 浏览器读取三个实测项目，调查完整实际地址来源；记录访问受限、超时及人工验证码行为，不以本机成功代替 NAS 结果。
3. 保存公开页面最小测试样本，先写新房独立发现、同 ID 类型隔离、真实选择器、验证页和截断地址回归测试。
4. 实现索引发现与 project 来源保存，修复 existing 缓存/历史事实类型分流，验证忽略、取消、幂等。
5. 按验证结果接入详情获取与可选浏览器 worker，设置限速/缓存/超时/取消，失败保留旧事实。
6. 联合修改身份关联、source-only 市场投影、混合市场与 listing_gate，保护人工决定、历史和所有下游 ID 路由。
7. 复用管理入口，验证筛选/总数/分页/详情/单项重试以及桌面手机操作。
8. 质量检查、同步真实契约，生成只读生产补录预览；审阅后另行安排生产执行。

## 验证安排
- Windows 后端测试遵守 .trellis/spec/backend/testing-environment.md，使用独立 HOUSING_DATA_DIR 与专用 basetemp；覆盖 directory_flow、community_enrichment、community_listing、位置/价格隔离和新增采集测试。
- 前端运行 TypeScript、相关目录/筛选/管理测试和改动文件 ESLint。
- 离线测试、NAS 实测及生产预览分开报告；150/52/19 是研究快照，不写固定断言。

## 风险
ID 串用、重复主小区、ESF 低挂牌误排除、截断地址误收录、推荐字段误取、浏览器挂死阻断全任务、人工决定被覆盖、新房价格进入 ESF 指标。

## 当前状态（2026-10-23 实现完成，待 NAS 验证与生产预览）
- 步骤 1 完成：Q1 确认为保留资料待补；任务已激活（in_progress）。
- 步骤 2 部分完成：本机只读实测（scripts/verify_newhouse_live.py）证实索引可 HTTP 读取——3486 项目、滨江 175、在售/尾盘/待售 52，与 PRD 研究快照一致；三个实测项目（春来晴翠园/泊玺骏庐/月澜雅颂里）详情页本机 HTTP 全部返回验证页（challenge），证实详情获取必须走浏览器 worker。NAS 浏览器验证仍未执行（需部署环境）。
- 步骤 3-7 完成：新房独立发现循环（滨江在售/尾盘/待售、名录已覆盖项目跳过、忽略不复活、30 天缓存、详情失败保留名单并按 challenge/identity_mismatch/missing_facts/截断地址分类）；existing 缓存改 (source_kind, source_id) 键；project 来源走 fetch_project_facts_by_id 直取，enrich/采集均不构造 ESF URL；全部 legacy 事实回退点（eligibility/effective_type/classify_sources/catalog_property_types/source_view/reviews）按 kind 隔离；listing_gate 新房豁免与售完回落、售完 project 不产生 unknown；community_views 混合市场新房优先投影；inventory source-only 行带 market_state；价格刷新目标排除 project kind；截断地址永不落行（Q1）。tests/test_newhouse_collection.py 15 例 + 全量回归 611 通过（另 5 个 test_api 失败为存量问题，与本任务无关，stash 验证）。前端 directory-flow/position-status 测试 16 通过。
- 步骤 8 未完成：NAS 浏览器实测、只读生产补录预览、生产执行授权，均待部署阶段。
- 注意：工作区存在并行会话的幸福里租金改动（xingfuli 相关文件），提交时只包含本任务文件。
