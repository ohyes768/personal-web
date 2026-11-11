# Hermes AI 任务触发镜像（task-web docker 引擎按次拉起）
# 职责：读 HERMES_PROMPT（唯一 prompt 来源，2026-11-11 起 jobs.json 回退已移除）
# → Runs API 提交 → 轮询到终态。无 CLI 参数，无卷挂载。
# 它是 task-web 的执行基础设施，与业务仓库无关；由 deploy-nas.sh task-web 构建。
FROM python:3.12-slim
RUN pip install --no-cache-dir requests
WORKDIR /app
COPY hermes_trigger.py .
CMD ["python", "hermes_trigger.py"]
