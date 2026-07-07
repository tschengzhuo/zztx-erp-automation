# Stage 3: 结构化用例转换服务
# 把测试点展开成可执行的 AAA 格式结构化用例
# 支持双形态生成（UI + API），步骤带 locked 标记

import logging
from typing import Optional, List
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm_provider import (
    get_llm_provider,
    STRUCTURED_CASE_SCHEMA,
    LLMProvider,
)
from app.models import (
    Requirement, TestPoint, TestCase, TraceabilityLink,
    CaseVersion, RequirementStatus,
)
from app.config import settings

logger = logging.getLogger(__name__)

# Stage 3 Prompt 模板
CASE_GENERATION_SYSTEM_PROMPT = """你是一个资深测试自动化工程师，擅长编写结构化测试用例。

# 你的任务
根据测试点和需求信息，生成可直接执行的结构化测试用例。

# 用例格式 (AAA: Arrange-Act-Assert)
每条用例包含：
- precondition: 前置条件（数据准备、环境要求）
- steps: 步骤序列，每步包含 action + target + value

# UI 用例动作类型
- navigate: 页面跳转，target=URL路径
- fill: 输入，target=CSS选择器，value=输入值
- click: 点击，target=CSS选择器
- select: 下拉选择，target=CSS选择器，value=选项值
- hover: 悬停，target=CSS选择器
- scroll: 滚动，target=CSS选择器
- wait: 等待，target=等待时间(ms)/选择器出现
- assert: 断言，target=断言内容，value=期望值

# API 用例动作类型
- api_request: API请求，target=接口路径，method=GET/POST/PUT/DELETE

# 核心要求
1. **选择器优先使用语义属性**：data-testid > role > text > CSS class
2. 每条步骤带 locked=false 和 last_modified_by="AI" 标记
3. 断言要明确具体，不要"结果正确"这种空话
4. test_data 包含测试需要的账号/参数数据
5. tags 标签要包括业务关键词和测试类型

# 关键原则
- 每条用例必须独立可执行，前置条件自包含
- 预期的 expected_result 要具体可验证"""


async def generate_test_cases(
    db: AsyncSession,
    requirement_id: str,
    test_point_ids: Optional[List[str]] = None,
    generate_both: bool = True,
    provider: Optional[LLMProvider] = None,
) -> dict:
    """执行 Stage 3：从测试点生成结构化用例

    Args:
        db: 数据库会话
        requirement_id: 需求 ID
        test_point_ids: 指定的测试点 ID 列表（为空则用全部确认的）
        generate_both: 是否同时生成 UI 和 API 用例
        provider: LLM Provider

    Returns:
        dict: {status, message, data: {ui_count, api_count, cases}}
    """
    llm = provider or get_llm_provider()

    # 1. 获取需求和测试点
    stmt = select(Requirement).where(Requirement.id == requirement_id)
    result = await db.execute(stmt)
    req = result.scalar_one_or_none()
    if not req:
        raise ValueError(f"Requirement not found: {requirement_id}")

    if test_point_ids:
        tp_stmt = select(TestPoint).where(TestPoint.id.in_(test_point_ids))
    else:
        tp_stmt = select(TestPoint).where(
            TestPoint.requirement_id == requirement_id,
            TestPoint.is_confirmed == True,
        )
    tp_result = await db.execute(tp_stmt)
    test_points: List[TestPoint] = tp_result.scalars().all()

    if not test_points:
        raise ValueError("没有可用的测试点，请先完成 Stage 2 并确认测试点")

    logger.info(f"[Stage 3] 开始生成用例: {req.title}, 测试点数={len(test_points)}")

    # 2. 批量生成（每批最多 5 个测试点，控制 token）
    batch_size = 5
    all_ui_cases = []
    all_api_cases = []
    case_counter = 0

    for i in range(0, len(test_points), batch_size):
        batch = test_points[i:i + batch_size]
        tp_text = _format_test_points(batch)
        req_text = _format_requirement(req)

        try:
            cases_data = await llm.chat_structured(
                messages=[
                    {"role": "system", "content": CASE_GENERATION_SYSTEM_PROMPT},
                    {"role": "user", "content": req_text + "\n\n" + tp_text},
                ],
                schema=STRUCTURED_CASE_SCHEMA,
                temperature=settings.LLM_TEMPERATURE_GENERATE,
                max_tokens=settings.LLM_MAX_TOKENS_GENERATE,
            )
        except Exception as e:
            logger.error(f"[Stage 3] LLM 生成失败 (batch {i}-{i+len(batch)}): {e}")
            continue

        # 3. 入库 UI 用例
        for case_data in cases_data.get("cases", []):
            tp_title = case_data.get("test_point_title", "")
            # 找到对应的测试点
            tp = next((t for t in batch if t.title == tp_title), None)

            # UI Case
            ui = case_data.get("ui_case")
            if ui and ui.get("steps"):
                case_counter += 1
                case_id = f"TC-{datetime.now().strftime('%Y')}-{case_counter:04d}"

                steps = ui.get("steps", [])
                # 保证每个步骤有 locked 和 last_modified_by
                for step in steps:
                    step.setdefault("locked", False)
                    step.setdefault("last_modified_by", "AI")

                test_case = TestCase(
                    case_id=case_id,
                    requirement_id=requirement_id,
                    test_point_id=tp.id if tp else None,
                    title=ui.get("title", f"UI-{tp_title}"),
                    precondition=ui.get("precondition", ""),
                    steps=steps,
                    expected_result=ui.get("expected_result", ""),
                    test_data=ui.get("test_data"),
                    case_type="UI",
                    priority=ui.get("priority", "P1"),
                    tags=ui.get("tags", []),
                    is_confirmed=False,
                    created_by="AI",
                )
                db.add(test_case)
                await db.flush()

                # 追溯链: TestPoint → TestCase
                if tp:
                    link = TraceabilityLink(
                        source_type="test_point", source_id=tp.id,
                        target_type="test_case", target_id=test_case.id,
                        relation="implemented_by",
                        created_by="AI",
                    )
                    db.add(link)

                # 用例版本
                cv = CaseVersion(
                    test_case_id=test_case.id,
                    version=1,
                    steps=steps,
                    expected_result=test_case.expected_result,
                    change_reason="AI 自动生成",
                )
                db.add(cv)

                all_ui_cases.append({
                    "id": test_case.id,
                    "case_id": case_id,
                    "title": test_case.title,
                    "priority": test_case.priority,
                })

            # API Case
            if generate_both:
                api = case_data.get("api_case")
                if api and api.get("steps"):
                    case_counter += 1
                    case_id = f"TC-{datetime.now().strftime('%Y')}-{case_counter:04d}"

                    steps = api.get("steps", [])
                    for step in steps:
                        step.setdefault("locked", False)
                        step.setdefault("last_modified_by", "AI")

                    test_case = TestCase(
                        case_id=case_id,
                        requirement_id=requirement_id,
                        test_point_id=tp.id if tp else None,
                        title=api.get("title", f"API-{tp_title}"),
                        precondition=api.get("precondition", ""),
                        steps=steps,
                        expected_result=api.get("expected_result", ""),
                        test_data=api.get("test_data"),
                        case_type="API",
                        priority=api.get("priority", "P1"),
                        tags=api.get("tags", []),
                        is_confirmed=False,
                        created_by="AI",
                    )
                    db.add(test_case)
                    await db.flush()

                    if tp:
                        link = TraceabilityLink(
                            source_type="test_point", source_id=tp.id,
                            target_type="test_case", target_id=test_case.id,
                            relation="implemented_by",
                            created_by="AI",
                        )
                        db.add(link)

                    cv = CaseVersion(
                        test_case_id=test_case.id,
                        version=1,
                        steps=steps,
                        expected_result=test_case.expected_result,
                        change_reason="AI 自动生成",
                    )
                    db.add(cv)

                    all_api_cases.append({
                        "id": test_case.id,
                        "case_id": case_id,
                        "title": test_case.title,
                        "priority": test_case.priority,
                    })

        await db.flush()

    # 4. 更新需求状态
    req.status = RequirementStatus.CASES_GENERATED
    req.updated_at = datetime.now()
    await db.flush()

    total = len(all_ui_cases) + len(all_api_cases)
    logger.info(f"[Stage 3] 用例生成完成: UI={len(all_ui_cases)}, API={len(all_api_cases)}, 总计={total}")

    return {
        "status": "success",
        "message": f"生成了 {total} 条用例 (UI: {len(all_ui_cases)}, API: {len(all_api_cases)})",
        "data": {
            "requirement_id": requirement_id,
            "ui_count": len(all_ui_cases),
            "api_count": len(all_api_cases),
            "ui_cases": all_ui_cases,
            "api_cases": all_api_cases,
        },
    }


def _format_test_points(points: List[TestPoint]) -> str:
    """格式化测试点为 prompt 文本"""
    lines = ["## 测试点清单\n"]
    for i, tp in enumerate(points, 1):
        lines.append(f"{i}. [{tp.dimension}][{tp.priority}] {tp.title}")
        lines.append(f"   技法: {tp.technique}")
        lines.append(f"   场景: {tp.scenario_desc}")
        lines.append("")
    return "\n".join(lines)


def _format_requirement(req) -> str:
    """格式化需求为 prompt 文本"""
    import json
    lines = [
        f"## 需求信息",
        f"- 需求: {req.title}",
        f"- 模块: {req.module}",
        f"- 描述: {req.description or '无'}",
        f"- 参与者: {json.dumps(req.participants or [], ensure_ascii=False)}",
        f"- 约束: {json.dumps(req.constraints or [], ensure_ascii=False)}",
        "",
    ]

    # 抽取的实体信息（页面/接口）
    entities = req.extracted_entities or {}
    if entities.get("pages"):
        lines.append(f"- 涉及页面: {', '.join(entities['pages'])}")
    if entities.get("apis"):
        lines.append(f"- 涉及接口: {', '.join(entities['apis'])}")
    if entities.get("roles"):
        lines.append(f"- 涉及角色: {', '.join(entities['roles'])}")

    lines.append("")
    return "\n".join(lines)
