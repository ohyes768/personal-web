"""
数据库 engine / Session / 建表 / 老库列升级
"""
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from src.db.models import Base
from src.utils.config import DATA_DIR, get_database_url
from src.utils.logger import setup_logger

logger = setup_logger("fund-select.session")

DATA_DIR.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    get_database_url(),
    connect_args={"check_same_thread": False},  # SQLite 多线程（FastAPI + 刷新线程）
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db() -> None:
    """建表（幂等，已存在的表不动）+ 老库列升级"""
    Base.metadata.create_all(engine)
    _ensure_market_type_column(engine)


def _ensure_market_type_column(engine) -> None:
    """funds.market_type 列：旧库（PR 之前）需要 ALTER TABLE；新库由 create_all 创建。

    SQLite 不支持 ADD COLUMN IF NOT EXISTS，所以用 PRAGMA table_info 查询列存在性。
    """
    with engine.begin() as conn:
        rows = conn.execute(text("PRAGMA table_info(funds)")).fetchall()
        col_names = {row[1] for row in rows}
        if "market_type" not in col_names:
            conn.execute(text("ALTER TABLE funds ADD COLUMN market_type VARCHAR(64)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_funds_market_type ON funds(market_type)"))
            logger.info("funds.market_type 列已添加（旧库升级）")


def get_db():
    """FastAPI 依赖：每请求一个 Session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
