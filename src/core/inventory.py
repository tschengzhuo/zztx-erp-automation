"""
库存计算核心逻辑
封装库存查询、扣减、预警等业务规则
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

from src.common.exceptions import SyncException
from src.common.logger import get_logger

logger = get_logger(__name__)


@dataclass
class InventoryItem:
    """库存项"""
    sku: str
    warehouse_id: str
    available_qty: int
    reserved_qty: int = 0
    locked_qty: int = 0
    reorder_point: int = 0
    reorder_qty: int = 0
    updated_at: Optional[datetime] = None

    def __post_init__(self):
        if self.updated_at is None:
            self.updated_at = datetime.now()

    @property
    def total_qty(self) -> int:
        """库存总量"""
        return self.available_qty + self.reserved_qty + self.locked_qty

    @property
    def actual_available(self) -> int:
        """实际可用库存（扣除预占和锁定）"""
        return max(0, self.available_qty - self.reserved_qty - self.locked_qty)

    @property
    def is_low_stock(self) -> bool:
        """是否低库存"""
        return self.actual_available <= self.reorder_point


@dataclass
class StockMovement:
    """库存变动记录"""
    sku: str
    warehouse_id: str
    movement_type: str  # IN, OUT, ADJUST, TRANSFER
    quantity: int
    reference_id: Optional[str] = None
    remark: Optional[str] = None
    created_at: Optional[datetime] = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()


class InventoryManager:
    """库存管理器"""

    def __init__(self):
        # 模拟库存数据存储，实际应用中应使用数据库
        self._inventory: Dict[str, InventoryItem] = {}

    def _make_key(self, sku: str, warehouse_id: str) -> str:
        """生成库存唯一键"""
        return f"{sku}@{warehouse_id}"

    def get_inventory(
        self,
        sku: str,
        warehouse_id: str
    ) -> Optional[InventoryItem]:
        """查询指定 SKU 在指定仓库的库存"""
        key = self._make_key(sku, warehouse_id)
        return self._inventory.get(key)

    def get_all_inventory(self) -> List[InventoryItem]:
        """获取所有库存"""
        return list(self._inventory.values())

    def update_inventory(self, item: InventoryItem) -> InventoryItem:
        """更新库存记录"""
        key = self._make_key(item.sku, item.warehouse_id)
        item.updated_at = datetime.now()
        self._inventory[key] = item
        logger.info(
            f"Inventory updated: {item.sku}@{item.warehouse_id}, "
            f"available={item.available_qty}"
        )
        return item

    def reserve_stock(
        self,
        sku: str,
        warehouse_id: str,
        quantity: int,
        order_id: str
    ) -> bool:
        """
        预占库存

        Args:
            sku: 商品 SKU
            warehouse_id: 仓库 ID
            quantity: 预占数量
            order_id: 关联订单 ID

        Returns:
            是否预占成功
        """
        item = self.get_inventory(sku, warehouse_id)
        if item is None:
            raise SyncException(f"Inventory not found for {sku}@{warehouse_id}")

        if item.actual_available < quantity:
            raise SyncException(
                f"Insufficient stock for {sku}: available={item.actual_available}, "
                f"required={quantity}"
            )

        item.reserved_qty += quantity
        self.update_inventory(item)

        movement = StockMovement(
            sku=sku,
            warehouse_id=warehouse_id,
            movement_type="RESERVE",
            quantity=-quantity,
            reference_id=order_id,
            remark=f"Reserved for order {order_id}"
        )
        logger.info(f"Stock reserved: {sku} x{quantity} for order {order_id}")
        return True

    def release_stock(
        self,
        sku: str,
        warehouse_id: str,
        quantity: int,
        order_id: str
    ) -> bool:
        """释放预占库存"""
        item = self.get_inventory(sku, warehouse_id)
        if item is None:
            raise SyncException(f"Inventory not found for {sku}@{warehouse_id}")

        item.reserved_qty = max(0, item.reserved_qty - quantity)
        self.update_inventory(item)

        logger.info(f"Stock released: {sku} x{quantity} for order {order_id}")
        return True

    def deduct_stock(
        self,
        sku: str,
        warehouse_id: str,
        quantity: int,
        order_id: str
    ) -> bool:
        """
        扣减库存（出库）

        Args:
            sku: 商品 SKU
            warehouse_id: 仓库 ID
            quantity: 出库数量
            order_id: 关联订单 ID

        Returns:
            是否扣减成功
        """
        item = self.get_inventory(sku, warehouse_id)
        if item is None:
            raise SyncException(f"Inventory not found for {sku}@{warehouse_id}")

        if item.available_qty < quantity:
            raise SyncException(
                f"Insufficient available stock for {sku}: "
                f"available={item.available_qty}, required={quantity}"
            )

        item.available_qty -= quantity
        item.reserved_qty = max(0, item.reserved_qty - quantity)
        self.update_inventory(item)

        movement = StockMovement(
            sku=sku,
            warehouse_id=warehouse_id,
            movement_type="OUT",
            quantity=-quantity,
            reference_id=order_id,
            remark=f"Shipped for order {order_id}"
        )
        logger.info(f"Stock deducted: {sku} x{quantity} for order {order_id}")
        return True

    def get_low_stock_items(self) -> List[InventoryItem]:
        """获取所有低库存商品"""
        return [item for item in self._inventory.values() if item.is_low_stock]

    def check_stock_availability(
        self,
        sku: str,
        warehouse_id: str,
        quantity: int
    ) -> bool:
        """检查库存是否充足"""
        item = self.get_inventory(sku, warehouse_id)
        if item is None:
            return False
        return item.actual_available >= quantity
