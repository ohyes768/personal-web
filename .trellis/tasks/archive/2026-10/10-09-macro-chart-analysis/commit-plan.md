# 提交计划

1. `feat(macro): 接入日频图表分析助手`

首期中国国债分析、共享会话/快照/DeepSeek适配器、部署配置、测试与契约文档作为一个完整变更提交。文件：

- `.trellis/spec/guides/index.md`
- `.trellis/spec/guides/macro-chart-analysis.md`
- `.trellis/tasks/10-09-macro-chart-analysis/check.jsonl`
- `.trellis/tasks/10-09-macro-chart-analysis/commit-plan.md`
- `.trellis/tasks/10-09-macro-chart-analysis/design.md`
- `.trellis/tasks/10-09-macro-chart-analysis/implement.jsonl`
- `.trellis/tasks/10-09-macro-chart-analysis/implement.md`
- `.trellis/tasks/10-09-macro-chart-analysis/prd.md`
- `.trellis/tasks/10-09-macro-chart-analysis/research/deepseek-baseline.md`
- `.trellis/tasks/10-09-macro-chart-analysis/task.json`
- `apps/macro/src/app/modules/economic/components/MacroEChart.tsx`
- `apps/macro/src/app/modules/economic/components/analysis/AnalysisProvider.tsx`
- `apps/macro/src/app/modules/economic/page.tsx`
- `apps/macro/src/lib/modules/analysis/api.test.ts`
- `apps/macro/src/lib/modules/analysis/api.ts`
- `backend/macro/.env.example`
- `backend/macro/README.md`
- `backend/macro/src/analysis/__init__.py`
- `backend/macro/src/analysis/auth.py`
- `backend/macro/src/analysis/deepseek.py`
- `backend/macro/src/analysis/registry.py`
- `backend/macro/src/analysis/routes.py`
- `backend/macro/src/analysis/sessions.py`
- `backend/macro/src/analysis/snapshot.py`
- `backend/macro/src/config.py`
- `backend/macro/src/main.py`
- `backend/macro/src/services/data_service.py`
- `backend/macro/tests/test_chart_analysis.py`
- `docker-compose.nas.yml`
- `nginx/web.conf`

未识别且不纳入提交：`.pnpm-store/`（会话开始前已有）。

确认后仅提交上述文件，不推送；任务归档与journal另按Trellis收尾流程处理。
