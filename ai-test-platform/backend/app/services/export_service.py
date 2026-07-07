# AI Test Platform - Export Service
# 用例导出: JSON / Excel / XMind / Markdown

import json
import logging
import os
from datetime import datetime
from typing import List, Dict, Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

from app.models import Requirement, TestPoint, TestCase
from app.config import settings

logger = logging.getLogger(__name__)


# ==================== JSON 导出 ====================

async def export_json(db: AsyncSession, requirement_id: str) -> str:
    """导出为 JSON 格式"""
    req, test_points, test_cases = await _load_export_data(db, requirement_id)

    data = {
        "export_time": datetime.now().isoformat(),
        "requirement": {
            "id": req.id,
            "title": req.title,
            "module": req.module,
            "version": req.version,
            "feature_id": req.feature_id,
            "description": req.description,
            "functional_points": req.functional_points,
        },
        "test_points": [
            {
                "id": tp.id,
                "title": tp.title,
                "dimension": tp.dimension,
                "scenario_desc": tp.scenario_desc,
                "technique": tp.technique,
                "priority": tp.priority,
            }
            for tp in test_points
        ],
        "test_cases": _cases_to_dict(test_cases),
    }

    path = _get_export_path(requirement_id, "json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return path


# ==================== Excel 导出 ====================

async def export_xlsx(db: AsyncSession, requirement_id: str, include_summary: bool = True) -> str:
    """导出为 Excel 格式，含样式"""
    req, test_points, test_cases = await _load_export_data(db, requirement_id)

    wb = openpyxl.Workbook()

    # 样式定义
    header_font = Font(bold=True, size=12, color="FFFFFF")
    header_fill = PatternFill(start_color="185FA5", end_color="185FA5", fill_type="solid")
    p0_fill = PatternFill(start_color="FFE0E0", end_color="FFE0E0", fill_type="solid")
    thin_border = Border(
        left=Side(style='thin'), right=Side(style='thin'),
        top=Side(style='thin'), bottom=Side(style='thin'),
    )

    # Sheet 1: 需求概览
    if include_summary:
        ws_summary = wb.active
        ws_summary.title = "需求概览"
        summary_data = [
            ["字段", "内容"],
            ["需求标题", req.title],
            ["所属模块", req.module],
            ["版本", str(req.version)],
            ["Feature ID", req.feature_id or ""],
            ["描述", req.description or ""],
            ["功能点数量", str(len(req.functional_points or []))],
            ["测试点数量", str(len(test_points))],
            ["用例数量(UI)", str(sum(1 for tc in test_cases if tc.case_type == "UI"))],
            ["用例数量(API)", str(sum(1 for tc in test_cases if tc.case_type == "API"))],
        ]
        for row in summary_data:
            ws_summary.append(row)
        _style_header(ws_summary, header_font, header_fill)
        ws_summary.column_dimensions['A'].width = 16
        ws_summary.column_dimensions['B'].width = 60

    # Sheet 2: 测试点
    ws_tp = wb.create_sheet("测试点")
    tp_headers = ["序号", "测试点", "维度", "测试技法", "优先级", "场景描述"]
    ws_tp.append(tp_headers)
    for i, tp in enumerate(test_points, 1):
        ws_tp.append([i, tp.title, tp.dimension, tp.technique, tp.priority, tp.scenario_desc])
    _style_header(ws_tp, header_font, header_fill)
    ws_tp.column_dimensions['A'].width = 8
    ws_tp.column_dimensions['B'].width = 40
    ws_tp.column_dimensions['C'].width = 14
    ws_tp.column_dimensions['D'].width = 16
    ws_tp.column_dimensions['E'].width = 10
    ws_tp.column_dimensions['F'].width = 60

    # Sheet 3: UI 用例
    _write_cases_sheet(wb, "UI用例", [tc for tc in test_cases if tc.case_type == "UI"],
                       header_font, header_fill, p0_fill)

    # Sheet 4: API 用例
    api_cases = [tc for tc in test_cases if tc.case_type == "API"]
    if api_cases:
        _write_cases_sheet(wb, "API用例", api_cases, header_font, header_fill, p0_fill)

    path = _get_export_path(requirement_id, "xlsx")
    wb.save(path)
    return path


def _write_cases_sheet(wb, title, cases, header_font, header_fill, p0_fill):
    """写入用例 sheet"""
    ws = wb.create_sheet(title)
    headers = ["序号", "用例ID", "用例标题", "优先级", "前置条件", "步骤(操作→目标→值)", "预期结果", "标签"]
    ws.append(headers)
    _style_header(ws, header_font, header_fill)

    for i, tc in enumerate(cases, 1):
        steps_text = "\n".join([
            f"{j}. {s.get('action','')} → {s.get('target','')} → {s.get('value','')}"
            for j, s in enumerate(tc.steps or [], 1)
        ])
        row = [i, tc.case_id, tc.title, tc.priority,
               tc.precondition or "", steps_text,
               tc.expected_result or "", ", ".join(tc.tags or [])]
        ws.append(row)
        if tc.priority == "P0":
            for cell in ws[ws.max_row]:
                cell.fill = p0_fill

    ws.column_dimensions['A'].width = 8
    ws.column_dimensions['B'].width = 18
    ws.column_dimensions['C'].width = 50
    ws.column_dimensions['D'].width = 10
    ws.column_dimensions['E'].width = 30
    ws.column_dimensions['F'].width = 60
    ws.column_dimensions['G'].width = 40
    ws.column_dimensions['H'].width = 20


def _style_header(ws, font, fill):
    """设置表头样式"""
    for cell in ws[1]:
        cell.font = font
        cell.fill = fill
        cell.alignment = Alignment(horizontal='center', vertical='center')


# ==================== XMind 导出 ====================

async def export_xmind(db: AsyncSession, requirement_id: str) -> str:
    """导出为 XMind 格式（JSON 兼容格式）"""
    req, test_points, test_cases = await _load_export_data(db, requirement_id)

    # 构建 XMind JSON 结构（兼容 XMind 8+）
    def _build_topic(title):
        return {"title": title, "children": {"attached": []}}

    root = _build_topic(req.title)
    root["children"]["attached"].append(_build_topic(f"模块: {req.module}"))

    # 按维度分组
    dim_groups: Dict[str, Any] = {}
    for tp in test_points:
        if tp.dimension not in dim_groups:
            dim_groups[tp.dimension] = _build_topic(tp.dimension)
        tp_topic = _build_topic(f"[{tp.priority}] {tp.title}")
        tp_topic["children"]["attached"].append(_build_topic(tp.scenario_desc))
        dim_groups[tp.dimension]["children"]["attached"].append(tp_topic)

    dim_node = _build_topic("测试点 (按维度)")
    for dim_topic in dim_groups.values():
        dim_node["children"]["attached"].append(dim_topic)
    root["children"]["attached"].append(dim_node)

    # 用例节点
    ui_cases = [tc for tc in test_cases if tc.case_type == "UI"]
    case_node = _build_topic(f"用例 ({len(ui_cases)}条)")
    for tc in ui_cases:
        tc_topic = _build_topic(f"[{tc.priority}] {tc.case_id}: {tc.title}")
        for step in (tc.steps or []):
            step_text = f"{step.get('action','')} → {step.get('target','')}"
            tc_topic["children"]["attached"].append(_build_topic(step_text))
        case_node["children"]["attached"].append(tc_topic)
    root["children"]["attached"].append(case_node)

    xmind_data = [{
        "id": "root",
        "title": "AI Test Platform Export",
        "rootTopic": root,
    }]

    path = _get_export_path(requirement_id, "xmind.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(xmind_data, f, ensure_ascii=False, indent=2)

    return path


# ==================== Markdown 导出 ====================

async def export_markdown(db: AsyncSession, requirement_id: str) -> str:
    """导出为 Markdown 格式"""
    req, test_points, test_cases = await _load_export_data(db, requirement_id)

    md_lines = [
        f"# {req.title}",
        f"",
        f"| 属性 | 值 |",
        f"|------|-----|",
        f"| 模块 | {req.module} |",
        f"| Feature ID | {req.feature_id or '-'} |",
        f"| 版本 | v{req.version} |",
        f"| 测试点数 | {len(test_points)} |",
        f"| 用例数(UI) | {sum(1 for tc in test_cases if tc.case_type == 'UI')} |",
        f"| 用例数(API) | {sum(1 for tc in test_cases if tc.case_type == 'API')} |",
        f"",
        f"## 需求描述",
        f"",
        f"{req.description or '无'}",
        f"",
        f"## 测试点清单",
        f"",
    ]

    for i, tp in enumerate(test_points, 1):
        md_lines.append(f"{i}. **[{tp.priority}] [{tp.dimension}]** {tp.title}")
        md_lines.append(f"   - 技法: {tp.technique}")
        md_lines.append(f"   - 场景: {tp.scenario_desc}")
        md_lines.append("")

    md_lines.extend(["## UI 用例", ""])
    for tc in [tc for tc in test_cases if tc.case_type == "UI"]:
        md_lines.append(f"### [{tc.priority}] {tc.case_id}: {tc.title}")
        md_lines.append(f"- 前置条件: {tc.precondition or '无'}")
        md_lines.append(f"- 步骤:")
        for j, step in enumerate(tc.steps or [], 1):
            md_lines.append(f"  {j}. `{step.get('action','')}` → {step.get('target','')} → {step.get('value','')}")
        md_lines.append(f"- 预期: {tc.expected_result or ''}")
        md_lines.append("")

    api_cases = [tc for tc in test_cases if tc.case_type == "API"]
    if api_cases:
        md_lines.extend(["## API 用例", ""])
        for tc in api_cases:
            md_lines.append(f"### [{tc.priority}] {tc.case_id}: {tc.title}")
            md_lines.append(f"- 前置条件: {tc.precondition or '无'}")
            md_lines.append(f"- 步骤:")
            for j, step in enumerate(tc.steps or [], 1):
                md_lines.append(f"  {j}. `{step.get('method','GET')} {step.get('target','')}`")
            md_lines.append(f"- 预期: {tc.expected_result or ''}")
            md_lines.append("")

    path = _get_export_path(requirement_id, "md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

    return path


# ==================== 辅助 ====================

async def _load_export_data(db: AsyncSession, requirement_id: str):
    """加载导出所需数据"""
    stmt = select(Requirement).where(Requirement.id == requirement_id)
    result = await db.execute(stmt)
    req = result.scalar_one_or_none()
    if not req:
        raise ValueError(f"Requirement not found: {requirement_id}")

    tp_stmt = select(TestPoint).where(TestPoint.requirement_id == requirement_id)
    tp_result = await db.execute(tp_stmt)
    test_points = tp_result.scalars().all()

    tc_stmt = select(TestCase).where(TestCase.requirement_id == requirement_id).order_by(TestCase.priority, TestCase.case_id)
    tc_result = await db.execute(tc_stmt)
    test_cases = tc_result.scalars().all()

    return req, test_points, test_cases


def _get_export_path(requirement_id: str, ext: str) -> str:
    """获取导出文件路径"""
    os.makedirs(settings.EXPORT_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return os.path.join(settings.EXPORT_DIR, f"export_{requirement_id[:8]}_{timestamp}.{ext}")


def _cases_to_dict(cases) -> list:
    """用例列表转字典"""
    return [
        {
            "case_id": tc.case_id,
            "title": tc.title,
            "case_type": tc.case_type,
            "priority": tc.priority,
            "precondition": tc.precondition,
            "steps": tc.steps,
            "expected_result": tc.expected_result,
            "test_data": tc.test_data,
            "tags": tc.tags,
        }
        for tc in cases
    ]
