# 执行计划：宏观 Markdown 报告看板

前置确认（第一步内完成）：
- [ ] `backend/macro` 依赖中是否有 pyyaml（`pyproject.toml` / `uv.lock`）→ 决定 frontmatter 解析实现分支（见 design.md）

## Phase A 后端（backend/macro）

- [ ] A1 `src/config.py`：加 `macro_report_data_dir`、`macro_report_upload_token`
  - 验证：现有测试不受影响，`pytest tests/ -x -q` 通过
- [ ] A2 `src/services/report_board_service.py`：save_report / list_reports / get_report / clear_cache（幂等、白名单、原子写、id 字符安全）
  - 验证：`pytest tests/test_report_board_service.py -v` 通过
- [ ] A3 `src/models.py`：ReportUploadResponse / ReportListResponse / ReportDetailResponse
  - 验证：import 无错
- [ ] A4 `src/api/routes.py`：POST /api/reports/upload、GET /api/reports、GET /api/reports/{report_id}（token 校验工具函数）
  - 验证：`pytest tests/test_report_routes.py -v` 通过
- [ ] A5 全量回归：`python -m pytest tests/ -v`
  - **评审门 A**：后端接口用 curl 自测通过（上传→重复上传→列表→详情→401→400→404）

## Phase B Skill 端（两个 impact skill）

- [ ] B1 `a-share-macro-impact-skill/scripts/push_rss.py`：--report-endpoint/--report-token 参数、RSS 成功后追加推送、失败语义（skipped_no_token / failed / duplicate）
  - 验证：本地 `--dry-run` 类自测（无 token 场景跳过告警）；可用本地起 uvicorn + 临时 token 走真推
- [ ] B2 `bond-market-macro-impact-skill/scripts/push_rss.py`：同 B1
  - 验证：同上；两脚本 diff 仅常量与各自 markers
  - **评审门 B**：真推一篇测试报告到本地/生产后端，确认 `duplicate` 重推语义

## Phase C 前端（apps/macro）

- [ ] C1 依赖：`pnpm add react-markdown remark-gfm rehype-sanitize`（+ `@tailwindcss/typography` 如缺）
- [ ] C2 `src/lib/types/reports.ts` + `src/lib/hooks/reports.ts`（useReports / useReportDetail）
- [ ] C3 `src/app/reports/`：page.tsx + components/ReportBoard / ReportList / ReportViewer（两栏布局、来源筛选、移动端切换、sanitize）
  - 验证：`pnpm build` 通过
- [ ] C4 主页 header 加「分析报告」入口链接
- [ ] C5 浏览器走查（dev server + curl 灌样例数据）：列表/详情/筛选/移动端/XSS 注入样例被转义
  - **评审门 C**：截图/快照确认后进入 Phase D

## Phase D 部署配置与收尾

- [ ] D1 `docker-compose.nas.yml` macro-backend 加 `MACRO_REPORT_DATA_DIR=/app/data/reports`
- [ ] D2 生产 `.env` 说明（部署手册或 compose 注释）：`MACRO_REPORT_UPLOAD_TOKEN`；skill 侧 `finance-macro/.env` 同步配置
- [ ] D3 spec 更新（trellis-update-spec）：报告接口契约写入 `.trellis/spec/`
- [ ] D4 提交：按 conventional commits，分 backend / skills / frontend 三笔或合一笔（视改动聚散）
  - 回滚点：任一 Phase 出问题，回退对应代码即可；运行时无 schema/数据迁移，无破坏性

## 验证命令速查

```bash
# 后端
cd backend/macro && python -m pytest tests/ -v
# 前端
cd apps/macro && pnpm build
# 冒烟（生产，替换 token）
curl -sk -X POST https://web.duomi77.cn:9443/api/macro/reports/upload \
  -H "Content-Type: application/json" -H "X-Upload-Token: $TOKEN" \
  -d '{"title":"2026-09-23 测试｜中性｜无","content":"# t\n核心判断 测试","source":"a-share-macro-impact-skill"}'
```
