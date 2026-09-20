"""skill-manager FastAPI 入口。

注意：Settings 不在此模块实例化——import app 不应要求环境变量已就绪，
部署入口（uvicorn 启动的进程）在需要时自行构造 Settings。
"""

from fastapi import FastAPI

app = FastAPI(title="skill-manager")


@app.get("/api/health")
def health() -> dict[str, str]:
    """存活探针：无依赖、无状态。"""
    return {"status": "ok"}
