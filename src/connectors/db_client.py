"""
数据库客户端
封装数据库连接和基本 CRUD 操作
"""

from contextlib import contextmanager
from typing import Any, Dict, List, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, Session

from src.common.exceptions import DatabaseException
from src.common.logger import get_logger

logger = get_logger(__name__)


class DBClient:
    """数据库客户端"""

    def __init__(self, connection_string: str, pool_size: int = 5):
        """
        初始化数据库客户端

        Args:
            connection_string: SQLAlchemy 数据库连接字符串
            pool_size: 连接池大小
        """
        self.engine: Engine = create_engine(
            connection_string,
            pool_size=pool_size,
            pool_pre_ping=True,
            echo=False
        )
        self.SessionLocal = sessionmaker(bind=self.engine)
        logger.info("Database client initialized")

    @contextmanager
    def get_session(self) -> Session:
        """
        获取数据库会话（上下文管理器）

        Yields:
            SQLAlchemy Session 对象
        """
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Database session error: {e}")
            raise DatabaseException(f"Database operation failed: {e}")
        finally:
            session.close()

    def execute(
        self,
        sql: str,
        params: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        执行 SQL 查询并返回结果

        Args:
            sql: SQL 语句
            params: 查询参数

        Returns:
            查询结果列表
        """
        with self.get_session() as session:
            try:
                result = session.execute(text(sql), params or {})
                rows = [dict(row._mapping) for row in result]
                logger.debug(f"SQL executed: {sql}, rows returned: {len(rows)}")
                return rows
            except Exception as e:
                logger.error(f"SQL execution failed: {e}\nSQL: {sql}")
                raise DatabaseException(f"Query failed: {e}")

    def execute_update(
        self,
        sql: str,
        params: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        执行更新语句（INSERT/UPDATE/DELETE）

        Args:
            sql: SQL 语句
            params: 查询参数

        Returns:
            受影响的行数
        """
        with self.get_session() as session:
            try:
                result = session.execute(text(sql), params or {})
                logger.debug(f"SQL update executed: {sql}, rows affected: {result.rowcount}")
                return result.rowcount
            except Exception as e:
                logger.error(f"SQL update failed: {e}\nSQL: {sql}")
                raise DatabaseException(f"Update failed: {e}")

    def health_check(self) -> bool:
        """检查数据库连接是否正常"""
        try:
            with self.get_session() as session:
                session.execute(text("SELECT 1"))
            return True
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False
