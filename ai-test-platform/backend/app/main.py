# AI Test Platform - FastAPI Application Entry
# Phase 1 MVP: 需求→用例 单链路

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.database import init_db, check_db_health
from app.api import requirements, test_points, test_cases, entities


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期"""
    # 启动时
    os.makedirs(settings.EXPORT_DIR, exist_ok=True)
    os.makedirs(settings.EVIDENCE_DIR, exist_ok=True)

    # 尝试初始化数据库
    try:
        await init_db()
        print(f"[OK] Database initialized: {settings.DB_NAME}")
    except Exception as e:
        print(f"[WARN] Database init skipped (will retry on first request): {e}")

    print(f"[OK] AI Test Platform v{settings.APP_VERSION} started")
    print(f"     LLM Provider: {settings.LLM_PROVIDER}")
    print(f"     Env: {settings.APP_ENV}")
    print(f"     http://{settings.HOST}:{settings.PORT}/docs")

    yield

    # 关闭时
    print("[OK] AI Test Platform shutting down")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="AI 测试平台 · 从需求到用例的自动化生成 · Phase 1 MVP",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(requirements.router)
app.include_router(test_points.router)
app.include_router(test_cases.router)
app.include_router(entities.router)


# ==================== 基础 API ====================

@app.get("/", response_model=dict)
async def root():
    """服务根路径"""
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "env": settings.APP_ENV,
        "llm_provider": settings.LLM_PROVIDER,
        "docs": "/docs",
    }


@app.get("/api/health", response_model=dict)
async def health_check():
    """健康检查"""
    db_ok = await check_db_health()
    return {
        "status": "healthy" if db_ok else "degraded",
        "database": "connected" if db_ok else "disconnected",
        "version": settings.APP_VERSION,
    }


@app.get("/api/stats", response_model=dict)
async def platform_stats():
    """平台统计"""
    return {
        "stages": {
            1: "需求读取 (解析+指纹生成)",
            2: "测试点生成 (RAG增强+7维度覆盖)",
            3: "结构化用例转换 (UI+API双形态)",
            4: "UI 步骤执行 (Playwright) - Phase 2",
            5: "接口请求执行 (Playwright API) - Phase 2",
            6: "失败原因分析 (LLM多模态) - Phase 3",
            7: "回归资产沉淀 (CI闭环) - Phase 4",
        },
        "cross_cutting": {
            "A": "需求精准定位 (5路召回+置信度融合) - Phase 1.0",
            "B": "需求迭代用例同步 (语义diff+Merge) - Phase 1.5",
        },
        "current_phase": "Phase 1 MVP",
        "supported_exports": ["json", "xlsx", "xmind", "markdown"],
    }


# ==================== 全局异常处理 ====================

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """全局异常处理"""
    return JSONResponse(
        status_code=500,
        content={"success": False, "message": str(exc), "data": None},
    )
