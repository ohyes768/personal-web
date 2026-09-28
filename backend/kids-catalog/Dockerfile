FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .
RUN mkdir -p /app/data /music
EXPOSE 8098
HEALTHCHECK CMD curl -f http://localhost:8098/health || exit 1
CMD ["uvicorn","src.main:app","--host","0.0.0.0","--port","8098"]