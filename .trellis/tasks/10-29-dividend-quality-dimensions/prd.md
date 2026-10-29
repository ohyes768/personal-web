# 股息率五维评分与 skill 版本单列展示

## Goal

筛选列表移除加权总分，在一列按业务模式、护城河、行业前景、管理层、财务质量顺序展示；既有 dimensions 可直接展示，新增 skill 输出版本追踪以识别需要重新分析的历史评级。

## Requirements

- 移除筛选列表“评级结果”中的加权总分，按业务模式、护城河、行业前景、管理层、财务质量固定顺序在一列显示，例如 4/4/3/2/1（v1.1.1）；点击该项打开评级详情。
- 使用现有 dimensions 的 1–5 分值；单维 null 用“—”占位，提示与弹框解释为未评分，其他有值维度照常显示，不因总分为 null 隐藏所有维度。
- 从未评级的股票结果列显示“—”，与已分析但证据不足区分；保留打开评级报告的明确入口。
- 历史评级无需重跑即可展示。排队状态、分析/重评/重试、详情、收藏和队列耗时继续正常工作。
- 保留五维、加权分、星级计算规则；skill 输出新增 skill_version 并随评级保存，五维同一点击项的括号内展示实际版本。
- 已知当前已部署版本时，旧版评分标记“需重评”；历史缺版本显示“版本未知”，不回填为当前版本。当前版本来源不可用时明确提示，不能推断评分已是最新版。
- 显式重评不得因原有股票/数据日期幂等键而拿到旧版缓存。

## Acceptance Criteria

- [ ] 已有 dimensions 为 4/4/3/3/5 的股票，在评级结果列显示 4/4/3/3/5（v实际版本），列表不显示加权总分 3.7。
- [ ] 部分维度为 null 时在对应位置显示“—”，保留其他维分数；未分析股票显示“—”。
- [ ] 点击整项打开评级报告，列标题与单元格对齐，空列表 colspan 适配单列布局。
- [ ] 不调用 Hermes 重评即可展示已有结果；原有分析排队、失败重试与报告功能不受影响。
- [ ] TypeScript 检查及 screening 浏览器回归通过，覆盖完整五维、部分 null、从未评级三种情况。
- [ ] skill 输出的版本来自实际执行目录的元数据，经后端保存和 API 传递后原样展示；已知当前版本不一致时显示需重评。
- [ ] 无版本历史结果可读且显示版本未知；更新版本的重评使用不同幂等键，已知版本不符的执行结果不误存为新版。

## Evidence and implementation boundaries

- apps/dividend/src/lib/quality.ts 定义 QUALITY_DIMENSION_ORDER、QUALITY_DIMENSION_LABELS 和 dimensions；现有 dimensionShorthand 遇到 null 会整体返回 null，不适合本次逐维保留分数需求。
- apps/dividend/src/components/ScreeningTab.tsx 当前展示 weighted_score.toFixed(1)；修改表头、单元格和空态列数。
- apps/dividend/src/components/QualityReportModal.tsx 已逐维展示评分，可直接复用同一维度顺序与名称。
- apps/dividend/e2e/screening.spec.ts 已有五维评分 fixture，可扩展验证列映射及 null 场景。
- 实施前读取 frontend 相关约定，并更新 .trellis/spec/backend/dividend-select/backend/quality-rating-contract.md 中列表展示口径。
- 范围已扩展到 skill 输出、后端持久化和前端展示；design.md 和 implement.md 记录设计及验证计划。用户已明确要求开始实现；不包含生产发布或部署。

## Latest layout decision — 2026-10-29

用户要求直接改为单列紧凑格式 4/4/3/2/1（v1.1.1），整体可点击打开详情；替代先前五个独立评分列与单独报告列。版本追踪、旧版需重评和未知版本语义不变。

## Report presentation follow-up — 2026-10-29

- 弹框顶部移除星级、总星数及踩线/升降星提示；保留数据日期、评分时间、分析耗时、skill 版本和五维明细。
- skill 升级至 4.4.0：新报告正文、摘要、风险和关注项不输出总体星级或踩线描述。保留 JSON 兼容字段和原算分规则。
- finalize/只读校验拒绝向报告复制总体星级/踩线文案；不再要求报告包含星级与边界章节。风险边界、五星酒店等真实业务描述不应误判。
- 历史 JSON 与正文不批量改写；已存报告若包含星级章节，发布新版 skill 后重评可更新正文。前端顶部去星立即适用于历史结果。
- 验证历史三颗星/boundary 输入也不再渲染顶部星级、元数据和五维仍可见；skill 文案校验与完整回归通过。
