FROM python:3.12-slim

# 配置国内镜像源
# tzdata：slim 镜像不带 zoneinfo，不装的话 ENV TZ 不生效（datetime.now() 会停在 UTC）
RUN sed -i 's|http://deb.debian.org|https://mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources && \
    sed -i 's|http://security.debian.org|https://mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources && \
    apt-get update && \
    apt-get install -y --no-install-recommends curl tzdata && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# 容器时区设为北京时间，保证 datetime.now() / 楼龄计算 / 文件时间戳为本地时间
ENV TZ=Asia/Shanghai

# 配置 pip 国内镜像源
RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple

# 安装 uv
RUN pip install uv

WORKDIR /app

# 复制项目文件（数据随镜像分发到 /app/data，运行时由 named volume 持久化 refresh 写入）
COPY pyproject.toml ./
COPY uv.lock ./
COPY src ./src
COPY scripts ./scripts
COPY data ./data
# 已存在的 named volume 会遮住 /app/data；保留轮廓重建所需的只读种子副本，启动时按需补齐。
COPY data/binjiang_osm_residential.geojson ./seed-data/binjiang_osm_residential.geojson

# 安装依赖（uv sync 从 lock 文件精确安装）
RUN uv sync --frozen --no-dev

# 将 venv 加入 PATH，后续 CMD 直接使用 venv 中的 uvicorn
ENV PATH="/app/.venv/bin:$PATH"

# 创建日志目录
RUN mkdir -p logs

# 暴露端口（容器内监听端口；实际端口从 HOUSING_PORT 读）
EXPOSE 8096

# 健康检查：命中 /api/health（router prefix = /api，path = /health）
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD sh -c "curl -f http://localhost:${HOUSING_PORT:-8096}/api/health || exit 1"

# 启动命令（端口从 HOUSING_PORT 读，未设置时 fallback 8096）
CMD ["sh", "-c", "if [ ! -f /app/data/binjiang_osm_residential.geojson ]; then cp /app/seed-data/binjiang_osm_residential.geojson /app/data/; fi; exec uvicorn src.main:app --host 0.0.0.0 --port ${HOUSING_PORT:-8096}"]
