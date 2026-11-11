# hermes 统一触发 技术设计

决策依据：prd.md（触发器进 stock-info-dingding 镜像；jobs.json 只读挂载为单一事实源）。

## 组件与数据流

```
task-web (docker engine)
  └─ stock-info:latest 容器
       ├─ 普通任务: python brief.py ...（skills 目录 ro 挂载）
       └─ hermes_trigger.py --job-id <id>
            ├─ 读 /hermes-cron/jobs.json 取 prompt（ro 挂载）
            ├─ POST {HERMES_BASE_URL}/p/{profile}/v1/runs（Bearer + Idempotency-Key）
            ├─ 轮询 GET /v1/runs/{run_id} 至终态
            └─ completed→exit 0 + stdout 摘要；其余→非 0 + 错误详情
```

## hermes_trigger.py（stock-info-dingding 仓库根）

- `--job-id <id>`：jobs.json 中匹配 id 或 name 含糊匹配（二者其一即可，id 优先）。
- env 复用既有约定：`HERMES_BASE_URL/API_KEY/PROFILE/POLL_INTERVAL/TIMEOUT`（与 hermes_client.py 相同）。
- 提交 body：`{"prompt": <job.prompt>, "idempotency_key": <uuid>}`；HTTP 错误/缺 key/找不到 job → stderr 明确报错，exit 2。
- 轮询：间隔 POLL_INTERVAL 秒，总超时 TIMEOUT（默认 1800s，AI run 较长）；超时 exit 3；终态映射 completed→0，failed/cancelled/interrupted→1 并打印服务端错误信息。
- stdout 打印：开始时间、run_id、终态、结果文本最后 500 字符摘要。**API key 永不打印**。
- 幂等：每次执行新 Idempotency-Key（task-web 层已有互斥防重，此处防同 run 重复提交）。

## task-web 侧改动

1. **executor docker 引擎 volumes**：tasks.yaml `volumes: ["src:dst:mode"]` → db tasks 加列 `volumes TEXT`（JSON 数组）→ containers.run(volumes=[...])；mode 默认 ro。沿用方案 B 既有模式，env/密钥红线不变。
2. **registry**：透传 volumes 字段（JSON 序列化入库）。
3. **tasks.yaml 试点登记**（默认 enabled 由用户页面启用）：

```yaml
- id: csi300-brief
  engine: docker
  image: stock-info:latest
  command: python /hermes-skills/investment-analysis/csi300-brief/scripts/brief.py --push --insecure --only-today
  volumes: ["${CSI300_SKILLS_HOST_PATH:-/home/ohyes768/skills}:/hermes-skills:ro"]
  cron: "35 16 * * 1-5"    # 北京 16:35（旧 crontab 为 UTC 8:35）
  timeout: 900

- id: pm25-broadcast
  engine: docker
  image: stock-info:latest
  command: python hermes_trigger.py --job-id 246c69c1e845
  volumes: ["${HERMES_CRON_HOST_PATH:-/home/ohyes768/.hermes/cron}:/hermes-cron:ro"]
  cron: "45 23,3,9 * * *"
  timeout: 2100
```

注意：compose 的 build-only `stock-info-image` 无法插值任务卷（卷在任务运行时由 task-web 容器发起），因此 volumes 源路径在 tasks.yaml 里写 NAS 宿主机绝对路径（docker engine 起容器时由宿主机 docker 解析）——环境变量插值在 task-web 后端不生效，直接写默认值，注释说明。

4. **compose**：task-web-backend volumes 追加两条（env var 可覆盖默认）：
   - `${CSI300_SKILLS_HOST_PATH:-/home/ohyes768/skills}:/hermes-skills-registry:ro`? 
   
   ——不需要：任务卷由 docker 引擎按 tasks.yaml 直接挂宿主机路径，task-web 容器自身只挂 jobs.json 触发器要读的吗？也不需要（读 jobs.json 的是 stock-info 容器，不是 task-web）。**结论：task-web-backend 不加新卷**，只有 tasks.yaml 声明任务级 volumes，由 executor 起的容器挂载。compose 仅保留既有挂载。
5. **PM2.5 job id**：246c69c1e845（2026-11-07 实测读取，若 Hermes 侧重建 job 需同步改）。

## 与既有机制的契合

- 互斥：AI run 长耗时，重复触发被 skipped 记录拦截。
- 不补跑：错过即错过，页面手动触发；Idempotency-Key 每次 run 独立。
- 重启恢复：running→interrupted，不会把 AI run 永久挂起。
- 日志：stdout/stderr 分流照旧；API key 只经 env 进容器，不回显。

## 回滚

- tasks.yaml 删条目 + 页面禁用即下线；Hermes 旧 job 置回 enabled=true 恢复原调度。
- executor volumes 支持独立 revert，shell/docker 既有路径不受影响。
