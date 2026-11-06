"""
task-web 后端入口
"""
import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

try:
    from dotenv import load_dotenv

    PROJECT_ROOT = Path(__file__).parent.parent
    load_dotenv(PROJECT_ROOT / ".env")
    load_dotenv(PROJECT_ROOT / ".env.local", override=True)
except ImportError:
    pass

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api import routes
from src.api.routes import router
from src.config import get_server_host, get_server_port, get_timezone
from src.db import init_db
from src.registry import sync_registry
from src.scheduler import TaskScheduler

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("task-web")

scheduler = TaskScheduler(timezone=get_timezone())


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    registered = sync_registry()
    logger.info("任务登记同步完成: %s", registered)
    scheduler.start()
    routes.scheduler = scheduler
    logger.info("task-web 启动完成 http://%s:%s", get_server_host(), get_server_port())
    yield
    scheduler.shutdown()


app = FastAPI(title="task-web", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router, prefix="/api")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("src.main:app", host=get_server_host(), port=get_server_port(), reload=True)
