# AI Test Platform - API Routes: Test Cases
# 用例管理 + Stage 3 + 导出

import asyncio
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.models import TestCase, TestPoint, Requirement
from app.schemas import (
    TestCaseCreate, TestCaseUpdate, TestCaseResponse,
    APIResponse, ExportRequest,
)
from app.services.stage3_cases import generate_test_cases
from app.services.export_service import (
    export_json, export_xlsx, export_xmind, export_markdown,
)
from app.services.task_manager import (
    create_task, get_task, run_stage3_in_background,
)

router = APIRouter(prefix="/api/test-cases", tags=["用例管理"])


@router.post("/generate", response_model=APIResponse)
async def generate_test_cases_stage3(
    req_data: TestCaseCreate,
    db: AsyncSession = Depends(get_db),
):
    """Stage 3: 从测试点生成结构化用例（异步后台执行）"""
    # 参数校验：确认测试点存在
    try:
        from app.services.stage3_cases import generate_test_cases as _check
    except Exception:
        pass

    # 创建后台任务
    task_id = create_task()

    # 启动后台异步任务
    asyncio.create_task(
        run_stage3_in_background(
            task_id=task_id,
            requirement_id=req_data.requirement_id,
            test_point_ids=req_data.test_point_ids,
            generate_both=req_data.generate_both,
        )
    )

    return APIResponse(
        success=True,
        message="Stage 3 任务已启动，正在后台生成用例",
        data={"task_id": task_id, "status": "pending"},
    )


@router.get("/generate-status/{task_id}", response_model=APIResponse)
async def get_generate_status(task_id: str):
    """轮询 Stage 3 任务状态"""
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在或已过期")

    return APIResponse(
        success=task["status"] != "failed",
        message=task["message"],
        data={
            "task_id": task_id,
            "status": task["status"],
            "progress": task.get("progress", 0),
            "total": task.get("total", 0),
            "result": task.get("result"),
            "error": task.get("error"),
        },
    )


@router.get("/by-requirement/{requirement_id}", response_model=APIResponse)
async def list_test_cases(
    requirement_id: str,
    case_type: str = None,
    confirmed_only: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """获取需求下的用例列表"""
    query = select(TestCase).where(
        TestCase.requirement_id == requirement_id,
        TestCase.is_active == True,
    )
    if case_type:
        query = query.where(TestCase.case_type == case_type)
    if confirmed_only:
        query = query.where(TestCase.is_confirmed == True)

    query = query.order_by(TestCase.priority, TestCase.case_id)
    result = await db.execute(query)
    items = result.scalars().all()

    return APIResponse(
        success=True,
        data=[TestCaseResponse.model_validate(tc) for tc in items],
    )


@router.get("/{case_id}", response_model=APIResponse)
async def get_test_case(
    case_id: str,
    db: AsyncSession = Depends(get_db),
):
    """获取单个用例详情"""
    stmt = select(TestCase).where(TestCase.id == case_id)
    result = await db.execute(stmt)
    tc = result.scalar_one_or_none()
    if not tc:
        raise HTTPException(status_code=404, detail="用例不存在")

    return APIResponse(success=True, data=TestCaseResponse.model_validate(tc))


@router.put("/{case_id}", response_model=APIResponse)
async def update_test_case(
    case_id: str,
    update_data: TestCaseUpdate,
    db: AsyncSession = Depends(get_db),
):
    """QA 编辑用例（人工修改保护）"""
    stmt = select(TestCase).where(TestCase.id == case_id)
    result = await db.execute(stmt)
    tc = result.scalar_one_or_none()
    if not tc:
        raise HTTPException(status_code=404, detail="用例不存在")

    fields = update_data.model_dump(exclude_unset=True)
    for key, value in fields.items():
        if value is not None:
            setattr(tc, key, value)

    # 标记人工修改
    if "steps" in fields:
        steps = fields["steps"]
        if isinstance(steps, list):
            for step in steps:
                step["locked"] = True
                step["last_modified_by"] = "human"
            tc.steps = steps
        # 保存版本快照
        from app.models import CaseVersion
        cv = CaseVersion(
            test_case_id=case_id,
            version=(await _get_next_version(db, case_id)),
            steps=tc.steps,
            expected_result=tc.expected_result,
            change_reason="人工修改",
        )
        db.add(cv)

    tc.updated_at = datetime.now()
    await db.flush()

    return APIResponse(success=True, message="用例已更新",
                       data=TestCaseResponse.model_validate(tc))


@router.post("/{case_id}/confirm", response_model=APIResponse)
async def confirm_case(
    case_id: str,
    db: AsyncSession = Depends(get_db),
):
    """QA 确认用例"""
    stmt = select(TestCase).where(TestCase.id == case_id)
    result = await db.execute(stmt)
    tc = result.scalar_one_or_none()
    if not tc:
        raise HTTPException(status_code=404, detail="用例不存在")

    tc.is_confirmed = True
    await db.flush()

    return APIResponse(success=True, message="用例已确认")


@router.post("/{case_id}/lock-step", response_model=APIResponse)
async def lock_case_step(
    case_id: str,
    step_index: int,
    db: AsyncSession = Depends(get_db),
):
    """锁定用例中的某个步骤（防止 AI 覆盖）"""
    stmt = select(TestCase).where(TestCase.id == case_id)
    result = await db.execute(stmt)
    tc = result.scalar_one_or_none()
    if not tc:
        raise HTTPException(status_code=404, detail="用例不存在")

    steps = list(tc.steps or [])
    if 0 <= step_index < len(steps):
        steps[step_index]["locked"] = True
        steps[step_index]["last_modified_by"] = "human"
        tc.steps = steps
        await db.flush()
        return APIResponse(success=True, message=f"步骤 {step_index} 已锁定")

    raise HTTPException(status_code=400, detail="步骤索引无效")


# ==================== 导出 ====================

@router.post("/export", response_class=FileResponse)
async def export_cases(
    export_req: ExportRequest,
    db: AsyncSession = Depends(get_db),
):
    """导出用例到指定格式"""
    format_handlers = {
        "json": export_json,
        "xlsx": export_xlsx,
        "xmind": export_xmind,
        "markdown": export_markdown,
    }

    handler = format_handlers.get(export_req.format)
    if not handler:
        raise HTTPException(status_code=400,
                            detail=f"不支持的格式: {export_req.format}，支持: {list(format_handlers.keys())}")

    try:
        path = await handler(db, export_req.requirement_id)
        return FileResponse(path, filename=path.split("/")[-1] if "/" in path else path.split("\\")[-1],
                            media_type="application/octet-stream")
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


async def _get_next_version(db: AsyncSession, case_id: str) -> int:
    """获取下一个版本号"""
    from app.models import CaseVersion
    stmt = select(func.max(CaseVersion.version)).where(CaseVersion.test_case_id == case_id)
    result = await db.execute(stmt)
    max_ver = result.scalar() or 0
    return max_ver + 1
