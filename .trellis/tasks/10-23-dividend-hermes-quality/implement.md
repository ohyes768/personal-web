# Implement: 股息率选股关注接入 Hermes 五维基本面评级

执行顺序自上而下；每个 Phase 结束跑对应验证命令，通过后才进入下一 Phase。

> 2026-10-23 晚间修订：契约换为五维星级版（见 design.md「评分契约」），Phase 划分不变。

## Phase 0: Skill 源文件（五维版）

- [x] 新建 `backend/dividend-select/skills/dividend-quality-scoring/SKILL.md`
  - 输入契约（与 `build_stock_payload` 字段一一对应）
  - 五维细则与权重（business 25/moat 25/industry 20/management 15/financial 15）、各维判别问题、E 维硬数据核对表、金融股替代规则
  - 星级映射表（≥4.5→5 / 4.0-4.5→4 / 3.0-4.0→3 / 2.0-3.0→2 / <2.0→1）+ 边界规则（距边界 <0.25 输出 boundary）
  - 数据不足降档规则、数据来源优先级
  - 输出 JSON schema + 示例（与 `QualityScore` pydantic 一致，含 report_md 及其模板）
- 验证：字段表与 design.md 的 payload 清单逐项核对无缺漏；输出键名与 pydantic 逐字一致。

## Phase 1: 后端 hermes_client + 测试

- [x] `backend/dividend-select/src/services/hermes_client.py`
  - `HermesConfig.from_env()`、`submit_run()`、`poll_run()`、异常类
  - 未配置时 `from_env` 能表达「未启用」语义
- [x] `tests/test_hermes_client.py`（mock requests，不真连）
  - submit：URL/profile 前缀/Bearer/Idempotency-Key/非 2xx 抛错/缺 run_id 抛错
  - poll：completed 返回 output；failed 终态抛错；超时抛 HermesTimeout
- 验证：`cd backend/dividend-select && python -m pytest tests/test_hermes_client.py -v`

## Phase 2: 后端 quality_service + 测试

- [x] `quality_service.py`：`build_stock_payload` / `build_prompt` / `QualityScore`（五维校验：dimensions 五键 1-5、weighted_score=加权和、stars 与映射一致、report_md 非空）/ `QualityService.submit_analysis` / 落盘合并写
- [x] `refresh_jobs.py` `_prune` kinds 加 `'quality'`（仅此一处）
- [x] `tests/test_quality_service.py`（假 Hermes：注入 submit/poll 双函数）
  - 正常链路：2 股完成 → 落盘字段齐全、progress 计数正确
  - 一股 failed 不影响另一股；解析失败（带围栏的合法 JSON 应成功，纯垃圾 failed）
  - 幂等键格式 `quality-{code}-{data_date}`；weighted_score/stars 校验不一致按失败处理
- 验证：`python -m pytest tests/test_quality_service.py tests/test_screening_service.py -v`（确认筛选存量测试不受影响）

## Phase 3: 后端路由 + 集成测试

- [x] `routes.py`：`POST /quality/analyze`（503/202/reused 三分支）、`GET /quality/jobs/{id}`（404）、`GET /quality`
- [x] `main.py`：QualityService 装配（复用 app.state / set_services 模式）
- [x] `tests/test_quality_api.py`：FastAPI TestClient + 假 Hermes
  - 未配置 503；提交 202 返回 job_id；jobs/{id} 404 与正常；GET /quality 返回落盘
- 验证：`python -m pytest tests/ -v`（全量，对照基线无新增失败）
- [ ] 本机连真 Hermes 冒烟：`.env` 配 HERMES_*，curl 提交 1 只股票，确认 run 产出合法 JSON（需要 NAS 可达 + skill 已发布；不可达则记 TODO 延后）

## Phase 4: 前端

- [x] `apps/dividend`：`pnpm add react-markdown`
- [x] `lib/quality.ts`：类型（QualityScore/QualityJob）+ `dividendApi` 三个方法封装（api.ts 追加）
- [x] `ScreeningTab.tsx`：基本面列（星级 badge + 五维分简写 4/5/3/3/5 + boundary ⚠️）+ 详情弹层（五维 + summary/risks/watch_points + scored_at + react-markdown 渲染 report_md）+ 「分析基本面」按钮 + job 轮询（3s、requestId 防错序）+ 失败股重试
- [x] 首屏并行加载 `GET /quality`，筛选结果与基本面互不阻塞
- 验证：`cd apps/dividend && pnpm build`（类型+构建通过）；`pnpm dev` 手测全流程（发起→进度→星级→弹层）
- [x] 若 `lib/quality.ts` 含可测纯函数（星级映射/解析），补 vitest 用例（对齐 screening.test.ts 风格）

## Phase 5: 部署配置 + 收尾

- [x] `docker-compose.nas.yml` dividend-backend 增加上表 6 个 env；NAS `.env` 补值（不入库）
- [ ] SKILL.md 复制到 NAS skills 源目录，经 skill-manager 管理台发布到 hermes profile（操作步骤，截图/记录到任务 notes）
- [x] `.trellis` spec 更新（backend/dividend-select spec 增补 quality 路由与 hermes 契约）
- [ ] 全量回归：后端 pytest + 前端 build；NAS 部署后端到端冒烟（1 只股票真实评分）

## 回滚点

- Phase 1-3 均为新增文件/路由，revert 即回滚；Phase 4 前端独立可回退；Phase 5 去掉 env 即功能下线。
