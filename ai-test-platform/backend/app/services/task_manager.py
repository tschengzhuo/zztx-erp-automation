# 异步任务管理器 - 内存存储任务状态
# 用于 Stage 3 等耗时任务的异步执行 + 轮询

import asyncio
import logging
from datetime import datetime
from typing import Any, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)

# 任务状态: pending → running → completed / failed
# {task_id: {status, progress, total, message, result, error, created_at, updated_at}}
_tasks: dict[str, dict] = {}

# 最长保留已完成任务 30 分钟
_TASK_TTL_SECONDS = 30 * 60


def create_task() -> str:
    """创建任务并返回 task_id"""
    task_id = str(uuid4())
    _tasks[task_id] = {
        "status": "pending",
        "progress": 0,
        "total": 0,
        "message": "任务已创建，等待执行",
        "result": None,
        "error": None,
        "created_at": datetime.now(),
        "updated_at": datetime.now(),
    }
    return task_id


def update_task(task_id: str, **kwargs):
    """更新任务状态"""
    if task_id not in _tasks:
        return
    _tasks[task_id].update(kwargs)
    _tasks[task_id]["updated_at"] = datetime.now()


def get_task(task_id: str) -> Optional[dict]:
    """查询任务状态"""
    return _tasks.get(task_id)


def cleanup_expired():
    """清理过期任务"""
    now = datetime.now()
    expired = [
        tid for tid, t in _tasks.items()
        if t["status"] in ("completed", "failed")
        and (now - t["updated_at"]).total_seconds() > _TASK_TTL_SECONDS
    ]
    for tid in expired:
        del _tasks[tid]
    if expired:
        logger.debug(f"清理 {len(expired)} 个过期任务")


async def run_stage3_in_background(
    task_id: str,
    requirement_id: str,
    test_point_ids: list,
    generate_both: bool,
):
    """后台执行 Stage 3 用例生成"""
    from app.database import async_session
    from app.services.stage3_cases import generate_test_cases

    update_task(task_id, status="running", message="正在生成用例...", progress=0)

    def on_progress(current: int, total: int, msg: str):
        """批次进度回调"""
        update_task(
            task_id,
            message=msg,
            progress=current,
            total=total,
        )

    try:
        async with async_session() as db:
            result = await generate_test_cases(
                db,
                requirement_id,
                test_point_ids,
                generate_both,
                progress_callback=on_progress,
            )
            await db.commit()

        update_task(
            task_id,
            status="completed",
            progress=100,
            total=100,
            message=result.get("message", "用例生成完成"),
            result=result.get("data"),
        )
        logger.info(f"[TaskManager] 任务 {task_id} 完成: {result.get('message')}")
    except Exception as e:
        logger.error(f"[TaskManager] 任务 {task_id} 失败: {e}", exc_info=True)
        update_task(
            task_id,
            status="failed",
            message=f"生成失败: {str(e)}",
            error=str(e),
        )

    # 定期清理
    cleanup_expired()
