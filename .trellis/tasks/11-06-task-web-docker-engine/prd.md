# task-web docker 执行引擎（方案 B）

来源：11-05-task-web-cron-manager 实施中发现的依赖漂移问题（a-stock-push 容器内缺 requests）。

## Goal

业务脚本与依赖由业务仓库（stock-info-dingding）独立维护并自建镜像；task-web 只负责定时调度与按次执行（docker run），平台镜像不再混入业务依赖。

用户决策：方案 B（2026-11-06）。现有业务仓库已有 Dockerfile + requirements.txt（python:3.11-slim，WORKDIR /app），NAS 只需 `docker build -t stock-info:latest .`。

## Requirements

- tasks.yaml 任务支持 `engine: docker`（默认 shell 向后兼容）+ `image` + `env_file`（宿主机路径，KEY=VALUE）+ `env`（明文非密变量）。
- executor 按 engine 分派；docker 引擎经 docker.sock（Python SDK）创建一次性容器执行，stdout/stderr 分流写入 run 日志，超时 kill 容器，退出码/状态语义与 shell 引擎一致。
- env_file/env 的值不回显到页面、不写日志（密钥红线）。
- task-web-backend 容器挂载 /var/run/docker.sock（NAS 单用户环境，接受该权限）。
- tasks 表新增列迁移（engine/image/env_file/env），旧数据默认 engine=shell 行为不变。

## Acceptance Criteria

- [ ] shell 引擎行为不变（既有测试 9/9 通过）。
- [ ] docker 引擎：fake client 测试验证容器参数（image/command/env/working_dir）、超时 kill、退出码映射；密钥不进日志。
- [ ] a-stock-push 登记切换为 engine=docker，NAS 构建 stock-info 镜像后手动执行验证。
- [ ] compose 挂载 docker.sock。

## Out of Scope

- 多镜像仓库/registry 推送；镜像自动构建（NAS 手动 build）。
- docker-compose 方式执行；GPU/资源限制参数。

## Notes

- docker 引擎 cwd 语义变为容器内 working_dir（默认镜像 WORKDIR，可绝对路径覆盖）。
