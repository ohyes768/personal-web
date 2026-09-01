FROM python:3.12-slim

# 配置国内镜像源
# tzdata：slim 镜像不带 zoneinfo，不装的话 ENV TZ 不生效（datetime.now() 会停在 UTC）
RUN sed -i 's|http://deb.debian.org|https://mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources && \
    sed -i 's|http://security.debian.org|https://mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources && \
    apt-get update && \
    apt-get install -y --no-install-recommends curl tzdata && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# 容器时区设为北京时间，保证 datetime.now() / 文件 mtime 序列化输出为本地时间
ENV TZ=Asia/Shanghai

# 配置 pip 国内镜像源
RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple

# 安装 uv
RUN pip install uv

WORKDIR /app

# 复制项目文件
COPY pyproject.toml ./
COPY uv.lock ./
COPY config ./config
COPY src ./src

# 安装依赖（uv sync 从 lock 文件精确安装，比 pip install -e . 可靠）
RUN uv sync --frozen --no-dev

# 将 venv 加入 PATH，后续 CMD 直接使用 venv 中的 uvicorn
ENV PATH="/app/.venv/bin:$PATH"

# 创建数据/缓存/日志目录
RUN mkdir -p data logs cache

# 暴露端口（容器内监听端口；实际端口从 SERVER_PORT 读）
EXPOSE 8095

# 健康检查：命中 /api/funds/health（router prefix = /api/funds，path = /health）
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD sh -c "curl -f http://localhost:${SERVER_PORT:-8095}/api/funds/health || exit 1"

# 启动命令
# 端口从 SERVER_PORT 读（与 src/utils/config.py 一致），未设置时 fallback 8095
CMD ["sh", "-c", "uvicorn src.main:app --host 0.0.0.0 --port ${SERVER_PORT:-8095}"]
