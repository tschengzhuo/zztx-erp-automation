# AI Test Platform - FastAPI Application Entry
# Phase 1 MVP: 需求→用例 单链路

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from pathlib import Path

from app.config import settings
from app.database import init_db, check_db_health
from app import models  # noqa: F401 导入模型以注册 metadata
from app.api import requirements, test_points, test_cases, entities, categories, auth


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期"""
    # 启动时
    os.makedirs(settings.EXPORT_DIR, exist_ok=True)
    os.makedirs(settings.EVIDENCE_DIR, exist_ok=True)

    # 确保 SQLite 数据库目录存在
    if settings.is_sqlite:
        db_name = settings.DB_NAME if settings.DB_NAME.endswith(".db") else f"{settings.DB_NAME}.db"
        db_path = Path(db_name) if Path(db_name).is_absolute() else Path(__file__).parent.parent / db_name
        os.makedirs(db_path.parent, exist_ok=True)

    # 尝试初始化数据库
    try:
        await init_db()
        print(f"[OK] Database initialized: {settings.DB_NAME}")

        # 种子数据（首次部署时自动插入演示数据）
        from app.database import async_session
        from app.seed import seed_database
        async with async_session() as session:
            await seed_database(session)
            await session.commit()
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
app.include_router(categories.router)
app.include_router(auth.router)


# ==================== 基础 API ====================

@app.api_route("/", methods=["GET", "HEAD"])
async def root(request: Request):
    """服务根路径：CloudStudio HEAD 健康检查 / 浏览器 GET 返回 SPA"""
    import os as _os
    from fastapi.responses import FileResponse as _FileResponse
    _STATIC_DIR = _os.path.join(_os.path.dirname(_os.path.dirname(__file__)), "static")

    if request.method == "HEAD":
        return {"name": settings.APP_NAME, "version": settings.APP_VERSION, "status": "ok"}

    if _os.path.isdir(_STATIC_DIR) and _os.path.isfile(_os.path.join(_STATIC_DIR, "index.html")):
        return _FileResponse(_os.path.join(_STATIC_DIR, "index.html"))

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


# ==================== 静态文件（CloudStudio / 生产环境） ====================
import os as _os
from fastapi.responses import FileResponse as _FileResponse

_STATIC_DIR = _os.path.join(_os.path.dirname(_os.path.dirname(__file__)), "static")
if _os.path.isdir(_STATIC_DIR):
    # 确保 API 路由优先于静态文件
    @app.get("/{full_path:path}")
    async def _serve_spa(full_path: str):
        file_path = _os.path.join(_STATIC_DIR, full_path)
        if full_path and _os.path.isfile(file_path):
            return _FileResponse(file_path)
        return _FileResponse(_os.path.join(_STATIC_DIR, "index.html"))
