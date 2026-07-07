@echo off
REM AI Test Platform - Windows 快速启动脚本
echo ============================================
echo   AI 测试平台 Phase 1 MVP 启动
echo ============================================
echo.

REM 检查 Python
where python >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] 未找到 Python，请先安装 Python 3.10+
    pause
    exit /b 1
)

REM 进入 backend 目录
cd /d "%~dp0backend"

REM 检查 .env
if not exist ".env" (
    echo [WARN] 未找到 .env 文件，使用 .env.example 作为模板
    copy .env.example .env
    echo [INFO] 请编辑 .env 填入 LLM API Key 等配置后重新运行
    pause
    exit /b 1
)

REM 安装依赖
echo [1/3] 安装 Python 依赖...
pip install -r requirements.txt -q

REM 启动后端
echo [2/3] 启动 FastAPI 后端 (http://localhost:8000)...
start "AI-Test-Platform-Backend" cmd /c "cd /d %~dp0backend && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"

REM 启动前端
echo [3/3] 启动 React 前端 (http://localhost:3000)...
cd /d "%~dp0frontend"
if exist "package.json" (
    echo [INFO] 安装前端依赖...
    call npm install
    start "AI-Test-Platform-Frontend" cmd /c "cd /d %~dp0frontend && npm run dev"
)

echo.
echo ============================================
echo   启动完成！
echo   后端: http://localhost:8000/docs
echo   前端: http://localhost:3000
echo ============================================
pause
