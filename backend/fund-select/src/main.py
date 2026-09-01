"""
FastAPI 应用入口
fund-select 后端服务
"""
import sys
from contextlib import asynccontextmanager
from pathlib import Path

# 加载 .env / .env.local（在所有 import 之前，确保 os.getenv 读到值）
try:
    from dotenv import load_dotenv
    PROJECT_ROOT = Path(__file__).parent.parent
    load_dotenv(PROJECT_ROOT / ".env")
    load_dotenv(PROJECT_ROOT / ".env.local", override=True)  # .env.local 优先级最高
except ImportError:
    pass  # 没装 python-dotenv 也不报错，走 os.getenv 默认值

# 添加项目根目录到 Python 路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import router
from src.db.session import init_db
from src.scheduler.manager import SchedulerManager
from src.utils.config import get_server_host, get_server_port
from src.utils.logger import setup_logger

logger = setup_logger("fund-select")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=" * 50)
    logger.info("fund-select 服务启动中...")
    logger.info(f"地址: {get_server_host()}:{get_server_port()}")
    logger.info("=" * 50)

    # 建表（幂等）
    init_db()

    # 启动定时调度（每日刷新配置名单）
    scheduler = SchedulerManager()
    scheduler.start(app)
    app.state.scheduler = scheduler

    yield

    logger.info("fund-select 服务关闭中...")
    await scheduler.shutdown(wait=False)


app = FastAPI(
    title="Fund Select API",
    description="债基筛选平台 API（31 只精选基金）",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api/funds")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.main:app",
        host=get_server_host(),
        port=get_server_port(),
        reload=False,
        log_level="info",
    )
