# AI Test Platform - 种子数据
# 在全新部署时自动插入演示需求和用例数据

import logging
from datetime import datetime

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Requirement, RequirementStatus
from app.auth import hash_password
from app.models import User

logger = logging.getLogger(__name__)


SEED_USERNAME = "admin"
SEED_PASSWORD = "admin123"

SEED_REQUIREMENTS = [
    {
        "title": "用户登录功能",
        "module": "用户中心",
        "raw_text": "用户可以通过用户名和密码登录系统。登录成功后跳转到首页。支持记住密码功能。连续5次登录失败锁定账号15分钟。",
        "status": RequirementStatus.PARSED,
        "created_by": SEED_USERNAME,
    },
    {
        "title": "订单列表查询",
        "module": "订单管理",
        "raw_text": "用户可以在订单列表页查看所有订单。支持按订单号、状态、时间范围筛选。列表默认按创建时间倒序排列，每页显示20条。",
        "status": RequirementStatus.PARSED,
        "created_by": SEED_USERNAME,
    },
    {
        "title": "商品搜索与筛选",
        "module": "商品管理",
        "raw_text": "用户可以在搜索框输入关键词搜索商品。支持按分类、价格区间、品牌进行筛选。搜索结果支持按销量、价格、评分排序。",
        "status": RequirementStatus.DRAFT,
        "created_by": SEED_USERNAME,
    },
    {
        "title": "购物车增删改",
        "module": "购物车",
        "raw_text": "用户可以将商品加入购物车，修改商品数量，删除购物车中的商品。购物车支持全选和批量删除。商品库存不足时提示用户。",
        "status": RequirementStatus.DRAFT,
        "created_by": SEED_USERNAME,
    },
    {
        "title": "支付流程处理",
        "module": "支付中心",
        "raw_text": "用户确认订单后进入支付页面，支持微信支付和支付宝。支付成功后跳转到订单详情页。支付失败时显示失败原因并支持重新支付。",
        "status": RequirementStatus.DRAFT,
        "created_by": SEED_USERNAME,
    },
]


async def seed_database(db: AsyncSession) -> int:
    """插入种子数据，返回插入的记录数"""
    count = 0

    # 检查是否已有种子用户
    result = await db.execute(select(User).where(User.username == SEED_USERNAME))
    if result.scalar_one_or_none() is None:
        user = User(
            username=SEED_USERNAME,
            display_name="管理员",
            password_hash=hash_password(SEED_PASSWORD),
            is_active=True,
        )
        db.add(user)
        logger.info(f"[Seed] Created user: {SEED_USERNAME}")
        count += 1

    # 检查是否已有种子需求
    result = await db.execute(select(func.count()).select_from(Requirement))
    existing = result.scalar()
    if existing > 0:
        logger.info(f"[Seed] Database already has {existing} requirements, skipping seed")
        return count

    # 插入需求
    for req_data in SEED_REQUIREMENTS:
        req = Requirement(
            title=req_data["title"],
            module=req_data["module"],
            raw_text=req_data["raw_text"],
            source="seed",
            status=req_data["status"],
            created_by=req_data["created_by"],
        )
        db.add(req)
        count += 1

    logger.info(f"[Seed] Inserted {count} seed records")
    return count
