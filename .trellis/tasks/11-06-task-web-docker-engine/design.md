# task-web docker 执行引擎 设计

## 分派模型

- `executor.start_run(task)` 不变；`execute_run` 按 `task.get("engine", "shell")` 分派：
  - shell → 现有 subprocess 路径
  - docker → `execute_docker_run(run_id, task, timeout)`
- docker 客户端经 `_get_docker_client()`（docker.from_env()，读 DOCKER_HOST/默认 unix socket）；测试 monkeypatch 注入 fake。

## docker 执行流

1. 组装 env：`env_file`（KEY=VALUE 逐行，忽略 #注释/空行）+ `env` 映射；值不写日志。
2. `client.containers.run(image, command, detach=True, environment=env, working_dir=..., stdout=True, stderr=True)`。
3. `container.logs(stream=True, follow=True, demux=True)` 循环写 `<run_id>.out/.err`。
4. `container.wait(timeout=remaining)` → `StatusCode` 0=success 非 0=failed；TimeoutExpired → `container.kill()` → status=timeout。
5. finally `container.remove(force=True)` 兜底清理（run 一次性，不等 auto-remove）。
6. duration/started/finished 与 shell 引擎同构，DB 状态机复用。

## 数据迁移

tasks 表追加列：`engine TEXT DEFAULT 'shell'`、`image TEXT`、`env_file TEXT`、`env TEXT`（JSON 字符串）。init_db 里 PRAGMA table_info 检查缺失即 ALTER TABLE ADD COLUMN（SQLite 兼容，旧卷无损升级）。

## compose

task-web-backend volumes 增 `/var/run/docker.sock:/var/run/docker.sock`；注释写明该挂载等价宿主机 root 的边界与理由。

## 安全

- env 值仅经 SDK 传给容器；API/日志均不输出；页面任务详情只显示 image/engine/env_file 路径。
