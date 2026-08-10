"""
douyin-processor 主入口
"""

import uvicorn

from src.utils import setup_logger, load_config

# 加载配置
config = load_config("config/app.yaml")

# 设置日志
log_config = config.get("app", {}).get("logging", {})
setup_logger(
    log_dir=log_config.get("dir", "logs"),
    level=log_config.get("level", "INFO")
)

if __name__ == "__main__":
    from loguru import logger

    server_config = config.get("app", {}).get("server", {})
    host = server_config.get("host", "0.0.0.0")
    port = server_config.get("port", 8093)

    logger.info(f"启动 douyin-processor 服务: http://{host}:{port}")

    uvicorn.run(
        "src.server.main:app",
        host=host,
        port=port,
        log_level="info",
        reload=False
    )
