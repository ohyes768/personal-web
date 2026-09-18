"""FastAPI 应用入口 — housing-map 后端服务"""

import logging
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

logger = logging.getLogger("housing-map")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=logging.INFO)
    logger.info("=" * 50)
    logger.info("housing-map 服务启动中...")
    logger.info("=" * 50)
    yield
    logger.info("housing-map 服务关闭中...")


app = FastAPI(
    title="Housing Map API",
    description="滨江购房地图 API（小区评分 / 地铁裁剪 / 价格快照刷新）",
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

# nginx 将 /api/map/* 剥前缀转成 /api/* 直转本服务，故 prefix 固定为 /api
app.include_router(router, prefix="/api")


if __name__ == "__main__":
    import os

    import uvicorn

    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=int(os.getenv("HOUSING_PORT", "8096")),
        reload=False,
    )
