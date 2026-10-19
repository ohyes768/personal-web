# 实施计划（未开始）

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

## 当前状态
仅创建规划文档并整理此前只读研究；未开始实现、未运行生产采集、未修改业务数据。
