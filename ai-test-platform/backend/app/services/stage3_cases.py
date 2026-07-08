# Stage 3: 结构化用例转换服务
# 把测试点展开成可执行的 AAA 格式结构化用例
# 支持双形态生成（UI + API），步骤带 locked 标记

import asyncio
import logging
import uuid
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

# Stage 3 Prompt - 精简核心步骤 + 预期结果基于需求文档
CASE_GENERATION_SYSTEM_PROMPT = """你是资深测试工程师，根据测试点和需求文档生成结构化 AAA 格式用例。

# 设计原则
- 正常/异常/边界全覆盖，边界值精准不冗余
- **步骤精简**：只保留核心业务操作步骤，不走查式罗列。每个步骤代表一个有意义的业务动作。
- 琐碎操作（登录、导航、等待、点击无关按钮等）合并为前置条件或合并到第一步中一笔带过。
- 每条用例独立可执行，每个测试点对应一条用例，cases 数组长度等于测试点数。

# 用例字段
- title: "模块-场景简述"
- precondition: 前置条件（含登录状态、数据准备等环境信息）
- steps: [{action, target, value, expected, locked:false, last_modified_by:"AI"}]
  - expected: **重要步骤必须填写**步骤级预期结果，严格依据需求文档。非关键步骤可留空。
- expected_result: 用例级最终预期结果，严格依据需求文档原文
- test_data: 测试数据对象
- priority: P0/P1/P2/P3
- tags: [业务关键词, 测试类型]

# 步骤动作类型
UI: 导航/输入/点击/选择/悬停/滚动/等待/断言
API: 接口请求（含 method/headers/body/expect_status）

# 步骤示例（精简后的效果）
正确✅ - 3~5步核心操作，关键步骤带 expected：
  step1: action="输入", target="在商品汇总页筛选中输入批次号 XYZ001", value="XYZ001", expected="根据需求文档，筛选后列表仅显示对应批次数据"
  step2: action="点击", target="用户A点击刷新按钮", value="", expected=""
  step3: action="断言", target="对比用户A与用户B看到的批号、生产日期、保质期", value="", expected="需求文档明确：两名用户看到的汇总表数据完全一致"

错误❌ - 步骤过于琐碎：
  step1: "导航 打开浏览器"、step2: "输入 输入用户名"、step3: "输入 输入密码"、step4: "点击 点击登录" ...

# 关键要求
1. **target/value 必须全部是业务名称，禁止出现任何代码字段/技术标识**：
   - 禁止 snake_case 页面名，如 `order_summary_page` 必须写成"商品汇总页"；
   - 禁止 CSS 选择器、DOM id、class、Vue/React 组件名等技术定位信息；
   - 禁止 URL、API 路径出现在 UI 步骤的 target/value 中（API 用例的 target 除外，但仍建议搭配业务说明）；
   - 禁止字段名、表名、参数名等技术术语直接作为操作对象，必须转换为业务名称，如 `batch_no` → "批次号"。
   正确示例：target="用户A与用户B在商品汇总页中查看同一商品行的批次号、生产日期、保质期"
   错误示例：target="用户A与用户B在 order_summary_page 中查看同一商品行的 batch_no、prod_date、expire_date"
2. target 字段必须写成业务操作描述（人话），格式"谁 + 在什么页面/模块 + 做什么"。
3. 并发/多用户场景必须体现多会话操作顺序和关键时间点。
4. **预期结果必须引用需求文档中的原文表述**，不能自行推断。若需求文档未明确写出，标记为"需求未明确"。
5. 断言类步骤（action=assert）的 expected 字段必须填写具体的判定标准，如"数据一致"不够，应写"批号、生产日期、保质期三者均相同"。
6. 每个用例步骤数控制在 3~7 步，多余的非核心步骤合并或省略。"""


async def generate_test_cases(
    db: AsyncSession,
    requirement_id: str,
    test_point_ids: Optional[List[str]] = None,
    generate_both: bool = True,
    provider: Optional[LLMProvider] = None,
    progress_callback=None,
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
        tp_result = await db.execute(tp_stmt)
        test_points: List[TestPoint] = tp_result.scalars().all()
    else:
        # 未指定测试点时，优先使用已确认的测试点；没有确认点则降级为该需求下全部测试点
        confirmed_stmt = select(TestPoint).where(
            TestPoint.requirement_id == requirement_id,
            TestPoint.is_confirmed == True,
        )
        confirmed_result = await db.execute(confirmed_stmt)
        test_points = confirmed_result.scalars().all()
        if not test_points:
            all_stmt = select(TestPoint).where(TestPoint.requirement_id == requirement_id)
            all_result = await db.execute(all_stmt)
            test_points = all_result.scalars().all()

    if not test_points:
        raise ValueError("没有可用的测试点，请先完成 Stage 2 测试点生成")


    logger.info(f"[Stage 3] 开始生成用例: {req.title}, 测试点数={len(test_points)}")

    # 2.5 清理旧用例（支持重新生成）
    from sqlalchemy import delete
    old_cases_stmt = select(TestCase).where(TestCase.requirement_id == requirement_id)
    old_result = await db.execute(old_cases_stmt)
    old_cases = old_result.scalars().all()
    if old_cases:
        old_case_ids = [c.id for c in old_cases]
        await db.execute(
            delete(CaseVersion).where(CaseVersion.test_case_id.in_(old_case_ids))
        )
        await db.execute(
            delete(TraceabilityLink).where(
                TraceabilityLink.target_type == "test_case",
                TraceabilityLink.target_id.in_(old_case_ids),
            )
        )
        await db.execute(
            delete(TestCase).where(TestCase.requirement_id == requirement_id)
        )
        await db.flush()
        logger.info(f"[Stage 3] 清理了 {len(old_cases)} 条旧用例")

    # 3. 并行批量生成用例（核心优化：asyncio.gather + 快速模型 + 大批次）
    _run_id = uuid.uuid4().hex[:6]
    BATCH_SIZE = 5          # 每批测试点数（减少 API 调用次数）
    MAX_CONCURRENT = 5      # 最大并行 LLM 请求数
    MAX_TOKENS_STAGE3 = 2048  # 精简输出，加速生成

    # 选择快速模型（medium 模型速度快 3-5 倍，用例生成场景质量差距小）
    provider_name = settings.LLM_PROVIDER
    _model_map = {
        "qwen": settings.QWEN_MODEL_MEDIUM,          # qwen-plus
        "openai": settings.OPENAI_MODEL_MEDIUM,       # gpt-4o-mini
        "anthropic": settings.ANTHROPIC_MODEL_MEDIUM, # claude-3-haiku
    }
    stage3_model = _model_map.get(provider_name, None)
    logger.info(f"[Stage 3] 并行模式: model={stage3_model or '默认'}, batch={BATCH_SIZE}, concurrent={MAX_CONCURRENT}")

    # 分批
    batches = [
        (test_points[i:i + BATCH_SIZE], i // BATCH_SIZE)
        for i in range(0, len(test_points), BATCH_SIZE)
    ]
    total_batches = len(batches)

    sem = asyncio.Semaphore(MAX_CONCURRENT)
    req_text = _format_requirement(req)  # 所有批次共享，只格式化一次

    async def _process_batch(batch, batch_index):
        """并行处理单个批次：LLM 调用，返回原始结果"""
        async with sem:
            tp_text = _format_test_points(batch)
            batch_n = len(batch)
            user_content = (
                f"{req_text}\n\n{tp_text}\n\n"
                f"请为以上 {batch_n} 个测试点分别生成测试用例，"
                f"cases 数组中必须恰好包含 {batch_n} 个元素，通过 test_point_title 与测试点一一对应。"
            )

            if progress_callback:
                progress_callback(batch_index + 1, total_batches,
                                  f"并行生成 {batch_index+1}/{total_batches}...")

            try:
                result = await llm.chat_structured(
                    messages=[
                        {"role": "system", "content": CASE_GENERATION_SYSTEM_PROMPT},
                        {"role": "user", "content": user_content},
                    ],
                    schema=STRUCTURED_CASE_SCHEMA,
                    temperature=settings.LLM_TEMPERATURE_GENERATE,
                    max_tokens=MAX_TOKENS_STAGE3,
                    model=stage3_model,
                )
                return (batch, batch_index, result, None)
            except Exception as e:
                logger.error(f"[Stage 3] 批次 {batch_index+1} 失败: {e}")
                return (batch, batch_index, None, str(e))

    # ===== 并行执行所有 LLM 调用 =====
    tasks = [_process_batch(b, i) for b, i in batches]
    raw_batch_results = await asyncio.gather(*tasks)

    # ===== 顺序入库（DB 操作必须串行） =====
    all_ui_cases = []
    all_api_cases = []
    case_counter = 0

    for batch, batch_index, cases_data, error in raw_batch_results:
        if error:
            logger.warning(f"[Stage 3] 跳过失败批次 {batch_index+1}: {error}")
            continue

        raw_cases = (
            cases_data if isinstance(cases_data, list)
            else (cases_data.get("cases", []) if isinstance(cases_data, dict) else [])
        )
        logger.info(f"[Stage 3] 批次 {batch_index+1} raw_cases={len(raw_cases)}, expect={len(batch)}")

        ui_saved = 0
        api_saved = 0

        for case_data in raw_cases:
            try:
                if not isinstance(case_data, dict):
                    continue

                # 适配千问打平格式
                ui_raw = case_data.get("ui_case")
                if not isinstance(ui_raw, dict):
                    case_data = _normalize_qwen_flattened_case(case_data)

                tp_title = case_data.get("test_point_title", "")
                tp = next((t for t in batch if t.title == tp_title), None)
                if tp is None and tp_title:
                    for t in batch:
                        if t.title in tp_title or tp_title.endswith(t.title):
                            tp = t
                            break

                # UI Case
                ui = case_data.get("ui_case")
                if ui and isinstance(ui, dict) and ui.get("steps"):
                    case_counter += 1
                    case_id = f"TC-{datetime.now().strftime('%Y')}-{_run_id}-{case_counter:04d}"
                    steps = ui.get("steps", [])
                    if not isinstance(steps, list):
                        steps = []
                    for step in steps:
                        if isinstance(step, dict):
                            step.setdefault("locked", False)
                            step.setdefault("last_modified_by", "AI")

                    test_case = TestCase(
                        case_id=case_id, requirement_id=requirement_id,
                        test_point_id=tp.id if tp else None,
                        title=ui.get("title", f"UI-{tp_title}"),
                        precondition=ui.get("precondition", ""),
                        steps=steps,
                        expected_result=ui.get("expected_result", ""),
                        test_data=ui.get("test_data"),
                        case_type="UI",
                        priority=ui.get("priority", "P1"),
                        tags=ui.get("tags", []),
                        is_confirmed=False, created_by="AI",
                    )
                    db.add(test_case)
                    await db.flush()

                    if tp:
                        link = TraceabilityLink(
                            source_type="test_point", source_id=tp.id,
                            target_type="test_case", target_id=test_case.id,
                            relation="implemented_by", created_by="AI",
                        )
                        db.add(link)

                    cv = CaseVersion(
                        test_case_id=test_case.id, version=1,
                        steps=steps, expected_result=test_case.expected_result,
                        change_reason="AI 自动生成",
                    )
                    db.add(cv)

                    all_ui_cases.append({
                        "id": test_case.id, "case_id": case_id,
                        "title": test_case.title, "priority": test_case.priority,
                    })
                    ui_saved += 1

                # API Case
                if generate_both:
                    api = case_data.get("api_case")
                    if api and isinstance(api, dict) and api.get("steps"):
                        case_counter += 1
                        case_id = f"TC-{datetime.now().strftime('%Y')}-{_run_id}-{case_counter:04d}"
                        steps = api.get("steps", [])
                        if not isinstance(steps, list):
                            steps = []
                        for step in steps:
                            if isinstance(step, dict):
                                step.setdefault("locked", False)
                                step.setdefault("last_modified_by", "AI")

                        test_case = TestCase(
                            case_id=case_id, requirement_id=requirement_id,
                            test_point_id=tp.id if tp else None,
                            title=api.get("title", f"API-{tp_title}"),
                            precondition=api.get("precondition", ""),
                            steps=steps,
                            expected_result=api.get("expected_result", ""),
                            test_data=api.get("test_data"),
                            case_type="API",
                            priority=api.get("priority", "P1"),
                            tags=api.get("tags", []),
                            is_confirmed=False, created_by="AI",
                        )
                        db.add(test_case)
                        await db.flush()

                        if tp:
                            link = TraceabilityLink(
                                source_type="test_point", source_id=tp.id,
                                target_type="test_case", target_id=test_case.id,
                                relation="implemented_by", created_by="AI",
                            )
                            db.add(link)

                        cv = CaseVersion(
                            test_case_id=test_case.id, version=1,
                            steps=steps, expected_result=test_case.expected_result,
                            change_reason="AI 自动生成",
                        )
                        db.add(cv)

                        all_api_cases.append({
                            "id": test_case.id, "case_id": case_id,
                            "title": test_case.title, "priority": test_case.priority,
                        })
                        api_saved += 1

            except Exception as case_err:
                logger.warning(f"[Stage 3] 单条用例保存失败: {case_err}")
                continue

        logger.info(f"[Stage 3] 批次 {batch_index+1} 入库: UI={ui_saved}, API={api_saved}")
        await db.flush()

    # 4. 验证生成结果并更新需求状态
    total = len(all_ui_cases) + len(all_api_cases)
    logger.info(f"[Stage 3] 用例生成完成: UI={len(all_ui_cases)}, API={len(all_api_cases)}, 总计={total}")

    if total == 0:
        logger.error(f"[Stage 3] LLM 返回了空结果，0 条用例入库。请检查 LLM provider 响应格式是否正确")
        raise RuntimeError(
            f"用例生成失败：LLM 未返回任何有效用例（共处理 {len(test_points)} 个测试点）。"
            f"请检查 LLM provider 配置或稍后重试。"
        )

    req.status = RequirementStatus.CASES_GENERATED
    req.updated_at = datetime.now()
    await db.flush()

    # 导出 XMind 文件（基于 test-case-generator skill 规范）
    xmind_path = ""
    try:
        xmind_output_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "storage", "xmind_export"
        )
        xmind_path = export_xmind(all_ui_cases, all_api_cases, req.title, xmind_output_dir)
    except Exception as xmind_err:
        logger.error(f"[XMind] 导出失败: {xmind_err}", exc_info=True)

    return {
        "status": "success",
        "message": f"生成了 {total} 条用例 (UI: {len(all_ui_cases)}, API: {len(all_api_cases)})",
        "data": {
            "requirement_id": requirement_id,
            "ui_count": len(all_ui_cases),
            "api_count": len(all_api_cases),
            "ui_cases": all_ui_cases,
            "api_cases": all_api_cases,
            "xmind_file": xmind_path,
        },
    }


def _normalize_qwen_flattened_case(case_data: dict) -> dict:
    """
    千问 json_object 模式可能输出打平的结构（steps/ui_case 属性直接放在顶层）。
    检测到 ui_case 不是 dict 时，从顶层字段重建标准嵌套格式。
    """
    ui = case_data.get("ui_case")
    if isinstance(ui, dict):
        return case_data  # 已经是正确格式，无需处理

    # --- 重建 ui_case ---
    ui_case: dict = {}

    # 标题：优先用顶层 title，否则从 test_point_title 派生
    raw_title = case_data.get("title", "")
    if raw_title and isinstance(raw_title, str) and raw_title not in (
        "title", "steps", "precondition", "expected_result",
        "test_data", "priority", "tags", "action",
    ):
        ui_case["title"] = raw_title
    else:
        tp = case_data.get("test_point_title", "")
        # 去掉 test_point_title 前缀中的维度/优先级标记
        if tp.startswith("[") and "]" in tp:
            tp = tp.split("]", 1)[-1] if len(tp.split("]", 1)) > 1 else tp
        ui_case["title"] = f"UI-{tp}" if tp else "UI-未命名用例"

    # 前置条件
    pre = case_data.get("precondition", "")
    if pre and isinstance(pre, str) and len(pre) > 3:
        ui_case["precondition"] = pre
    else:
        ui_case["precondition"] = ""

    # 预期结果
    er = case_data.get("expected_result", "")
    if er and isinstance(er, str) and len(er) > 3:
        ui_case["expected_result"] = er
    else:
        ui_case["expected_result"] = ""

    # 优先级
    p = case_data.get("priority", "P1")
    if isinstance(p, str) and p in ("P0", "P1", "P2", "P3"):
        ui_case["priority"] = p
    else:
        ui_case["priority"] = "P1"

    # 测试数据
    td = case_data.get("test_data")
    if isinstance(td, dict):
        ui_case["test_data"] = td
    elif isinstance(td, str) and td and td not in ("test_data", "batch_number"):
        ui_case["test_data"] = {td: ""}
    else:
        ui_case["test_data"] = {}

    # 标签
    tags = case_data.get("tags", [])
    if isinstance(tags, list):
        ui_case["tags"] = tags
    elif isinstance(tags, str) and tags and tags not in ("tags", "销售"):
        ui_case["tags"] = [tags]
    else:
        ui_case["tags"] = []

    # --- 重建 steps ---
    steps: list = []
    action = case_data.get("action", "")
    target = case_data.get("target", "")
    if action and isinstance(action, str) and action not in ("action", "title"):
        step = {
            "action": action if action != "action" else "断言",
            "target": target if isinstance(target, str) and target not in ("target", "") else "",
            "value": case_data.get("value", "") if isinstance(case_data.get("value"), str) else "",
            "expected": case_data.get("expected", "") if isinstance(case_data.get("expected"), str) else "",
            "locked": bool(case_data.get("locked", False)),
            "last_modified_by": str(case_data.get("last_modified_by", "AI")),
        }
        steps.append(step)

    # 如果步骤中有 "action" 这样的占位符值，清理掉
    cleaned_steps = []
    for s in steps:
        cs = {}
        for k, v in s.items():
            if isinstance(v, str) and v in ("action", "target", "value", "expected",
                                              "locked", "last_modified_by"):
                cs[k] = ""
            else:
                cs[k] = v
        # 至少要有 action 和 target
        if cs.get("action"):
            cleaned_steps.append(cs)

    ui_case["steps"] = cleaned_steps if cleaned_steps else steps

    return {
        "test_point_title": case_data.get("test_point_title", ""),
        "ui_case": ui_case,
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
    if not isinstance(entities, dict):
        entities = {}
    if entities.get("pages"):
        lines.append(f"- 涉及页面: {', '.join(entities['pages'])}")
    if entities.get("apis"):
        lines.append(f"- 涉及接口: {', '.join(entities['apis'])}")
    if entities.get("roles"):
        lines.append(f"- 涉及角色: {', '.join(entities['roles'])}")

    lines.append("")
    return "\n".join(lines)


# ==================== XMind 导出（基于 test-case-generator skill） ====================

import zipfile
import os
import html


def _esc(s):
    return html.escape(str(s) if s else "", quote=False)


def _make_tc_xml(tc: dict, id_counter: list) -> str:
    """生成单条测试用例的 XMind XML（3层结构）"""
    id_counter[0] += 1
    tc_id = f"t_{id_counter[0]}"
    title = tc.get("title", "未命名用例")
    if not title.startswith("TC:"):
        title = f"TC: {title}"

    priority_map = {"P0": "1", "P1": "2", "P2": "3"}
    p_num = priority_map.get(tc.get("priority", "P1"), "2")
    xml = f'<topic id="{tc_id}">'
    xml += f'<title>{_esc(title)}</title>'
    xml += f'<marker-refs><marker-ref marker-id="priority-{p_num}"/></marker-refs>'
    xml += '<children><topics type="attached">'

    # 前置条件
    if tc.get("precondition"):
        id_counter[0] += 1
        xml += f'<topic id="t_{id_counter[0]}"><title>前置：{_esc(tc["precondition"])}</title></topic>'

    # 操作步骤 + 预期结果
    steps = tc.get("steps", [])
    if isinstance(steps, list):
        for i, step in enumerate(steps):
            id_counter[0] += 1
            step_text = ""
            if isinstance(step, dict):
                action = step.get("action", "")
                target = step.get("target", "")
                value = step.get("value", "")
                parts = [action, target]
                if value:
                    parts.append(value)
                step_text = " → ".join([p for p in parts if p])
            elif isinstance(step, str):
                step_text = step
            xml += f'<topic id="t_{id_counter[0]}"><title>{_esc(step_text)}</title>'

            # 预期结果作为最后一步的子节点
            if i == len(steps) - 1 and tc.get("expected_result"):
                xml += '<children><topics type="attached">'
                id_counter[0] += 1
                xml += f'<topic id="t_{id_counter[0]}"><title>预期：{_esc(tc["expected_result"])}</title></topic>'
                xml += '</topics></children>'

            xml += '</topic>'

    xml += '</topics></children></topic>'
    return xml


def export_xmind(all_ui_cases: list, all_api_cases: list,
                 requirement_title: str, output_dir: str) -> str:
    """导出测试用例为 XMind 文件（XMind 8+ 格式）

    Args:
        all_ui_cases: UI 用例列表 [{id, case_id, title, priority, precondition?, steps?, expected_result?}]
        all_api_cases: API 用例列表
        requirement_title: 需求标题（用于文件名）
        output_dir: 输出目录

    Returns:
        str: 生成的 .xmind 文件路径
    """
    import datetime as dt

    modules_data = {}
    if all_ui_cases:
        modules_data["UI 用例"] = all_ui_cases
    if all_api_cases:
        modules_data["API 用例"] = all_api_cases

    if not modules_data:
        logger.warning("[XMind] 没有用例可导出")
        return ""

    id_counter = [0]
    content = '<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n'
    content += '<xmap-content xmlns="urn:xmind:xmap:xmlns:content:2.0" xmlns:fo="http://www.w3.org/1999/XSL/Format" xmlns:svg="http://www.w3.org/2000/svg" xmlns:xhtml="http://www.w3.org/1999/xhtml" xmlns:xlink="http://www.w3.org/1999/xlink">'
    content += '<sheet id="sheet1"><title>测试用例</title>'
    content += '<topic id="root"><title>测试用例</title><children><topics type="attached">'

    for module, cases in modules_data.items():
        id_counter[0] += 1
        content += f'<topic id="t_{id_counter[0]}"><title>{_esc(module)}</title><children><topics type="attached">'
        for tc in cases:
            content += _make_tc_xml(tc, id_counter)
        content += '</topics></children></topic>'

    content += '</topics></children></topic></sheet></xmap-content>'

    styles = '''<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<xmap-styles xmlns="urn:xmind:xmap:xmlns:style:2.0" xmlns:fo="http://www.w3.org/1999/XSL/Format">
<styles>
<style id="priority-1" type="priority"><marker-id>flag-priority-1</marker-id></style>
<style id="priority-2" type="priority"><marker-id>flag-priority-2</marker-id></style>
<style id="priority-3" type="priority"><marker-id>flag-priority-3</marker-id></style>
</styles>
<markers>
<marker-group id="priority" display-name="Priority">
<shapes>
<shape id="flag-priority-1" display-name="P0" shape="star"/>
<shape id="flag-priority-2" display-name="P1" shape="circle"/>
<shape id="flag-priority-3" display-name="P2" shape="triangle"/>
</shapes>
</marker-group>
</markers>
</xmap-styles>'''

    manifest = '<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n<manifest xmlns="urn:xmind:xmap:xmlns:manifest:1.0">\n<file-entry full-path="content.xml" media-type="text/xml"/>\n<file-entry full-path="styles.xml" media-type="text/xml"/>\n<file-entry full-path="META-INF/" media-type=""/>\n<file-entry full-path="META-INF/manifest.xml" media-type="text/xml"/>\n</manifest>'

    meta = f'<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n<meta xmlns="urn:xmind:xmap:xmlns:meta:2.0" version="2.0">\n<Author><Name>AI Test Platform</Name></Author>\n<CreateDate>{dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")}</CreateDate>\n</meta>'

    safe_title = "".join(c for c in requirement_title if c.isalnum() or c in ('_', '-', ' ')).strip()[:50] or "test_cases"
    filename = f"{safe_title}_测试用例.xmind"
    filepath = os.path.join(output_dir, filename)

    os.makedirs(output_dir, exist_ok=True)
    with zipfile.ZipFile(filepath, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('content.xml', content)
        zf.writestr('styles.xml', styles)
        zf.writestr('META-INF/manifest.xml', manifest)
        zf.writestr('meta.xml', meta)

    logger.info(f"[XMind] 用例导出成功: {filepath} (UI:{len(all_ui_cases)}, API:{len(all_api_cases)})")
    return filepath
