# hermes 统一触发 实施计划

前置：prd/design 就绪，两项决策已定（2026-11-07）。

> 归档补记（2026-11-11）：下文的 Phase 1「触发器放在 stock-info-dingding 仓库」这一条
> 在实施中**已改**——触发镜像源码最终迁入本仓 `backend/task-web/trigger/`（它属于 task-web
> 的执行基础设施，不属于任何业务或 skill 内容仓库）。其余按计划执行，并在此基础上扩展到
> Hermes 双 profile 全量登记与任务分组 tab。

## 实施顺序

### Phase 1 触发器
1. [x] `hermes_trigger.py`：参数解析、jobs.json 查找（id 精确/name 兜底）、Runs API 提交
       （Idempotency-Key）、轮询终态、退出码映射（0=completed / 1=失败终态 /
       2=配置或提交错误 / 3=轮询超时）、stdout 摘要。
2. [x] 干跑自测：无 key / 错 base_url / 不存在 job-id 三类错误路径本地验证（不真调 API）。
3. [x] **计划变更**：触发镜像源码最终不留在 stock-info-dingding，迁入本仓
       `backend/task-web/trigger/`（`hermes_trigger.py` + `Dockerfile`，镜像
       `hermes-trigger:latest`），与 task-web 同仓同版本管理（提交 `0f1178a6`、`c0cb085a`）。

### Phase 2 task-web volumes 支持（personal-web）
4. [x] db.py tasks 表加 `volumes TEXT` 列迁移；registry 透传（yaml 数组→JSON 入库）。
5. [x] executor：docker 引擎支持 volumes/network/user + env 显式优先，
       `mode` 解析默认 ro；fake client 测试断言 volumes 传递与非法格式报错
       （提交 `9f004008`、`379fe602`、`888d6529`）。
6. [x] tasks.yaml 试点登记：csi300-brief（`35 16 * * 1-5`）+ pm25-broadcast
       （`45 23,3,9 * * *`），均默认禁用、写明旧触发禁用步骤。
7. [x] pytest 全绿 → commit/push（`uv run python -m pytest tests/ -q` → 80 passed）。

### Phase 3 NAS 验证（用户操作）
8. [x] stock-info-dingding git pull + 触发镜像重建；personal-web git pull +
       `./scripts/deploy-nas.sh task-web`。
9. [x] 页面手动执行 pm25-broadcast → 验证微信收到 + run completed；
       手动执行 csi300-brief → 验证钉钉收到 + 状态语义。
10. [x] 验证通过：Hermes 侧旧 job `enabled=false`（pm25）+ crontab 注释 CSI300 旧条目 →
       页面启用两个任务正式计划。

### Phase 4 计划外扩展（实施中自然生长，已落地）
11. [x] AI 任务 prompt 事实源收编进 tasks.yaml（`prompt:` → tasks 表 → 执行期注入
        `HERMES_PROMPT`），触发脚本首选 env、回退 jobs.json，切换 profile 不再要求
        目标 profile 有同名 job（提交 `0f1178a6`）。
12. [x] Hermes 双 profile 全量登记：10 个 job 进 hermes 组（提交 `5b943b44`）。
13. [x] 任务分组 tab——脚本任务与 Hermes 任务区分展示（提交 `47222b5e`）。
14. [x] natgeo 改造为 Hermes skill 触发（`6727f1e4`）；新闻联播摘要 RSS 推送登记
        （`abfeae28`）；csi300-brief 挂载路径随 skill 迁出改指业务仓
        （`5176e911`、`0b4b3c07`、`67b889a2`）。

## 规范沉淀
- [x] `.trellis/spec/backend/task-web/backend/hermes-profile.md`：生效 profile 契约、
      prompt 事实源、触发脚本位置（`backend/task-web/trigger/`）与凭证挂载路径。
- [x] `.trellis/spec/backend/task-web/backend/index.md`：Pre-Development Checklist
      补「涉及 AI 任务 profile / 凭证 env_file / jobs.json 挂载 → 必读 hermes-profile.md」。

## 验证命令

- personal-web：`cd backend/task-web && uv run python -m pytest tests/ -q` → 80 passed（2026-11-11 复跑）
- 触发器干跑：`python hermes_trigger.py --job-id 不存在` → exit 2；
  `--job-id pm25` 干跑（HERMES_BASE_URL 指向无效）→ exit 2
- NAS：页面 run 详情（状态/日志/摘要）

## 风险与回滚点

- runs API 字段名以 hermes_client.py 实证为准；若 submit body 字段与实现不符，
  以业务仓已验证代码为准修触发器。
- brief.py 挂载路径变化可能破坏其相对寻址 → 试点执行时核对日志，必要时改用
  `--output-dir` 显式参数。
- 回滚：Hermes 旧 job/crontab 恢复启用即回原链路；task-web 侧删 yaml 条目。
