"""
daily-review 入口：uvicorn 从项目根跑 src.main:app
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src import db
from src.api.routes import router
from src.config import get_server_host, get_server_port


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    yield


app = FastAPI(
    title="daily-review",
    description="每日工作回顾服务：两机 DSH 会话/任务板/git commit 汇聚 + LLM 日报周报",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("src.main:app", host=get_server_host(), port=get_server_port())
