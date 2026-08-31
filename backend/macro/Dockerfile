FROM python:3.12-slim

WORKDIR /app

# curl：healthcheck 探针；vim：进容器改 JSON / 排障（slim 默认都不带）
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl vim && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# 安装 uv
RUN pip install --no-cache-dir uv

# 复制项目配置（pyproject.toml + uv.lock 一起，sync 用 lockfile 锁版本）
COPY pyproject.toml uv.lock ./

# 创建虚拟环境并按 lockfile 安装依赖
# --locked: pyproject 与 lock 不一致则构建失败（与 --frozen 互斥，不能同时用）
RUN uv venv .venv
RUN uv sync --locked --no-dev

# 复制源代码
COPY src/ ./src/

# 创建必要的目录
RUN mkdir -p data logs

# 暴露端口
EXPOSE 8094

# 启动命令
CMD [".venv/bin/uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8094"]
