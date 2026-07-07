# AI Test Platform - Backend Configuration
# 支持多环境配置，通过环境变量切换

import os
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv(Path(__file__).parent.parent / ".env", override=True)


class Settings(BaseSettings):
    """平台全局配置"""

    # ========== 应用 ==========
    APP_NAME: str = "AI Test Platform"
    APP_VERSION: str = "0.1.0"
    APP_ENV: str = "dev"
    DEBUG: bool = True
    LOG_LEVEL: str = "DEBUG"
    SECRET_KEY: str = "change-me-in-production"

    # ========== 服务端口 ==========
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # ========== 数据库 (PostgreSQL) ==========
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_NAME: str = "ai_test_platform"
    DB_USER: str = "postgres"
    DB_PASSWORD: str = "postgres"
    DB_POOL_SIZE: int = 10
    DB_POOL_OVERFLOW: int = 20

    @property
    def DATABASE_URL(self) -> str:
        return f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    @property
    def DATABASE_URL_SYNC(self) -> str:
        return f"postgresql+psycopg2://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    # ========== Qdrant 向量库 ==========
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333
    QDRANT_COLLECTION_REQUIREMENTS: str = "requirements"
    QDRANT_COLLECTION_CASES: str = "test_cases"
    QDRANT_VECTOR_SIZE: int = 1536  # OpenAI text-embedding-ada-002

    # ========== Redis / Celery ==========
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # ========== LLM 配置 ==========
    LLM_PROVIDER: str = "openai"  # openai | anthropic | qwen (通义千问)

    # OpenAI
    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    OPENAI_MODEL_STRONG: str = "gpt-4o"      # 生成用例、分析
    OPENAI_MODEL_MEDIUM: str = "gpt-4o-mini"  # 辅助任务
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"

    # Anthropic Claude
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL_STRONG: str = "claude-3-5-sonnet-20241022"
    ANTHROPIC_MODEL_MEDIUM: str = "claude-3-haiku-20240307"

    # 通义千问
    QWEN_API_KEY: str = ""
    QWEN_MODEL_STRONG: str = "qwen-max"
    QWEN_MODEL_MEDIUM: str = "qwen-plus"

    # LLM 通用
    LLM_TEMPERATURE_GENERATE: float = 0.3  # 生成任务低温度保证一致性
    LLM_TEMPERATURE_ANALYZE: float = 0.1   # 分析任务更低温度
    LLM_MAX_TOKENS_GENERATE: int = 4096
    LLM_REQUEST_TIMEOUT: int = 120

    # ========== 向量模型 (本地) ==========
    EMBEDDING_LOCAL_MODEL: str = "BAAI/bge-small-zh-v1.5"  # 备选本地方案

    # ========== 文件存储 ==========
    STORAGE_DIR: str = str(Path(__file__).parent.parent / "storage")
    EXPORT_DIR: str = str(Path(__file__).parent.parent / "storage" / "exports")
    EVIDENCE_DIR: str = str(Path(__file__).parent.parent / "storage" / "evidence")

    # ========== 导出 ==========
    EXPORT_FORMATS: list[str] = ["json", "xlsx", "xmind", "markdown"]

    # ========== 需求结构化 Schema ==========
    REQUIREMENT_ENTITY_FIELDS: list[str] = [
        "feature_id", "title", "module", "description",
        "functional_points", "participants", "trigger_conditions",
        "expected_outcomes", "constraints", "data_scope",
        "pages", "apis", "roles", "business_terms"
    ]

    class Config:
        env_file = ".env"
        case_sensitive = True


# 全局单例
settings = Settings()
