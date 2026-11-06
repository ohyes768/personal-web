# task-web docker 执行引擎 实施计划

前置：prd/design 就绪（2026-11-06）。

## 实施顺序

1. db.py：tasks 表加列迁移（engine/image/env_file/env）+ upsert/list 透传。
2. registry.py：tasks.yaml 新字段读取透传（engine 默认 shell）。
3. executor.py：engine 分派 + execute_docker_run（SDK 容器执行、demux 日志、超时 kill、容器清理、env 值不落日志）。
4. tasks.yaml：a-stock-push 切 engine=docker（image stock-info:latest，env PUSH_MODE=1，env_file 指向业务 .env）。
5. docker-compose.nas.yml：task-web-backend 挂载 docker.sock。
6. pyproject：加 docker SDK 依赖，uv lock。
7. tests/test_engine.py：fake client 验证容器参数/超时/退出码映射/env 解析。
8. 验证：pytest 全绿 → commit/push。

## NAS 侧（用户执行）

- `cd /home/ohyes768/stock-info-dingding && docker build -t stock-info:latest .`
- `git pull && ./scripts/deploy-nas.sh task-web` 重建
- 页面手动执行 a-stock-push 验证

## 回滚点

- executor 分派独立提交可整体 revert；tasks 表新列可空、旧镜像照跑。
- docker.sock 挂载单独一行，删除即回 shell 引擎模式。
