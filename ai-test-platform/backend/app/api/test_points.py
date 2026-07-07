# AI Test Platform - API Routes: Test Points
# 测试点管理 + Stage 2

from fastapi import APIRouter, Depends, HTTPException

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models import Requirement, TestPoint, RequirementStatus
from app.schemas import (
    TestPointResponse, TestPointConfirmRequest, TestPointGenerateRequest,
    APIResponse,
)
from app.services.stage2_testpoints import generate_test_points

router = APIRouter(prefix="/api/test-points", tags=["测试点"])


@router.post("/generate", response_model=APIResponse)
async def generate_test_points_stage2(
    req_data: TestPointGenerateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Stage 2: 生成测试点清单"""
    try:
        result = await generate_test_points(
            db, req_data.requirement_id, req_data.max_points
        )
        return APIResponse(
            success=result["status"] == "success",
            message=result["message"],
            data=result.get("data"),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"生成失败: {str(e)}")


@router.get("/by-requirement/{requirement_id}", response_model=APIResponse)
async def list_test_points(
    requirement_id: str,
    confirmed_only: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """获取需求下的测试点列表"""
    query = select(TestPoint).where(TestPoint.requirement_id == requirement_id)
    if confirmed_only:
        query = query.where(TestPoint.is_confirmed == True)
    query = query.order_by(TestPoint.priority, TestPoint.dimension)

    result = await db.execute(query)
    items = result.scalars().all()

    return APIResponse(
        success=True,
        data=[TestPointResponse.model_validate(tp) for tp in items],
    )


@router.put("/{test_point_id}", response_model=APIResponse)
async def update_test_point(
    test_point_id: str,
    data: dict,
    db: AsyncSession = Depends(get_db),
):
    """编辑单个测试点"""
    stmt = select(TestPoint).where(TestPoint.id == test_point_id)
    result = await db.execute(stmt)
    tp = result.scalar_one_or_none()
    if not tp:
        raise HTTPException(status_code=404, detail="测试点不存在")

    for key in ["title", "dimension", "scenario_desc", "technique", "priority"]:
        if key in data:
            setattr(tp, key, data[key])

    tp.last_modified_by = "human" if data else "AI"
    await db.flush()

    return APIResponse(success=True, message="测试点已更新",
                       data=TestPointResponse.model_validate(tp))


@router.post("/confirm", response_model=APIResponse)
async def confirm_test_points(
    confirm_data: TestPointConfirmRequest,
    db: AsyncSession = Depends(get_db),
):
    """QA 确认/删除测试点"""
    # 确认
    if confirm_data.confirmed_ids:
        stmt = select(TestPoint).where(TestPoint.id.in_(confirm_data.confirmed_ids))
        result = await db.execute(stmt)
        for tp in result.scalars().all():
            tp.is_confirmed = True

    # 删除
    if confirm_data.deleted_ids:
        stmt = select(TestPoint).where(TestPoint.id.in_(confirm_data.deleted_ids))
        result = await db.execute(stmt)
        for tp in result.scalars().all():
            await db.delete(tp)

    await db.flush()

    return APIResponse(
        success=True,
        message=f"已确认 {len(confirm_data.confirmed_ids)} 条, 删除 {len(confirm_data.deleted_ids)} 条",
    )
