"""
每日数据同步任务
从 ERP 系统同步订单、库存等数据到本地数据库
"""

import os
from datetime import datetime, timedelta

import yaml
from dotenv import load_dotenv

from src.common.exceptions import SyncException
from src.common.logger import setup_logger
from src.connectors.db_client import DBClient
from src.connectors.erp_api import ERPAPIConnector
from src.core.inventory import InventoryItem, InventoryManager
from src.core.order_flow import Order, OrderItem, OrderProcessor

logger = setup_logger("daily_sync", level="INFO")


def load_config(env: str = None) -> dict:
    """加载配置文件"""
    if env is None:
        env = os.getenv("APP_ENV", "dev")

    config_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "config", f"{env}.yaml"
    )

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # 替换环境变量
    def replace_env_vars(obj):
        if isinstance(obj, str) and obj.startswith("${") and obj.endswith("}"):
            env_var = obj[2:-1]
            return os.getenv(env_var, obj)
        return obj

    def traverse(d):
        if isinstance(d, dict):
            return {k: traverse(v) for k, v in d.items()}
        elif isinstance(d, list):
            return [traverse(i) for i in d]
        else:
            return replace_env_vars(d)

    return traverse(config)


class DailySyncTask:
    """每日数据同步任务"""

    def __init__(self, config: dict):
        self.config = config
        self.erp = ERPAPIConnector(
            base_url=config["erp"]["base_url"],
            timeout=config["erp"]["timeout"],
            retry_times=config["erp"]["retry_times"]
        )

        db_config = config["database"]
        connection_string = (
            f"mysql+pymysql://{db_config['user']}:{db_config['password']}"
            f"@{db_config['host']}:{db_config['port']}/{db_config['name']}"
        )
        self.db = DBClient(connection_string)
        self.order_processor = OrderProcessor()
        self.inventory_manager = InventoryManager()

    def sync_orders(self, start_date: datetime = None, end_date: datetime = None):
        """
        同步订单数据

        Args:
            start_date: 开始日期，默认为昨天
            end_date: 结束日期，默认为今天
        """
        if start_date is None:
            start_date = datetime.now() - timedelta(days=1)
        if end_date is None:
            end_date = datetime.now()

        logger.info(
            f"Starting order sync from {start_date.isoformat()} to {end_date.isoformat()}"
        )

        try:
            params = {
                "start_date": start_date.strftime("%Y-%m-%d %H:%M:%S"),
                "end_date": end_date.strftime("%Y-%m-%d %H:%M:%S"),
                "page": 1,
                "page_size": self.config["sync"]["batch_size"]
            }

            response = self.erp.get("/orders", params=params)
            orders_data = response.get("data", [])

            logger.info(f"Fetched {len(orders_data)} orders from ERP")

            for order_data in orders_data:
                try:
                    self._process_single_order(order_data)
                except Exception as e:
                    logger.error(f"Failed to process order {order_data.get('order_id')}: {e}")

            logger.info("Order sync completed")

        except Exception as e:
            logger.error(f"Order sync failed: {e}")
            raise SyncException(f"Order sync failed: {e}")

    def _process_single_order(self, order_data: dict):
        """处理单个订单数据"""
        items = [
            OrderItem(
                sku=item["sku"],
                name=item.get("name", ""),
                quantity=item["quantity"],
                unit_price=item["unit_price"],
                discount=item.get("discount", 0.0)
            )
            for item in order_data.get("items", [])
        ]

        order = Order(
            order_id=order_data["order_id"],
            customer_id=order_data["customer_id"],
            items=items,
            shipping_address=order_data.get("shipping_address"),
            remark=order_data.get("remark")
        )

        self.order_processor.validate_order(order)

        # 保存到数据库
        self._save_order_to_db(order)

    def _save_order_to_db(self, order: Order):
        """将订单保存到数据库"""
        sql = """
            INSERT INTO orders (order_id, customer_id, total_amount, total_quantity,
                              status, payment_status, shipping_address, remark, created_at)
            VALUES (:order_id, :customer_id, :total_amount, :total_quantity,
                   :status, :payment_status, :shipping_address, :remark, :created_at)
            ON DUPLICATE KEY UPDATE
                status = VALUES(status),
                payment_status = VALUES(payment_status),
                updated_at = NOW()
        """
        self.db.execute_update(sql, {
            "order_id": order.order_id,
            "customer_id": order.customer_id,
            "total_amount": order.total_amount,
            "total_quantity": order.total_quantity,
            "status": order.status.value,
            "payment_status": order.payment_status.value,
            "shipping_address": order.shipping_address,
            "remark": order.remark,
            "created_at": order.created_at
        })
        logger.debug(f"Order {order.order_id} saved to database")

    def sync_inventory(self):
        """同步库存数据"""
        logger.info("Starting inventory sync")

        try:
            response = self.erp.get("/inventory")
            inventory_data = response.get("data", [])

            logger.info(f"Fetched {len(inventory_data)} inventory records from ERP")

            for item_data in inventory_data:
                item = InventoryItem(
                    sku=item_data["sku"],
                    warehouse_id=item_data["warehouse_id"],
                    available_qty=item_data["available_qty"],
                    reserved_qty=item_data.get("reserved_qty", 0),
                    locked_qty=item_data.get("locked_qty", 0),
                    reorder_point=item_data.get("reorder_point", 0),
                    reorder_qty=item_data.get("reorder_qty", 0)
                )
                self.inventory_manager.update_inventory(item)
                self._save_inventory_to_db(item)

            # 检查低库存
            low_stock_items = self.inventory_manager.get_low_stock_items()
            if low_stock_items:
                logger.warning(f"Found {len(low_stock_items)} low stock items")
                for item in low_stock_items:
                    logger.warning(
                        f"Low stock alert: {item.sku}@{item.warehouse_id}, "
                        f"available={item.actual_available}"
                    )

            logger.info("Inventory sync completed")

        except Exception as e:
            logger.error(f"Inventory sync failed: {e}")
            raise SyncException(f"Inventory sync failed: {e}")

    def _save_inventory_to_db(self, item: InventoryItem):
        """将库存保存到数据库"""
        sql = """
            INSERT INTO inventory (sku, warehouse_id, available_qty, reserved_qty,
                                 locked_qty, reorder_point, reorder_qty, updated_at)
            VALUES (:sku, :warehouse_id, :available_qty, :reserved_qty,
                   :locked_qty, :reorder_point, :reorder_qty, :updated_at)
            ON DUPLICATE KEY UPDATE
                available_qty = VALUES(available_qty),
                reserved_qty = VALUES(reserved_qty),
                locked_qty = VALUES(locked_qty),
                updated_at = VALUES(updated_at)
        """
        self.db.execute_update(sql, {
            "sku": item.sku,
            "warehouse_id": item.warehouse_id,
            "available_qty": item.available_qty,
            "reserved_qty": item.reserved_qty,
            "locked_qty": item.locked_qty,
            "reorder_point": item.reorder_point,
            "reorder_qty": item.reorder_qty,
            "updated_at": item.updated_at
        })
        logger.debug(f"Inventory {item.sku}@{item.warehouse_id} saved to database")

    def run(self):
        """执行完整的每日同步任务"""
        logger.info("=" * 50)
        logger.info("Daily sync task started")
        logger.info("=" * 50)

        try:
            self.sync_orders()
            self.sync_inventory()
            logger.info("Daily sync task completed successfully")
        except Exception as e:
            logger.error(f"Daily sync task failed: {e}")
            raise


def main():
    """任务入口"""
    load_dotenv()
    config = load_config()
    task = DailySyncTask(config)
    task.run()


if __name__ == "__main__":
    main()
