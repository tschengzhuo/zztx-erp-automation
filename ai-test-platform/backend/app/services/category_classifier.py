# AI Test Platform - Category Classifier Service
# 需求自动分类：LLM 分析需求内容，归入分类树，自动创建缺失节点

import json
import logging
from typing import Optional, List, Tuple

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models import ModuleCategory, Requirement
from app.llm_provider import get_llm_provider
from app.config import settings

logger = logging.getLogger(__name__)

# 分类分析 Prompt
CLASSIFICATION_SYSTEM_PROMPT = """你是一个需求分类专家。你需要根据需求文档的内容，将其归类到一个多层级的模块分类体系中。

## 任务
根据提供的需求标题和内容，分析该需求属于哪个业务模块，输出完整的三级分类路径（如：一级分类 > 二级分类 > 三级分类）。

## 分析维度
1. **业务领域**：需求涉及的顶层业务模块（如：订单管理、库存管理、财务管理、用户管理、报表分析等）
2. **子模块**：该业务领域下的具体功能模块（如：订单管理下的"商品汇总"、"订单审核"等）
3. **具体功能**：最细粒度的功能点（如："批次号管理"、"优惠券叠加"等）

## 已有分类（供参考，优先匹配已有分类）
{existing_categories}

## 输出规则
1. 分类路径应为 1~3 层（尽量使用已有分类）
2. 如果需求匹配某个已有分类的子功能，应创建新的子分类
3. 如果完全没有匹配的分类，则创建新的顶级分类
4. 分类名称应简洁业务化（2~6个汉字），禁止使用英文、代码字段名

## 输出格式
请只输出如下 JSON，不要任何额外文本：
```json
{{"category_path": ["一级分类", "二级分类", "三级分类"]}}
```

注意：路径长度可以是 1、2 或 3，根据需求粒度决定。"""


async def get_existing_category_tree(db: AsyncSession) -> List[dict]:
    """获取现有分类树结构（扁平列表，含完整路径）"""
    stmt = (
        select(ModuleCategory)
        .where(ModuleCategory.is_active == True)
        .options(selectinload(ModuleCategory.children))
        .order_by(ModuleCategory.sort_order)
    )
    result = await db.execute(stmt)
    items = result.unique().scalars().all()

    tree = []
    for item in items:
        if item.parent_id is None:
            path_parts = _get_category_path(item)
            tree.append({
                "id": item.id,
                "name": item.name,
                "path": " > ".join(path_parts),
                "children": _get_child_names(item),
            })
    return tree


def _get_category_path(cat: ModuleCategory) -> List[str]:
    """获取分类的完整路径（从根到当前节点）"""
    parts = [cat.name]
    parent = cat.parent
    while parent:
        parts.insert(0, parent.name)
        parent = parent.parent
    return parts


def _get_child_names(cat: ModuleCategory) -> List[str]:
    """获取子分类名称列表"""
    return [c.name for c in cat.children if c.is_active]


def _format_existing_categories(tree: List[dict]) -> str:
    """将分类树格式化为 LLM 可读的文本"""
    lines = []
    for item in tree:
        lines.append(f"- {item['path']}")
        for child in item.get("children", []):
            child_path = f"{item['path']} > {child}"
            lines.append(f"  - {child_path}")
    return "\n".join(lines) if lines else "（暂无分类）"


async def classify_requirement(title: str, raw_text: str, db: AsyncSession) -> List[str]:
    """
    使用 LLM 分析需求内容，返回建议的分类路径。
    返回：["一级", "二级", "三级"] 列表，长度 1~3
    """
    # 获取现有分类树
    tree = await get_existing_category_tree(db)
    existing_text = _format_existing_categories(tree)

    # 截取需求内容前 2000 字避免 token 浪费
    content_snippet = raw_text[:2000] if raw_text else ""

    system_prompt = CLASSIFICATION_SYSTEM_PROMPT.format(
        existing_categories=existing_text
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"## 需求标题\n{title}\n\n## 需求内容\n{content_snippet}"},
    ]

    try:
        provider = get_llm_provider()
        response = await provider.chat(
            messages=messages,
            temperature=0.1,
            max_tokens=512,
        )

        # 提取 JSON
        content = response.strip()
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        result = json.loads(content)
        path = result.get("category_path", [])

        if not path or not isinstance(path, list):
            logger.warning(f"[Classifier] LLM 返回的分类路径为空或格式错误: {result}")
            return [title[:10]]  # fallback：用标题前10字作为分类名

        # 清理路径（去除空白、限制长度）
        path = [p.strip()[:50] for p in path if p and p.strip()]
        if not path:
            return ["未分类"]

        logger.info(f"[Classifier] 需求 '{title}' 分类结果: {' > '.join(path)}")
        return path

    except Exception as e:
        logger.error(f"[Classifier] 分类失败: {e}")
        return ["未分类"]


async def ensure_category_path(
    db: AsyncSession,
    path: List[str],
) -> Tuple[ModuleCategory, List[str]]:
    """
    确保分类路径存在，自动创建缺失的节点。
    返回：(叶子节点分类, 完整路径列表)

    例如 path=["订单管理", "商品汇总", "批次管理"]：
    - 检查"订单管理"是否存在，不存在则创建
    - 检查"订单管理"下的"商品汇总"，不存在则创建
    - 检查"商品汇总"下的"批次管理"，不存在则创建
    - 返回 (批次管理节点, ["订单管理", "商品汇总", "批次管理"])
    """
    if not path:
        path = ["未分类"]

    current_parent_id = None
    created_nodes = []

    for i, name in enumerate(path):
        # 查找当前层级下是否已有同名的活动分类
        stmt = select(ModuleCategory).where(
            ModuleCategory.name == name,
            ModuleCategory.parent_id == current_parent_id,
            ModuleCategory.is_active == True,
        )
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            current_parent_id = existing.id
        else:
            # 自动创建缺失的分类节点
            new_cat = ModuleCategory(
                name=name,
                parent_id=current_parent_id,
                sort_order=i * 10,  # 按层级排
                description=f"自动创建于需求分类",
            )
            db.add(new_cat)
            await db.flush()
            current_parent_id = new_cat.id
            created_nodes.append(name)
            logger.info(f"[Classifier] 自动创建分类: {' > '.join(path[:i+1])}")

    if created_nodes:
        await db.flush()

    # 获取叶子节点
    leaf = await db.get(ModuleCategory, current_parent_id)
    return leaf, path
