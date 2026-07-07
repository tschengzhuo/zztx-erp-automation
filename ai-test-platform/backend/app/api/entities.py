# AI Test Platform - API Routes: Entity Registry
# 实体注册表管理（页面/接口/角色/业务术语）

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models import EntityRegistry
from app.schemas import EntityCreate, EntityResponse, APIResponse

router = APIRouter(prefix="/api/entities", tags=["实体注册表"])


@router.get("/", response_model=APIResponse)
async def list_entities(
    entity_type: Optional[str] = None,
    module: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """获取实体列表"""
    query = select(EntityRegistry).order_by(EntityRegistry.entity_type, EntityRegistry.module)

    if entity_type:
        query = query.where(EntityRegistry.entity_type == entity_type)
    if module:
        query = query.where(EntityRegistry.module == module)

    result = await db.execute(query)
    items = result.scalars().all()

    return APIResponse(
        success=True,
        data=[EntityResponse.model_validate(e) for e in items],
    )


@router.post("/", response_model=APIResponse)
async def create_entity(
    entity_data: EntityCreate,
    db: AsyncSession = Depends(get_db),
):
    """创建实体"""
    unified_id = entity_data.unified_id or f"{entity_data.module}.{entity_data.entity_type}.{entity_data.name}"

    entity = EntityRegistry(
        entity_type=entity_data.entity_type,
        module=entity_data.module,
        name=entity_data.name,
        unified_id=unified_id,
        aliases=entity_data.aliases,
        description=entity_data.description,
        metadata_=entity_data.metadata_,
        is_confirmed=False,
        created_by="user",
    )
    db.add(entity)
    await db.flush()

    return APIResponse(message="实体创建成功", data=EntityResponse.model_validate(entity))


@router.post("/batch-import/swagger", response_model=APIResponse)
async def batch_import_swagger(
    module: str,
    swagger_json: dict,
    db: AsyncSession = Depends(get_db),
):
    """从 Swagger/OpenAPI JSON 批量导入接口实体"""
    paths = swagger_json.get("paths", {})
    count = 0
    base_path = swagger_json.get("basePath", "")

    for path, methods in paths.items():
        for method, details in methods.items():
            if method.upper() in ("GET", "POST", "PUT", "DELETE", "PATCH"):
                name = f"{method.upper()} {base_path}{path}"
                unified_id = f"{module}.api.{name}"

                entity = EntityRegistry(
                    entity_type="api",
                    module=module,
                    name=name,
                    unified_id=unified_id,
                    description=details.get("summary", ""),
                    metadata_={"method": method.upper(), "path": f"{base_path}{path}", "tags": details.get("tags", [])},
                    created_by="system",
                )
                db.add(entity)
                count += 1

    await db.flush()

    return APIResponse(success=True, message=f"从 Swagger 导入了 {count} 个接口实体")


@router.put("/{entity_id}", response_model=APIResponse)
async def update_entity(
    entity_id: str,
    data: dict,
    db: AsyncSession = Depends(get_db),
):
    """更新实体"""
    stmt = select(EntityRegistry).where(EntityRegistry.id == entity_id)
    result = await db.execute(stmt)
    entity = result.scalar_one_or_none()
    if not entity:
        raise HTTPException(status_code=404, detail="实体不存在")

    for key in ["name", "aliases", "description", "metadata_", "is_confirmed"]:
        if key in data:
            if key == "metadata_":
                setattr(entity, "metadata_", data[key])
            else:
                setattr(entity, key, data[key])

    await db.flush()
    return APIResponse(success=True, message="实体已更新", data=EntityResponse.model_validate(entity))


@router.delete("/{entity_id}", response_model=APIResponse)
async def delete_entity(
    entity_id: str,
    db: AsyncSession = Depends(get_db),
):
    """删除实体"""
    stmt = select(EntityRegistry).where(EntityRegistry.id == entity_id)
    result = await db.execute(stmt)
    entity = result.scalar_one_or_none()
    if not entity:
        raise HTTPException(status_code=404, detail="实体不存在")

    await db.delete(entity)
    await db.flush()
    return APIResponse(success=True, message="实体已删除")
