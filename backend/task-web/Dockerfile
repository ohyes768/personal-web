FROM python:3.12-slim

# tzdata：slim 镜像不带 zoneinfo；容器时区固定北京时间（调度时区契约）
RUN sed -i 's|http://deb.debian.org|https://mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources && \
    sed -i 's|http://security.debian.org|https://mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources && \
    apt-get update && \
    apt-get install -y --no-install-recommends curl tzdata && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

ENV TZ=Asia/Shanghai

RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple && \
    pip install uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY tasks.yaml ./
COPY src ./src

RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"

RUN mkdir -p data/logs

EXPOSE 8101

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:${TASK_WEB_PORT:-8101}/api/health || exit 1

CMD ["sh", "-c", "uvicorn src.main:app --host 0.0.0.0 --port ${TASK_WEB_PORT:-8101}"]
