# AI Test Platform - API Routes: Requirements
# 需求管理 API (增删改查 + Stage 1)

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.models import Requirement, RequirementStatus
from app.schemas import (
    RequirementCreate, RequirementUpdate, RequirementResponse,
    APIResponse, PaginationParams, PaginatedResponse,
)
from app.services.stage1_requirement import parse_requirement

router = APIRouter(prefix="/api/requirements", tags=["需求管理"])


@router.post("/", response_model=APIResponse)
async def create_requirement(
    req_data: RequirementCreate,
    db: AsyncSession = Depends(get_db),
):
    """上传需求文档（手动粘贴或上传文本）"""
    requirement = Requirement(
        title=req_data.title,
        module=req_data.module,
        raw_text=req_data.raw_text,
        source=req_data.source,
        status=RequirementStatus.DRAFT,
        created_by="user",
    )
    db.add(requirement)
    await db.flush()

    return APIResponse(
        success=True,
        message="需求创建成功",
        data={"id": requirement.id, "title": requirement.title, "status": requirement.status},
    )


@router.post("/upload", response_model=APIResponse)
async def upload_requirement_file(
    file: UploadFile = File(...),
    module: str = "",
    db: AsyncSession = Depends(get_db),
):
    """上传需求文件（.txt / .md / .docx）"""
    content = await file.read()
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        text = content.decode("gbk", errors="ignore")

    title = file.filename.rsplit(".", 1)[0] if file.filename else "未命名需求"

    requirement = Requirement(
        title=title,
        module=module or "未分类",
        raw_text=text,
        source="file_upload",
        status=RequirementStatus.DRAFT,
        created_by="user",
    )
    db.add(requirement)
    await db.flush()

    return APIResponse(
        success=True,
        message=f"文件 {file.filename} 上传成功",
        data={"id": requirement.id, "title": requirement.title, "text_length": len(text)},
    )


@router.get("/", response_model=PaginatedResponse)
async def list_requirements(
    module: Optional[str] = None,
    status: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
):
    """获取需求列表（支持按模块/状态筛选）"""
    query = select(Requirement).where(Requirement.is_active == True)

    if module:
        query = query.where(Requirement.module == module)
    if status:
        query = query.where(Requirement.status == status)

    query = query.order_by(Requirement.created_at.desc())

    # 总数
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar()

    # 分页
    offset = (page - 1) * page_size
    result = await db.execute(query.offset(offset).limit(page_size))
    items = result.scalars().all()

    return PaginatedResponse(
        items=[RequirementResponse.model_validate(r) for r in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size,
    )


@router.get("/{requirement_id}", response_model=APIResponse)
async def get_requirement(
    requirement_id: str,
    db: AsyncSession = Depends(get_db),
):
    """获取需求详情"""
    stmt = select(Requirement).where(Requirement.id == requirement_id)
    result = await db.execute(stmt)
    req = result.scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=404, detail="需求不存在")

    return APIResponse(success=True, data=RequirementResponse.model_validate(req))


@router.put("/{requirement_id}", response_model=APIResponse)
async def update_requirement(
    requirement_id: str,
    update_data: RequirementUpdate,
    db: AsyncSession = Depends(get_db),
):
    """更新需求（迭代场景）"""
    stmt = select(Requirement).where(Requirement.id == requirement_id)
    result = await db.execute(stmt)
    req = result.scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=404, detail="需求不存在")

    # 迭代更新：创建新版本快照
    if update_data.raw_text:
        from app.models import RequirementVersion
        import json
        snapshot = RequirementVersion(
            requirement_id=requirement_id,
            version=req.version,
            snapshot={
                "title": req.title, "raw_text": req.raw_text,
                "functional_points": req.functional_points,
            },
            change_summary="迭代更新",
        )
        db.add(snapshot)

        req.version += 1
        req.raw_text = update_data.raw_text
        req.status = RequirementStatus.DRAFT  # 需要重新解析

    if update_data.title:
        req.title = update_data.title

    await db.flush()

    return APIResponse(
        success=True,
        message="需求已更新",
        data={"id": req.id, "version": req.version, "title": req.title},
    )


@router.post("/{requirement_id}/parse", response_model=APIResponse)
async def parse_requirement_stage1(
    requirement_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Stage 1: 解析需求，生成结构化实体和指纹"""
    try:
        result = await parse_requirement(db, requirement_id)
        return APIResponse(
            success=result["status"] == "success",
            message=result["message"],
            data=result.get("data"),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"解析失败: {str(e)}")


@router.delete("/{requirement_id}", response_model=APIResponse)
async def delete_requirement(
    requirement_id: str,
    db: AsyncSession = Depends(get_db),
):
    """软删除需求"""
    stmt = select(Requirement).where(Requirement.id == requirement_id)
    result = await db.execute(stmt)
    req = result.scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=404, detail="需求不存在")

    req.is_active = False
    await db.flush()

    return APIResponse(success=True, message="需求已删除")
