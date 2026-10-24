FROM python:3.12-slim

# 配置国内镜像源，与其他后端一致（slim 直连 deb.debian.org 构建极慢）
RUN sed -i 's|http://deb.debian.org|https://mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources && \
    sed -i 's|http://security.debian.org|https://mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources && \
    apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# 配置 pip 国内镜像源
RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .
RUN mkdir -p /app/data /music
EXPOSE 8098
HEALTHCHECK CMD curl -f http://localhost:8098/health || exit 1
CMD ["uvicorn","src.main:app","--host","0.0.0.0","--port","8098"]