FROM python:3.12-slim

# 配置国内镜像源
# tzdata：slim 镜像不带 zoneinfo，不装的话 ENV TZ 不生效
RUN sed -i 's|http://deb.debian.org|https://mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources && \
    sed -i 's|http://security.debian.org|https://mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources && \
    apt-get update && \
    apt-get install -y --no-install-recommends curl tzdata && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

ENV TZ=Asia/Shanghai

RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple && \
    pip install uv

WORKDIR /app

# SQLite 数据卷在运行时挂载，不进镜像
COPY pyproject.toml ./
COPY uv.lock ./
COPY src ./src

RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8102

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:${SERVICE_MANAGER_SERVICE_PORT:-8102}/api/health || exit 1

CMD ["sh", "-c", "uvicorn src.main:app --host 0.0.0.0 --port ${SERVICE_MANAGER_SERVICE_PORT:-8102}"]
