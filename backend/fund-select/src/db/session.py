"""
数据库 engine / Session / 建表
"""
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.db.models import Base
from src.utils.config import DATA_DIR, get_database_url

DATA_DIR.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    get_database_url(),
    connect_args={"check_same_thread": False},  # SQLite 多线程（FastAPI + 刷新线程）
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db() -> None:
    """建表（幂等，已存在的表不动）"""
    Base.metadata.create_all(engine)


def get_db():
    """FastAPI 依赖：每请求一个 Session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
