# AI Test Platform - Database Setup
# PostgreSQL + SQLAlchemy async + Alembic 迁移

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text

from app.config import settings


# 异步引擎
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_POOL_OVERFLOW,
    pool_pre_ping=True,
)

# 异步 Session 工厂
async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """SQLAlchemy 声明式基类"""
    pass


async def get_db() -> AsyncSession:
    """FastAPI 依赖注入：获取数据库会话"""
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """初始化数据库表"""
    # 可选扩展：单独事务尝试安装，失败不影响核心建表
    for ext in ["vector", "pgcrypto"]:
        try:
            async with engine.begin() as conn:
                await conn.execute(text(f"CREATE EXTENSION IF NOT EXISTS {ext}"))
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Extension {ext} not created (skip): {e}")

    # 创建表结构
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)




async def check_db_health() -> bool:
    """数据库健康检查"""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
