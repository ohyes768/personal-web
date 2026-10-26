# 股息率选股关注接入 Hermes 五维基本面评级

## Goal

选股关注已通过规则筛出 eligible 股票。本任务在其后增加一层 AI 基本面评级：对 eligible 股票调用 NAS 上的 Hermes Runs API，运行 `dividend-quality-scoring` skill（五维加权：业务模式/护城河/行业前景/管理层/财务质量），产出**五维分项评分 + 星级（1-5）+ 基本面说明 markdown 报告**，后端落盘、前端在选股关注表格展示星级与评分详情。

> 2026-10-23 晚间修订：原方案（四维 0-100 分 + 5 挡位）升级为五维星级方案，评分标准移植自 `basic-quality-rating` skill v2.1（F:\personal-projects\skills\finance-macro\basic-quality-rating）。核心原则：星级为唯一对外聚合输出、边界必标、数据不足不猜、理由先行。

## 已确认决策（2026-10-23 与用户对齐）

1. **作用对象**：选股 eligible 股票（前端在筛选表格勾选后发起分析），暂不做收藏 watchlist 入口。
2. **五维标准写死在 skill 里**：维度、权重、星级映射由 SKILL.md 定死，保证多股可比、结果稳定。五维 = 业务模式 25% + 护城河 25% + 行业前景 20% + 管理层 15% + 财务质量 15%（1-5 分制）。
3. **星级映射（机械换算）**：加权总分 ≥4.5 → 5星；4.0-4.5 → 4星；3.0-4.0 → 3星；2.0-3.0 → 2星；<2.0 → 1星。总分不对外展示（虚假精度），星级 + 五维分项 + 边界标注对外。
4. **评分方式分层**：E 财务质量按后端 payload 硬数据机械核对；A-D 四维由 Hermes agent 联网搜证后按各维判别问题打分（理由先行）。
5. **输出 = 单个 JSON**（五维分、weighted_score、stars、boundary、summary、risks、watch_points、report_md），report_md 内嵌完整 markdown 基本面说明。
6. **参考实现**：`F:\personal-projects\stock-info-dingding\hermes_client.py`（Runs API 契约、Bearer + Idempotency-Key、轮询终态）。
7. **解耦原则**：dividend-quality-scoring 是自动化 JSON 契约变体（输入 JSON → 输出 JSON），不含任何 dividend 后端 URL/表结构；basic-quality-rating 本体保持交互式深度分析形态不变。

## Requirements

### R1 skill：dividend-quality-scoring（五维版）
- 位置：仓库内 `backend/dividend-select/skills/dividend-quality-scoring/SKILL.md` 作为版本化源；发布为操作步骤（复制到 NAS skills 源目录 → skill-manager 管理台安装到 hermes profile）。
- 输入：单只股票的结构化 JSON（后端已有字段：3 年股息率/分红次数/分红比例、ROE 及 3 年历史、年度扣非净利润及同比/3年CAGR、最近两季单季扣非同比、资产负债率、毛利率、股东户数及增幅、申万一级行业等）。
- 五维细则（SKILL.md 定死权重与判别问题）：
  - A business 业务模式（25%）：判别问题（复购周期/必需性、定价权、周期敏感度）
  - B moat 护城河（25%）：五类护城河清单（品牌定价权/转换成本/网络效应/规模/技术牌照）
  - C industry 行业前景（20%）：判别问题（5-10 年需求趋势、替代风险）
  - D management 管理层（15%）：判别问题（决策记录/资本配置/股东一致性/治理透明度/接班）
  - E financial 财务质量（15%）：按 payload 硬数据核对（ROE 水平与 3 年趋势、毛利率、资产负债率结合行业容忍度、扣非同比）；金融股替代规则
- 数据不足降档：字段 null 或证据查不到 → 该维度降档并把缺口写入 watch_points，禁止编造。
- 数据来源优先级：年报/公告 > 券商研报 > 财经数据平台 > 媒体报道；低等级来源须标注。
- 输出：最终回复**只输出一个 JSON 对象**（含 report_md 完整 markdown 报告），无多余文本。

### R2 后端：dividend-select 新增 Hermes 质量评分链路
- 新增 `src/services/hermes_client.py`：移植精简版——submit（Bearer + `Idempotency-Key`）→ 轮询至终态 → 返回 `run.output`；只走 output 交付，不做共享产物目录。
- 新增 `src/services/quality_service.py`：组装股票数据 JSON + prompt（点名 skill）；批量任务复用 RefreshJobManager 异步模式（kind=`quality`）；逐股解析 output JSON 并做 pydantic 校验（五维 1-5、weighted_score=加权和、stars 与映射一致、report_md 非空），失败按股标记。
- 结果落盘 dividend-data 卷（原子写），记录 `scored_at` 与所用数据日期。
- 新路由：
  - `POST /api/dividend/quality/analyze`，body `{codes: [...]}`，202 返回 job 信息；
  - `GET /api/dividend/quality/jobs/{job_id}`，查询单个任务进度（含每股状态）；
  - `GET /api/dividend/quality`，返回全部已落盘评分。
- 环境变量（未配置时 analyze 返回 503）：`HERMES_BASE_URL`、`HERMES_API_KEY`、`HERMES_PROFILE`（默认 ohyes768）、`HERMES_POLL_INTERVAL`（30s）、`HERMES_TIMEOUT`（3600s）、`HERMES_MAX_CONCURRENT`（默认 4）。

### R3 前端：apps/dividend 选股关注 tab
- eligible 表格新增「基本面」列：星级 badge（⭐×N）+ 五维分简写（如 4/5/3/3/5）+ 边界 ⚠️；未分析显示占位；点击「查看基本面」弹层展示五维得分、星级与边界、summary/risks/watch_points、scored_at 与完整 markdown 报告（react-markdown 渲染）。
- 新增「分析基本面」按钮：对勾选的 eligible 股票发起 `POST /quality/analyze`，轮询 job 至完成（转圈 loading + processed/total 进度），成功后刷新基本面列；失败股票可重试。
- 首屏并行 `GET /quality`，与筛选结果互不阻塞。

## Constraints

- Hermes run 分钟级耗时：必须异步（202 + job 轮询），禁止同步阻塞请求。
- 每股一个 run（幂等、可单股重试、避免长列表输出截断）；`Idempotency-Key = quality-{code}-{数据日期}`，同数据日重跑不重复计费。
- 不改动现有筛选/收藏逻辑与数据结构；HERMES 未配置时除新增路由外行为与现状完全一致。
- API key 等敏感信息只进 env / NAS .env，不提交仓库。

## Acceptance Criteria

- [ ] skill `dividend-quality-scoring`（五维版）已发布到 Hermes profile，单股 prompt 能返回合法 JSON（五维分/weighted_score/stars/boundary/summary/risks/watch_points/report_md 齐全，stars 与映射一致）。
- [ ] `POST /quality/analyze` 提交 N 只股票返回 202 + job_id；`GET /quality/jobs/{id}` 可见逐股状态（pending/running/completed/failed + 失败原因）。
- [ ] 评分结果落盘并可通过 `GET /quality` 读取；重复提交同数据日同股票不产生重复 Hermes run（幂等）。
- [ ] 前端选股关注表格显示基本面列与详情弹层（五维 + markdown）；发起分析→轮询→刷新全流程可用；失败股可重试。
- [ ] HERMES 未配置时 `POST /quality/analyze` 返回 503，其余功能不受影响。
- [ ] 后端新增代码有 pytest 覆盖（hermes_client 用 mock requests；quality_service 用假 Hermes；路由 202/查询/幂等）。
