"""
订单处理核心逻辑
封装订单生命周期中的业务规则
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import List, Optional

from src.common.exceptions import SyncException
from src.common.logger import get_logger

logger = get_logger(__name__)


class OrderStatus(str, Enum):
    """订单状态枚举"""
    PENDING = "pending"
    CONFIRMED = "confirmed"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class PaymentStatus(str, Enum):
    """支付状态枚举"""
    UNPAID = "unpaid"
    PAID = "paid"
    REFUNDED = "refunded"
    PARTIAL = "partial"


@dataclass
class OrderItem:
    """订单商品项"""
    sku: str
    name: str
    quantity: int
    unit_price: float
    discount: float = 0.0

    @property
    def subtotal(self) -> float:
        """计算商品小计"""
        return (self.unit_price - self.discount) * self.quantity


@dataclass
class Order:
    """订单实体"""
    order_id: str
    customer_id: str
    items: List[OrderItem]
    status: OrderStatus = OrderStatus.PENDING
    payment_status: PaymentStatus = PaymentStatus.UNPAID
    created_at: datetime = None
    updated_at: datetime = None
    shipping_address: Optional[str] = None
    remark: Optional[str] = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.updated_at is None:
            self.updated_at = datetime.now()

    @property
    def total_amount(self) -> float:
        """计算订单总金额"""
        return sum(item.subtotal for item in self.items)

    @property
    def total_quantity(self) -> int:
        """计算订单总数量"""
        return sum(item.quantity for item in self.items)


class OrderProcessor:
    """订单处理器"""

    def __init__(self):
        self._status_transitions = {
            OrderStatus.PENDING: [OrderStatus.CONFIRMED, OrderStatus.CANCELLED],
            OrderStatus.CONFIRMED: [OrderStatus.PROCESSING, OrderStatus.CANCELLED],
            OrderStatus.PROCESSING: [OrderStatus.SHIPPED],
            OrderStatus.SHIPPED: [OrderStatus.COMPLETED],
            OrderStatus.COMPLETED: [],
            OrderStatus.CANCELLED: [],
        }

    def validate_order(self, order: Order) -> bool:
        """
        验证订单数据有效性

        Args:
            order: 订单对象

        Returns:
            是否有效

        Raises:
            SyncException: 验证失败时抛出
        """
        if not order.items:
            raise SyncException(f"Order {order.order_id} has no items")

        for item in order.items:
            if item.quantity <= 0:
                raise SyncException(
                    f"Order {order.order_id}: item {item.sku} quantity must be positive"
                )
            if item.unit_price < 0:
                raise SyncException(
                    f"Order {order.order_id}: item {item.sku} unit_price cannot be negative"
                )

        logger.info(f"Order {order.order_id} validation passed")
        return True

    def transition_status(
        self,
        order: Order,
        new_status: OrderStatus
    ) -> Order:
        """
        转换订单状态

        Args:
            order: 订单对象
            new_status: 目标状态

        Returns:
            更新后的订单对象

        Raises:
            SyncException: 状态转换不合法时抛出
        """
        allowed = self._status_transitions.get(order.status, [])
        if new_status not in allowed:
            raise SyncException(
                f"Invalid status transition: {order.status.value} -> {new_status.value}"
            )

        old_status = order.status
        order.status = new_status
        order.updated_at = datetime.now()
        logger.info(
            f"Order {order.order_id} status changed: {old_status.value} -> {new_status.value}"
        )
        return order

    def confirm_order(self, order: Order) -> Order:
        """确认订单"""
        self.validate_order(order)
        return self.transition_status(order, OrderStatus.CONFIRMED)

    def cancel_order(self, order: Order, reason: Optional[str] = None) -> Order:
        """取消订单"""
        if reason:
            order.remark = f"Cancelled: {reason}"
        return self.transition_status(order, OrderStatus.CANCELLED)
