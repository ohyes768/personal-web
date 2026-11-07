# hermes 统一触发 实施计划

前置：prd/design 就绪，两项决策已定（2026-11-07）。

## 实施顺序

### Phase 1 触发器（stock-info-dingding 仓库）
1. `hermes_trigger.py`：参数解析、jobs.json 查找（id 精确/name 兜底）、Runs API 提交（Idempotency-Key）、轮询终态、退出码映射（0=completed / 1=失败终态 / 2=配置或提交错误 / 3=轮询超时）、stdout 摘要。
2. 干跑自测：无 key / 错 base_url / 不存在 job-id 三类错误路径本地验证（不真调 API）。
3. 该仓库独立 commit（它是独立 git 仓库）。

### Phase 2 task-web volumes 支持（personal-web）
4. db.py tasks 表加 `volumes TEXT` 列迁移；registry 透传（yaml 数组→JSON 入库）。
5. executor：docker 分支传 volumes 参数（mode 解析，默认 ro）；fake client 测试断言 volumes 传递与非法格式报错。
6. tasks.yaml 试点登记：csi300-brief（`35 16 * * 1-5`）+ pm25-broadcast（`45 23,3,9 * * *`），均默认禁用、写明旧触发禁用步骤。
7. pytest 全绿 → commit/push。

### Phase 3 NAS 验证（用户操作）
8. stock-info-dingding git pull + `docker build -t stock-info:latest .`；personal-web git pull + `./scripts/deploy-nas.sh task-web`。
9. 页面手动执行 pm25-broadcast → 验证微信收到 + run completed；手动执行 csi300-brief → 验证钉钉收到 + 状态语义。
10. 验证通过：Hermes 侧旧 job `enabled=false`（pm25）+ crontab 注释 CSI300 旧条目 → 页面启用两个任务正式计划。

## 验证命令

- personal-web：`cd backend/task-web && uv run python -m pytest tests/ -q`
- stock-info-dingding：`python hermes_trigger.py --job-id 不存在` → exit 2；`--job-id pm25 干跑（HERMES_BASE_URL 指向无效）` → exit 2
- NAS：页面 run 详情（状态/日志/摘要）

## 风险与回滚点

- runs API 字段名以 hermes_client.py 实证为准；若 submit body 字段与实现不符，以业务仓已验证代码为准修触发器。
- brief.py 挂载路径变化可能破坏其相对寻址 → 试点执行时核对日志，必要时改用 `--output-dir` 显式参数。
- 回滚：Hermes 旧 job/crontab 恢复启用即回原链路；task-web 侧删 yaml 条目。
