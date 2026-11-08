# Hermes AI 任务触发镜像（task-web docker 引擎按次拉起）
# 职责：读 prompt（HERMES_PROMPT 首选，jobs.json 回退）→ Runs API 提交 → 轮询到终态。
# 它是 task-web 的执行基础设施，与业务仓库无关；由 deploy-nas.sh task-web 构建。
FROM python:3.12-slim
RUN pip install --no-cache-dir requests
WORKDIR /app
COPY hermes_trigger.py .
CMD ["python", "hermes_trigger.py"]
