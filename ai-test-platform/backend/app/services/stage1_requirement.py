# Stage 1: 需求读取服务
# 把散落的需求文本解析成结构化需求实体，生成需求指纹
# 同时做实体抽取，为横切机制A做数据准备

import json
import logging
from typing import Optional
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.llm_provider import (
    get_llm_provider,
    REQUIREMENT_ENTITY_SCHEMA,
    LLMProvider,
)
from app.models import Requirement, RequirementStatus, TraceabilityLink, EntityRegistry
from app.config import settings

logger = logging.getLogger(__name__)

# Stage 1 Prompt 模板
REQUIREMENT_PARSE_SYSTEM_PROMPT = """你是一个资深测试架构师，擅长从需求文档中提取结构化测试要素。

请从以下需求文档中提取信息，返回严格的 JSON 格式。关键要求：

1. **feature_id** 格式为 "业务域.功能点名称"，如 "order.cart.coupon_stack_rule"
   - 业务域用小写英文，功能点用下划线连接
   - 确保同一功能点跨文档 ID 一致

2. **functional_points** 拆解所有功能点，每个包含：
   - feature_id: 功能点唯一标识
   - name: 功能点名称
   - description: 一句话描述
   - trigger: 触发条件
   - expected: 预期行为
   - constraints: 约束条件列表

3. **extracted_entities** 抽取实体供后续定位：
   - pages: 涉及的页面名称（如"购物车页"→"cart_page"）
   - apis: 涉及的接口（如"提交订单API"）
   - roles: 涉及的角色（如"普通用户""管理员"）
   - business_terms: 业务术语（如"满减""优惠券叠加"）

4. **summary_text** 写一段 100-200 字的结构化摘要，包含核心业务逻辑和关键实体，供向量检索使用。

5. 如果原文信息不足，不要编造，相关字段留空数组。"""


async def parse_requirement(
    db: AsyncSession,
    requirement_id: str,
    provider: Optional[LLMProvider] = None,
) -> dict:
    """执行 Stage 1：解析需求文本，生成结构化实体和指纹

    Args:
        db: 数据库会话
        requirement_id: 需求 ID
        provider: LLM Provider（可选，默认按配置）

    Returns:
        dict: 包含解析结果的状态信息
    """
    llm = provider or get_llm_provider()

    # 1. 获取需求
    stmt = select(Requirement).where(Requirement.id == requirement_id)
    result = await db.execute(stmt)
    req = result.scalar_one_or_none()
    if not req:
        raise ValueError(f"Requirement not found: {requirement_id}")
    if not req.raw_text:
        raise ValueError(f"Requirement has no raw_text: {requirement_id}")

    logger.info(f"[Stage 1] 开始解析需求: {req.title} (ID: {requirement_id})")

    # 2. 调用 LLM 结构化解析
    try:
        entity_data = await llm.chat_structured(
            messages=[
                {"role": "system", "content": REQUIREMENT_PARSE_SYSTEM_PROMPT},
                {"role": "user", "content": f"需求标题：{req.title}\n所属模块：{req.module}\n\n需求文档：\n{req.raw_text}"},
            ],
            schema=REQUIREMENT_ENTITY_SCHEMA,
            temperature=settings.LLM_TEMPERATURE_GENERATE,
            max_tokens=settings.LLM_MAX_TOKENS_GENERATE,
        )
    except Exception as e:
        logger.error(f"[Stage 1] LLM 解析失败: {e}")
        return {"status": "failed", "message": f"LLM 解析失败: {str(e)}"}

    # 3. 更新需求实体
    req.title = entity_data.get("title") or req.title
    req.module = entity_data.get("module") or req.module
    req.feature_id = entity_data.get("feature_id", "")
    req.description = entity_data.get("description", "")
    req.functional_points = entity_data.get("functional_points", [])
    req.participants = entity_data.get("participants", [])
    req.trigger_conditions = entity_data.get("trigger_conditions", [])
    req.expected_outcomes = entity_data.get("expected_outcomes", [])
    req.constraints = entity_data.get("constraints", [])
    req.data_scope = entity_data.get("data_scope", {})
    req.extracted_entities = entity_data.get("extracted_entities", {})
    req.summary_text = entity_data.get("summary_text", "")
    req.status = RequirementStatus.PARSED
    req.updated_at = datetime.now()

    await db.flush()

    # 4. 生成向量 embedding（如果有支持的话，尝试 embed）
    if req.summary_text:
        try:
            embedding = await llm.embed(req.summary_text)
            req.embedding = embedding
            await db.flush()
            logger.info(f"[Stage 1] 向量 embedding 生成成功, 维度: {len(embedding)}")
        except NotImplementedError:
            logger.warning("[Stage 1] 当前 LLM Provider 不支持 embedding，跳过向量化")
        except Exception as e:
            logger.warning(f"[Stage 1] embedding 生成失败 (非致命): {e}")

    # 5. 写入追溯链: Requirement → FeaturePoints
    # 先查询已存在的 feature_point 关联，避免 autoflush 导致重复插入
    existing_links_stmt = select(TraceabilityLink.target_id).where(
        TraceabilityLink.source_type == "requirement",
        TraceabilityLink.source_id == requirement_id,
        TraceabilityLink.target_type == "feature_point",
    )
    existing_result = await db.execute(existing_links_stmt)
    existing_target_ids = {row[0] for row in existing_result.all()}

    for fp in (req.functional_points or []):
        fid = fp.get("feature_id", "")
        if fid and fid not in existing_target_ids:
            link = TraceabilityLink(
                source_type="requirement", source_id=requirement_id,
                target_type="feature_point", target_id=fid,
                relation="contains",
                created_by="AI",
            )
            db.add(link)


    # 6. 提取实体并注册
    entities = req.extracted_entities or {}
    await _sync_entities(db, entities, req.module)

    # 7. 更新状态
    req.status = RequirementStatus.PARSED
    await db.flush()

    logger.info(f"[Stage 1] 需求解析完成: feature_id={req.feature_id}, "
                f"功能点数量={len(req.functional_points or [])}, "
                f"抽取实体={_count_entities(entities)}")

    return {
        "status": "success",
        "message": "需求解析完成",
        "data": {
            "requirement_id": requirement_id,
            "feature_id": req.feature_id,
            "functional_points_count": len(req.functional_points or []),
            "entities_count": _count_entities(entities),
            "summary_text": req.summary_text[:100] + "..." if req.summary_text and len(req.summary_text) > 100 else req.summary_text,
        },
    }


async def _sync_entities(db: AsyncSession, entities: dict, module: str):
    """同步抽取的实体到实体注册表"""
    entity_type_map = {
        "pages": "page",
        "apis": "api",
        "roles": "role",
        "business_terms": "business_term",
    }

    for key, etype in entity_type_map.items():
        names = entities.get(key, [])
        for name in names:
            unified_id = f"{module}.{etype}.{name}"
            # 检查是否已存在
            stmt = select(EntityRegistry).where(
                EntityRegistry.entity_type == etype,
                EntityRegistry.unified_id == unified_id,
            )
            result = await db.execute(stmt)
            existing = result.scalar_one_or_none()
            if not existing:
                entity = EntityRegistry(
                    entity_type=etype,
                    module=module,
                    name=name,
                    unified_id=unified_id,
                    aliases=[name],
                    created_by="AI",
                )
                db.add(entity)


def _count_entities(entities: dict) -> int:
    """统计实体总数"""
    return sum(len(v) for v in (entities or {}).values())
