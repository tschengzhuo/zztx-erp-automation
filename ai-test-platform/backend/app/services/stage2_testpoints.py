# Stage 2: 测试点生成服务
# 从需求实体生成覆盖全面的测试点清单，支持 RAG 增强

import json
import logging
from typing import Optional, List
from datetime import datetime

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm_provider import (
    get_llm_provider,
    TEST_POINTS_SCHEMA,
    LLMProvider,
)
from app.models import Requirement, TestPoint, RequirementStatus, TraceabilityLink
from app.config import settings

logger = logging.getLogger(__name__)

# Stage 2 Prompt 模板
TEST_POINTS_SYSTEM_PROMPT = """你是一个资深测试专家，擅长测试分析和测试设计。

你的任务是根据需求的结构化信息，生成全面、具体、可执行的测试点清单。

# 测试覆盖维度（必须穷举）
1. **功能正常**：正常输入下功能是否按预期工作
2. **边界值**：输入的最小/最大边界、刚好超出边界
3. **异常输入**：非法输入、空值、超长、特殊字符
4. **权限控制**：不同角色的访问和操作权限
5. **并发场景**：多用户同时操作的竞态条件
6. **兼容性**：不同浏览器/设备/数据格式的兼容
7. **数据完整性**：数据落库的准确性和一致性

# 测试技法
- 等价类划分：把输入域分成有效和无效等价类
- 边界值分析：对每个边界取边界值-1、边界值、边界值+1
- 决策表：罗列条件组合和对应动作
- 状态迁移：画出状态转换图，覆盖所有路径
- 场景法：模拟真实用户场景的端到端流程
- 错误推测：根据经验猜测易错点

# 核心要求
1. 每条测试点的 **title 必须具体到输入数据和预期行为**，不超过30字
2. **scenario_desc** 要包含具体的输入数据示例和预期行为
3. 优先覆盖 P0/P1 的核心路径
4. 避免重复的测试点，但要确保穷举维度
5. 参考提供的历史相似测试点，避免漏测"""


async def generate_test_points(
    db: AsyncSession,
    requirement_id: str,
    max_points: int = 30,
    provider: Optional[LLMProvider] = None,
) -> dict:
    """执行 Stage 2：生成测试点清单

    Args:
        db: 数据库会话
        requirement_id: 需求 ID
        max_points: 最大测试点数量
        provider: LLM Provider

    Returns:
        dict: {status, message, data: {count, test_points}}
    """
    llm = provider or get_llm_provider()

    # 1. 获取需求
    stmt = select(Requirement).where(Requirement.id == requirement_id)
    result = await db.execute(stmt)
    req = result.scalar_one_or_none()
    if not req:
        raise ValueError(f"Requirement not found: {requirement_id}")
    if req.status == RequirementStatus.DRAFT:
        raise ValueError("请先完成 Stage 1 需求解析")

    logger.info(f"[Stage 2] 开始生成测试点: {req.title}")

    # 2. 构建需求上下文
    fp_list = []
    for fp in (req.functional_points or []):
        fp_list.append(
            f"- [{fp.get('feature_id', '')}] {fp.get('name', '')}: {fp.get('description', '')}"
        )
    context = f"""
## 需求信息
- 需求标题: {req.title}
- 所属模块: {req.module}
- 核心描述: {req.description or '无'}

## 功能点清单
{chr(10).join(fp_list) if fp_list else '无'}

## 参与者
{json.dumps(req.participants or [], ensure_ascii=False)}

## 触发条件
{json.dumps(req.trigger_conditions or [], ensure_ascii=False)}

## 预期结果
{json.dumps(req.expected_outcomes or [], ensure_ascii=False)}

## 约束
{json.dumps(req.constraints or [], ensure_ascii=False)}

请生成 {max_points} 条以内的测试点，覆盖所有7个维度。
"""

    # 3. 尝试 RAG 检索历史相似测试点
    hist_context = ""
    try:
        hist_context = await _retrieve_similar_test_points(db, req.feature_id, req.summary_text)
    except Exception as e:
        logger.warning(f"[Stage 2] RAG 检索失败 (非致命): {e}")

    # 4. 调用 LLM 生成
    try:
        points_data = await llm.chat_structured(
            messages=[
                {"role": "system", "content": TEST_POINTS_SYSTEM_PROMPT},
                {"role": "user", "content": context + hist_context},
            ],
            schema=TEST_POINTS_SCHEMA,
            temperature=settings.LLM_TEMPERATURE_GENERATE,
            max_tokens=settings.LLM_MAX_TOKENS_GENERATE,
        )
    except Exception as e:
        logger.error(f"[Stage 2] LLM 生成失败: {e}")
        return {"status": "failed", "message": f"测试点生成失败: {str(e)}"}

    # 5. 入库
    created_points = []
    for pt in (points_data.get("test_points", [])[:max_points]):
        test_point = TestPoint(
            requirement_id=requirement_id,
            title=pt.get("title", "")[:500],
            feature_id=pt.get("feature_id", req.feature_id),
            dimension=pt.get("dimension", "功能正常"),
            scenario_desc=pt.get("scenario_desc", ""),
            technique=pt.get("technique", "等价类划分"),
            priority=pt.get("priority", "P1"),
            is_confirmed=False,
            created_by="AI",
        )
        db.add(test_point)
        await db.flush()

        # 追溯链: FeaturePoint → TestPoint
        fid = pt.get("feature_id") or req.feature_id or ""
        if fid:
            link = TraceabilityLink(
                source_type="feature_point", source_id=fid,
                target_type="test_point", target_id=test_point.id,
                relation="tested_by",
                created_by="AI",
            )
            db.add(link)

        created_points.append({
            "id": test_point.id,
            "title": test_point.title,
            "dimension": test_point.dimension,
            "priority": test_point.priority,
        })

    # 6. 更新需求状态
    req.status = RequirementStatus.TEST_POINTS_GENERATED
    req.updated_at = datetime.now()
    await db.flush()

    logger.info(f"[Stage 2] 测试点生成完成: 共 {len(created_points)} 个")

    return {
        "status": "success",
        "message": f"生成了 {len(created_points)} 个测试点",
        "data": {
            "requirement_id": requirement_id,
            "count": len(created_points),
            "test_points": created_points,
            "coverage_summary": points_data.get("coverage_summary", ""),
        },
    }


async def _retrieve_similar_test_points(
    db: AsyncSession,
    feature_id: Optional[str],
    summary_text: Optional[str],
) -> str:
    """RAG 检索相似历史测试点（简化版：基于 feature_id 前缀 + DB 查询）"""
    if not feature_id and not summary_text:
        return ""

    # 按 feature_id 前缀匹配同模块测试点
    if feature_id:
        prefix = feature_id.split(".")[0] if "." in feature_id else feature_id
        stmt = (
            select(TestPoint)
            .where(TestPoint.feature_id.like(f"{prefix}%"), TestPoint.is_confirmed == True)
            .order_by(TestPoint.created_at.desc())
            .limit(10)
        )
    else:
        stmt = (
            select(TestPoint)
            .where(TestPoint.is_confirmed == True)
            .order_by(TestPoint.created_at.desc())
            .limit(5)
        )

    result = await db.execute(stmt)
    hist_points = result.scalars().all()

    if not hist_points:
        return ""

    ctx = "\n\n## 历史相似测试点 (参考，避免漏测)\n"
    for p in hist_points:
        ctx += f"- [{p.dimension}] {p.title}: {p.scenario_desc[:80]}...\n"

    return ctx
