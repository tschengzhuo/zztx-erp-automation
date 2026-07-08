# AI Test Platform - API Routes: Module Categories
# 模块分类树 CRUD

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import ModuleCategory
from app.schemas import (
    CategoryCreate, CategoryUpdate,
    APIResponse,
)

router = APIRouter(prefix="/api/categories", tags=["分类树"])


def _build_category_path(cat: ModuleCategory) -> str:
    """获取分类的完整路径"""
    parts = [cat.name]
    parent = cat.parent
    while parent:
        parts.insert(0, parent.name)
        parent = parent.parent
    return " > ".join(parts)


@router.get("/tree", response_model=APIResponse)
async def get_category_tree(db: AsyncSession = Depends(get_db)):
    """获取完整分类树（含每个节点的需求数量）"""
    from app.models import Requirement

    stmt = (
        select(ModuleCategory)
        .where(ModuleCategory.is_active == True)
        .options(selectinload(ModuleCategory.children))
        .order_by(ModuleCategory.sort_order)
    )
    result = await db.execute(stmt)
    items = result.unique().scalars().all()

    # 获取所有活跃需求及其 module（统计用）
    req_result = await db.execute(
        select(Requirement.module).where(
            Requirement.is_active == True,
            Requirement.module.isnot(None),
        )
    )
    req_modules = [row[0] for row in req_result.all()]

    # 构建树形结构（只从根节点开始）
    tree = []
    for item in items:
        if item.parent_id is None:
            node = _build_tree_node(item, req_modules)
            tree.append(node)

    return APIResponse(success=True, data=tree)


def _build_tree_node(cat: ModuleCategory, req_modules: list = None) -> dict:
    """递归构建分类树节点（含需求数量）"""
    children_nodes = [_build_tree_node(c, req_modules) for c in cat.children if c.is_active]
    children_nodes.sort(key=lambda x: x.get("sort_order", 0))

    node = {
        "id": cat.id,
        "name": cat.name,
        "parent_id": cat.parent_id,
        "sort_order": cat.sort_order,
        "description": cat.description,
        "children": children_nodes,
        "created_at": cat.created_at.isoformat() if cat.created_at else None,
        "path": _build_category_path(cat),
    }

    if req_modules is not None:
        # 统计所有 module 以此节点路径为前缀的需求数（包含子孙）
        node["requirement_count"] = sum(
            1 for m in req_modules
            if m == node["path"] or m.startswith(node["path"] + " >")
        )

    return node


@router.get("/", response_model=APIResponse)
async def list_categories(
    parent_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """获取分类列表（扁平或按父节点筛选）"""
    query = (
        select(ModuleCategory)
        .where(ModuleCategory.is_active == True)
        .options(selectinload(ModuleCategory.children))
    )
    if parent_id is not None:
        if parent_id:
            query = query.where(ModuleCategory.parent_id == parent_id)
        else:
            query = query.where(ModuleCategory.parent_id.is_(None))
    query = query.order_by(ModuleCategory.sort_order)
    result = await db.execute(query)
    items = result.unique().scalars().all()

    # 返回扁平列表，带 children 简化信息
    resp_list = []
    for item in items:
        resp_list.append({
            "id": item.id,
            "name": item.name,
            "parent_id": item.parent_id,
            "sort_order": item.sort_order,
            "description": item.description,
            "children": [
                {"id": c.id, "name": c.name} for c in item.children if c.is_active
            ],
            "created_at": item.created_at.isoformat() if item.created_at else None,
        })
    return APIResponse(success=True, data=resp_list)


@router.post("/", response_model=APIResponse)
async def create_category(
    cat_data: CategoryCreate,
    db: AsyncSession = Depends(get_db),
):
    """创建分类节点"""
    # 检查同名同父节点
    existing = await db.execute(
        select(ModuleCategory).where(
            ModuleCategory.name == cat_data.name,
            ModuleCategory.parent_id == cat_data.parent_id,
            ModuleCategory.is_active == True,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="同级下分类名称已存在")

    # 检查父节点存在
    if cat_data.parent_id:
        parent = await db.get(ModuleCategory, cat_data.parent_id)
        if not parent or not parent.is_active:
            raise HTTPException(status_code=404, detail="父分类不存在")

    category = ModuleCategory(
        name=cat_data.name,
        parent_id=cat_data.parent_id,
        sort_order=cat_data.sort_order,
        description=cat_data.description,
    )
    db.add(category)
    await db.flush()

    return APIResponse(
        success=True,
        message="分类创建成功",
        data={"id": category.id, "name": category.name, "parent_id": category.parent_id},
    )


@router.put("/{category_id}", response_model=APIResponse)
async def update_category(
    category_id: str,
    update_data: CategoryUpdate,
    db: AsyncSession = Depends(get_db),
):
    """更新分类"""
    category = await db.get(ModuleCategory, category_id)
    if not category:
        raise HTTPException(status_code=404, detail="分类不存在")

    # 防止循环引用：不能把自己或子孙节点设为父节点
    if update_data.parent_id is not None:
        if update_data.parent_id == category_id:
            raise HTTPException(status_code=400, detail="不能将自己设为父节点")
        if update_data.parent_id:
            # 检查是否形成环
            all_nodes = (await db.execute(
                select(ModuleCategory).where(ModuleCategory.is_active == True)
            )).scalars().all()
            # 构建子树来判断环
            def get_descendant_ids(nodes, pid):
                ids = set()
                for n in nodes:
                    if n.parent_id == pid:
                        ids.add(n.id)
                        ids.update(get_descendant_ids(nodes, n.id))
                return ids
            descendants = get_descendant_ids(list(all_nodes), category_id)
            if update_data.parent_id in descendants:
                raise HTTPException(status_code=400, detail="不能将子孙节点设为父节点（会形成循环）")

    if update_data.name is not None:
        category.name = update_data.name
    if update_data.parent_id is not None:
        category.parent_id = update_data.parent_id
    if update_data.sort_order is not None:
        category.sort_order = update_data.sort_order
    if update_data.description is not None:
        category.description = update_data.description

    await db.flush()
    return APIResponse(success=True, message="分类已更新", data={"id": category.id})


@router.delete("/{category_id}", response_model=APIResponse)
async def delete_category(
    category_id: str,
    db: AsyncSession = Depends(get_db),
):
    """软删除分类（级联删除子分类）"""
    category = await db.get(ModuleCategory, category_id)
    if not category:
        raise HTTPException(status_code=404, detail="分类不存在")

    # 级联软删除子孙节点
    async def soft_delete_children(parent_id: str):
        stmt = select(ModuleCategory).where(
            ModuleCategory.parent_id == parent_id,
            ModuleCategory.is_active == True,
        )
        result = await db.execute(stmt)
        children = result.scalars().all()
        for child in children:
            child.is_active = False
            await soft_delete_children(child.id)

    category.is_active = False
    await soft_delete_children(category_id)
    await db.flush()

    return APIResponse(success=True, message=f"分类 '{category.name}' 及其子分类已删除")
