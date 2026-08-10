FROM python:3.12-slim

# 配置国内镜像源（阿里云 + 清华 pip）
RUN sed -i 's|http://deb.debian.org|https://mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources && \
    sed -i 's|http://security.debian.org|https://mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources && \
    apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    apt-get clean && rm -rf /var/lib/apt/lists/* && \
    pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple

WORKDIR /app

# 安装 uv
RUN pip install uv

# 复制项目文件
COPY pyproject.toml ./
COPY src ./src
COPY config ./config
COPY main.py ./

# 安装依赖
RUN uv pip install --system -e .

# 创建数据目录
RUN mkdir -p data/output logs

# 暴露端口
EXPOSE 8093

# 健康检查（与 dividend Dockerfile 一致，compose 漏配也能工作）
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8093/health || exit 1

# 启动命令
CMD ["uvicorn", "src.server.main:app", "--host", "0.0.0.0", "--port", "8093"]
