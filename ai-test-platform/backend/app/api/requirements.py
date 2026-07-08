# AI Test Platform - API Routes: Requirements
# 需求管理 API (增删改查 + Stage 1)

import logging
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

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/requirements", tags=["需求管理"])


@router.post("/", response_model=APIResponse)
async def create_requirement(
    req_data: RequirementCreate,
    db: AsyncSession = Depends(get_db),
):
    """上传需求文档（手动粘贴或上传文本）— 自动分类归入分类树"""
    from app.services.category_classifier import classify_requirement, ensure_category_path

    # 自动分类：LLM 分析需求内容，确定分类路径
    category_path_str = req_data.module  # 用户也可手动指定
    assigned_path = []

    try:
        suggested_path = await classify_requirement(req_data.title, req_data.raw_text, db)
        if suggested_path and suggested_path != ["未分类"]:
            leaf_cat, full_path = await ensure_category_path(db, suggested_path)
            category_path_str = " > ".join(full_path)
            assigned_path = full_path
            logger.info(f"[Requirements] 需求 '{req_data.title}' 自动归类: {category_path_str}")
    except Exception as e:
        logger.warning(f"[Requirements] 自动分类失败，使用手动设定: {e}")
        if not category_path_str:
            category_path_str = "未分类"

    requirement = Requirement(
        title=req_data.title,
        module=category_path_str,
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
        data={
            "id": requirement.id,
            "title": requirement.title,
            "module": requirement.module,
            "status": requirement.status,
            "auto_classified": bool(assigned_path),
        },
    )


@router.post("/upload", response_model=APIResponse)
async def upload_requirement_file(
    file: UploadFile = File(...),
    module: str = "",
    db: AsyncSession = Depends(get_db),
):
    """上传需求文件（.txt / .md / .docx）— 自动分类归入分类树"""
    from app.services.category_classifier import classify_requirement, ensure_category_path

    content = await file.read()
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        text = content.decode("gbk", errors="ignore")

    title = file.filename.rsplit(".", 1)[0] if file.filename else "未命名需求"
    category_path_str = module

    # 自动分类
    try:
        suggested_path = await classify_requirement(title, text, db)
        if suggested_path and suggested_path != ["未分类"]:
            leaf_cat, full_path = await ensure_category_path(db, suggested_path)
            category_path_str = " > ".join(full_path)
    except Exception as e:
        logger.warning(f"[Requirements] 文件上传自动分类失败: {e}")
        if not category_path_str:
            category_path_str = "未分类"

    requirement = Requirement(
        title=title,
        module=category_path_str or "未分类",
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
    title: Optional[str] = None,
    module: Optional[str] = None,
    category_id: Optional[str] = None,
    status: Optional[str] = None,
    sort_by: Optional[str] = "created_at",
    sort_order: Optional[str] = "desc",
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
):
    """获取需求列表（支持搜索、筛选、排序、分类树筛选）"""
    query = select(Requirement).where(Requirement.is_active == True)

    # 分类树筛选：支持全路径匹配（module 字段存储格式："一级 > 二级 > 三级"）
    if category_id:
        from app.models import ModuleCategory

        cats_result = await db.execute(
            select(ModuleCategory).where(ModuleCategory.is_active == True)
        )
        all_cats = list(cats_result.scalars().unique().all())
        target_cat = next((c for c in all_cats if c.id == category_id), None)

        if target_cat:
            # 构建当前分类的完整路径前缀
            def build_category_path(cat):
                parts = [cat.name]
                parent = cat.parent
                while parent:
                    parts.insert(0, parent.name)
                    parent = parent.parent
                return " > ".join(parts)

            target_path = build_category_path(target_cat)

            # 也包含所有子孙分类的路径
            def get_descendant_paths(all_cats_list, parent_cat):
                paths = set()
                for c in all_cats_list:
                    if c.parent_id == parent_cat.id:
                        paths.add(build_category_path(c))
                        paths.update(get_descendant_paths(all_cats_list, c))
                return paths

            path_prefixes = {target_path}
            path_prefixes.update(get_descendant_paths(all_cats, target_cat))

            # 用 ILIKE 模糊匹配：module 以这些路径开头
            from sqlalchemy import or_
            conditions = [
                Requirement.module.ilike(f"{p}%") for p in path_prefixes
            ]
            # 同时也精确匹配（对于旧数据只有单层名称的情况）
            conditions.append(Requirement.module == target_cat.name)
            query = query.where(or_(*conditions))

    if title:
        query = query.where(Requirement.title.ilike(f"%{title}%"))
    if module:
        query = query.where(Requirement.module == module)
    if status:
        query = query.where(Requirement.status == status)

    # 动态排序
    sort_column = getattr(Requirement, sort_by, Requirement.created_at)
    if sort_order == "asc":
        query = query.order_by(sort_column.asc())
    else:
        query = query.order_by(sort_column.desc())

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

    if update_data.title is not None:
        req.title = update_data.title

    if update_data.module is not None:
        req.module = update_data.module


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


@router.get("/{requirement_id}/test-cases", response_model=APIResponse)
async def list_test_cases_by_requirement(
    requirement_id: str,
    db: AsyncSession = Depends(get_db),
):
    """获取需求下的用例列表（别名路由，兼容前端旧版调用）"""
    from app.models import TestCase
    from app.schemas import TestCaseResponse

    query = select(TestCase).where(
        TestCase.requirement_id == requirement_id,
        TestCase.is_active == True,
    ).order_by(TestCase.priority, TestCase.case_id)

    result = await db.execute(query)
    items = result.scalars().all()

    return APIResponse(
        success=True,
        data=[TestCaseResponse.model_validate(tc) for tc in items],
    )


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
