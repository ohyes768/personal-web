# Design: 股息率选股关注接入 Hermes 五维基本面评级

> 2026-10-23 晚间修订：评分契约从"四维 0-100 分挡位"换为"五维 1-5 分 + 星级 + boundary + report_md"（移植 basic-quality-rating v2.1）。工程骨架（RefreshJobManager 复用、幂等、异步 job、路由形态、失败降级）沿用原设计不变。

## 总体流程

```
ScreeningTab 勾选 eligible → POST /api/dividend/quality/analyze {codes}
  → quality_service.submit_analysis(codes)
       1. 校验 HERMES 配置（缺 → 503）与 codes 均在采集池
       2. refresh_jobs.submit(kind='quality', codes, work)   # 复用现有异步任务管理器
  → work(progress)  # 线程池执行
       a. 每股组装数据 JSON + prompt（点名 dividend-quality-scoring skill）
       b. hermes_client.submit_run(..., idempotency_key=quality-{code}-{数据日期})
          信号量限并发（默认 4），全部提交后轮询
       c. 终态 completed → 解析 run.output → pydantic 校验 → 落盘 quality_scores.json
          终态 failed / 解析失败 → 该股标记 failed（原因记入 job），不中断其他股票
       d. 每完成一股调用 progress(code, success)
前端轮询 GET /quality/jobs/{job_id} → 终态后 GET /quality → 渲染基本面列
```

## 评分契约（核心变更）

### 五维与权重（SKILL.md 定死）

| 维度 key | 中文名 | 权重 | 评分 | 证据来源 |
|---|---|---|---|---|
| business | 业务模式 | 25% | 1-5 | 联网搜证（判别问题） |
| moat | 护城河 | 25% | 1-5 | 联网搜证（五类护城河清单） |
| industry | 行业前景 | 20% | 1-5 | 联网搜证（判别问题） |
| management | 管理层 | 15% | 1-5 | 联网搜证（判别问题） |
| financial | 财务质量 | 15% | 1-5 | **payload 硬数据机械核对** |

`weighted_score = business×0.25 + moat×0.25 + industry×0.20 + management×0.15 + financial×0.15`

### 星级映射（机械换算，唯一）

| weighted_score | stars |
|---|---|
| ≥ 4.5 | 5 |
| 4.0-4.5 | 4 |
| 3.0-4.0 | 3 |
| 2.0-3.0 | 2 |
| < 2.0 | 1 |

边界规则：距档位边界 < 0.25 时输出 `boundary`（如"行业前景 3→4 即五星"），否则 null。

### 输出 JSON（最终回复只含此对象，裸 JSON）

```json
{"code": "601717", "name": "中创智领",
 "dimensions": {"business": 4, "moat": 5, "industry": 3, "management": 3, "financial": 5},
 "weighted_score": 4.05,
 "stars": 4,
 "boundary": null,
 "summary": "一句话结论",
 "risks": ["..."], "watch_points": ["..."],
 "report_md": "# 基本面评级：...\n（完整 markdown 报告：业务核实 + 五维评分表含理由 + 星级与边界）"}
```

## 模块边界

### 新增 `src/services/hermes_client.py`（纯客户端，移植自 stock-info-dingding 并精简）

| 函数/类 | 职责 |
|---|---|
| `HermesConfig.from_env()` | 读 `HERMES_BASE_URL/API_KEY/PROFILE/POLL_INTERVAL/TIMEOUT/MAX_CONCURRENT`；`HERMES_API_KEY` 或 `BASE_URL` 缺失视为未配置（`is_configured=False` 语义） |
| `submit_run(cfg, prompt, idempotency_key) -> str` | `POST {base}/p/{profile}/v1/runs`，body `{"input": prompt}`，header Bearer + `Idempotency-Key`；返回 run_id |
| `poll_run(cfg, run_id) -> str` | 循环 GET 至终态；completed 返回 `output`；failed/cancelled/interrupted 抛 `HermesRunFailed`；超时抛 `HermesTimeout` |

异常类型：`HermesError` 基类 + `HermesApiError` / `HermesRunFailed` / `HermesTimeout`。仅用 `requests`，不引新依赖。
**不做** dingding 版的产物目录/binding/`_read_report`——评分结果为短 JSON（含 report_md 几 KB），只走 `run.output`。

### 新增 `src/services/quality_service.py`（业务编排）

- `build_stock_payload(stock: DividendStock) -> dict`：挑参与评分的字段（行业、3年股息率与分红次数、分红比例、ROE 及 3 年历史、年度扣非净利润/同比/3年CAGR、最近两季单季扣非同比及标签、资产负债率、毛利率、股东户数/增幅、EPS），值缺失传 null 由 skill 按缺失降档处理。
- `build_prompt(payload: dict) -> str`：点名 skill + 数据 JSON + 「最终回复只输出 JSON（含 report_md），不要 markdown 代码围栏」。
- `QualityScore`（pydantic）：`dimensions: dict[str,int]`（五键各 1-5）、`weighted_score: float`（校验 = 加权和，容差 ±0.01）、`stars: int(1-5)`（校验与映射表一致）、`boundary: str|None`、`summary: str`、`risks: list[str]`、`watch_points: list[str]`、`report_md: str`（非空）。解析时容错剥离 ```json 围栏；校验失败按该股失败处理。
- `QualityService.submit_analysis(codes) -> dict`：入口（校验→组 job）。
- 落盘：`data/quality_scores.json`，结构 `{code: {...QualityScore 字段, scored_at, data_date, name}}`，`atomic_write` 原子更新（每完成一股合并写一次）。
- 幂等键：`quality-{code}-{数据日期}`（数据日期取财务汇总文件日期，无则当天）。同数据日重跑同股票时 Hermes 返回原 run，结果覆盖落盘。

### `src/services/refresh_jobs.py` 改动（最小）

- `_prune` 的 kinds 元组加 `'quality'`；其余（submit 去重、断电恢复置 interrupted、retry_codes）直接复用。

### `src/api/routes.py` 新增路由

| 路由 | 说明 |
|---|---|
| `POST /quality/analyze` | body `{codes}`（非空、均需在采集池且筛选可查到）；未配置 Hermes → 503；已有 quality 活跃 job → 返回该 job（`reused: true`）；否则 202 返回 job |
| `GET /quality/jobs/{job_id}` | 返回 job（含逐股 codes/processed/failed_codes）；无此 job → 404 |
| `GET /quality` | 返回落盘的全部评分 + 每股分析状态（无=未分析） |

### Skill：`dividend-quality-scoring`（SKILL.md，五维版）

- 位置：仓库内 `backend/dividend-select/skills/dividend-quality-scoring/SKILL.md` 作为版本化源；发布为**操作步骤**——复制到 NAS skills 源目录（SKILLS_SOURCE_ROOT）后经 skill-manager 管理台安装到 hermes profile。
- 内容骨架：输入契约（字段表）→ 五维细则与判别问题（A-D 联网搜证、理由先行；E 按 payload 硬数据核对，金融股替代规则）→ 星级映射表 + 边界规则 → 数据不足降档规则 → 数据来源优先级 → 输出 JSON schema 与 report_md 模板。

### 前端 `apps/dividend`

- 新增依赖 `react-markdown`（渲染 report_md）。
- `lib/quality.ts`：类型（QualityScore、QualityJob）+ api 封装（api.ts 追加 analyzeQuality/getQualityJob/getQuality）。
- `ScreeningTab.tsx`：
  - 新列「基本面」：星级 badge（⭐×stars）+ 五维分简写（4/5/3/3/5）+ boundary ⚠️；点击开弹层。
  - 「分析基本面」按钮（勾选数 >0 可用）：POST → 轮询 job（3s 间隔，复用 requestId 防错序模式）→ 终态刷新 `GET /quality`；显示 `processed/total` 进度；失败股提示可重试（重新发起仅含失败股）。
  - 新弹层组件（照 DetailModal 模式）：五维得分 + 星级/边界 + summary/risks/watch_points + scored_at + react-markdown 渲染 report_md。
  - 基本面数据独立于筛选结果加载（首屏并行 GET /quality）。

## 配置（docker-compose.nas.yml dividend-backend + NAS .env）

| 变量 | 默认 | 说明 |
|---|---|---|
| `HERMES_BASE_URL` | 无 | 如 `http://<nas>:8642` |
| `HERMES_API_KEY` | 无 | Bearer key（profile 对应） |
| `HERMES_PROFILE` | `ohyes768` | Runs API 前缀 `/p/<profile>/` |
| `HERMES_POLL_INTERVAL` | `30` | 秒 |
| `HERMES_TIMEOUT` | `1800` | 单 run 总超时（秒） |
| `HERMES_MAX_CONCURRENT` | `4` | 同时在飞 run 数上限 |

## 关键决策与理由

- **output 交付而非产物目录**：评分输出是短 JSON（含 report_md），`run.output` 足够；免除 dividend-backend 容器与 Hermes 共享文件系统的部署约束。
- **每股一个 run**：幂等键粒度=股票，单股可重试；避免一次 run 评 N 股的长输出截断/漏评风险。代价是 run 数多，用并发上限 + 用户勾选控制成本。
- **复用 RefreshJobManager**：断电恢复、进度持久化、活跃去重、retry_codes 全部现成；只加一个 kind。
- **五维与星级映射写死在 skill**：LLM 只按细则打分并机械映射星级，跨股票一致、可回放核对。总分不对外展示（序数加权的虚假精度），对外只给五维分项 + 星级 + 边界。
- **E 维硬数据 / A-D 联网搜证分层**：财务数据后端现成（可靠、便宜），定性判断交给 agent 搜证（贵但必要）；判别问题先行防止理由后置。
- **同 kind 活跃 job 去重**：避免用户连点产生并发 run 风暴；想并行分析下一批需等当前 job 终态（MVP 够用，后续可放开）。

## 失败与降级

| 失败点 | 行为 |
|---|---|
| Hermes 未配置 | `POST /quality/analyze` 503，前端按钮置灰并提示 |
| submit 非 2xx / 网络异常 | 该股 failed（原因入 job），继续其他股票 |
| 轮询超时 / failed / cancelled / interrupted | 该股 failed，继续其他股票 |
| output 解析/校验失败（含 weighted_score/stars 不一致） | 该股 failed（原因=解析错误摘要），可重试 |
| 落盘失败 | 日志 + job error；已提交 run 结果在内存中尽力再写一次 |

## 兼容与回滚

- 不动筛选/收藏/刷新现有逻辑；`refresh_jobs.py` 仅 `_prune` 加一项。
- 移除 `HERMES_BASE_URL/API_KEY` 即整体下线，存量落盘评分只读不影响其他功能。
- 新增文件：hermes_client.py、quality_service.py、skills/dividend-quality-scoring/SKILL.md、前端 quality 模块 + 测试；routes.py 追加三路由。

## 风险与开放点

- **A-D 维度联网搜证使单 run 更慢/更贵**（相比旧四维纯核对方案）：并发上限默认 4 保守起步 + 用户勾选控制；实测后调整。
- **skill 输出稳定性**：JSON 模式偶发围栏/前言 → 解析层容错剥离；report_md 内嵌 JSON 使输出变长 → 仍为几 KB 量级；仍失败按股重试。
- **数据日期口径**：财务汇总文件日期作为幂等键的数据日期；财务刷新后重评自然生成新 run。
- **Hermes profile 并发/配额**：实测后调整。
