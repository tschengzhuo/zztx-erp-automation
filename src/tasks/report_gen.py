"""
报表生成任务
支持订单报表、库存报表、销售统计等
"""

import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

import yaml
from dotenv import load_dotenv

from src.common.exceptions import ReportException
from src.common.logger import setup_logger
from src.connectors.db_client import DBClient

logger = setup_logger("report_gen", level="INFO")


def load_config(env: str = None) -> dict:
    """加载配置文件"""
    if env is None:
        env = os.getenv("APP_ENV", "dev")

    config_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "config", f"{env}.yaml"
    )

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

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


class ReportGenerator:
    """报表生成器"""

    def __init__(self, config: dict):
        self.config = config
        self.output_dir = Path(config["report"]["output_dir"])
        self.output_dir.mkdir(parents=True, exist_ok=True)

        db_config = config["database"]
        connection_string = (
            f"mysql+pymysql://{db_config['user']}:{db_config['password']}"
            f"@{db_config['host']}:{db_config['port']}/{db_config['name']}"
        )
        self.db = DBClient(connection_string)

    def generate_daily_order_report(
        self,
        report_date: datetime = None
    ) -> str:
        """
        生成每日订单报表

        Args:
            report_date: 报表日期，默认为昨天

        Returns:
            生成的报表文件路径
        """
        if report_date is None:
            report_date = datetime.now() - timedelta(days=1)

        date_str = report_date.strftime("%Y-%m-%d")
        logger.info(f"Generating daily order report for {date_str}")

        try:
            sql = """
                SELECT
                    status,
                    payment_status,
                    COUNT(*) as order_count,
                    SUM(total_amount) as total_amount,
                    SUM(total_quantity) as total_quantity
                FROM orders
                WHERE DATE(created_at) = :report_date
                GROUP BY status, payment_status
            """
            results = self.db.execute(sql, {"report_date": date_str})

            # 生成简单文本报表
            report_path = self.output_dir / f"daily_order_report_{date_str}.txt"
            with open(report_path, "w", encoding="utf-8") as f:
                f.write(f"每日订单报表 - {date_str}\n")
                f.write("=" * 60 + "\n\n")

                if not results:
                    f.write("当日无订单数据\n")
                else:
                    f.write(f"{'状态':<12} {'支付状态':<12} {'订单数':<8} {'总金额':<12} {'总数量':<8}\n")
                    f.write("-" * 60 + "\n")
                    for row in results:
                        f.write(
                            f"{row['status']:<12} {row['payment_status']:<12} "
                            f"{row['order_count']:<8} {row['total_amount']:<12.2f} "
                            f"{row['total_quantity']:<8}\n"
                        )

            logger.info(f"Daily order report generated: {report_path}")
            return str(report_path)

        except Exception as e:
            logger.error(f"Failed to generate daily order report: {e}")
            raise ReportException(f"Daily order report generation failed: {e}")

    def generate_inventory_report(self) -> str:
        """
        生成库存报表

        Returns:
            生成的报表文件路径
        """
        logger.info("Generating inventory report")

        try:
            sql = """
                SELECT
                    sku,
                    warehouse_id,
                    available_qty,
                    reserved_qty,
                    locked_qty,
                    reorder_point,
                    updated_at
                FROM inventory
                ORDER BY warehouse_id, sku
            """
            results = self.db.execute(sql)

            date_str = datetime.now().strftime("%Y-%m-%d")
            report_path = self.output_dir / f"inventory_report_{date_str}.txt"

            with open(report_path, "w", encoding="utf-8") as f:
                f.write(f"库存报表 - {date_str}\n")
                f.write("=" * 80 + "\n\n")

                if not results:
                    f.write("暂无库存数据\n")
                else:
                    f.write(
                        f"{'SKU':<20} {'仓库':<10} {'可用':<8} {'预占':<8} "
                        f"{'锁定':<8} {'预警点':<8} {'更新时间':<20}\n"
                    )
                    f.write("-" * 80 + "\n")

                    for row in results:
                        low_stock_mark = " [低库存]" if row["available_qty"] <= row["reorder_point"] else ""
                        f.write(
                            f"{row['sku']:<20} {row['warehouse_id']:<10} "
                            f"{row['available_qty']:<8} {row['reserved_qty']:<8} "
                            f"{row['locked_qty']:<8} {row['reorder_point']:<8} "
                            f"{str(row['updated_at']):<20}{low_stock_mark}\n"
                        )

            logger.info(f"Inventory report generated: {report_path}")
            return str(report_path)

        except Exception as e:
            logger.error(f"Failed to generate inventory report: {e}")
            raise ReportException(f"Inventory report generation failed: {e}")

    def generate_sales_summary(
        self,
        start_date: datetime = None,
        end_date: datetime = None
    ) -> str:
        """
        生成销售汇总报表

        Args:
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            生成的报表文件路径
        """
        if start_date is None:
            start_date = datetime.now() - timedelta(days=30)
        if end_date is None:
            end_date = datetime.now()

        logger.info(
            f"Generating sales summary from {start_date.date()} to {end_date.date()}"
        )

        try:
            sql = """
                SELECT
                    DATE(created_at) as sale_date,
                    COUNT(*) as order_count,
                    SUM(total_amount) as daily_amount,
                    AVG(total_amount) as avg_order_value
                FROM orders
                WHERE status != 'cancelled'
                  AND created_at BETWEEN :start_date AND :end_date
                GROUP BY DATE(created_at)
                ORDER BY sale_date
            """
            results = self.db.execute(sql, {
                "start_date": start_date.strftime("%Y-%m-%d %H:%M:%S"),
                "end_date": end_date.strftime("%Y-%m-%d %H:%M:%S")
            })

            report_path = self.output_dir / f"sales_summary_{start_date.date()}_to_{end_date.date()}.txt"

            with open(report_path, "w", encoding="utf-8") as f:
                f.write(f"销售汇总报表 ({start_date.date()} ~ {end_date.date()})\n")
                f.write("=" * 60 + "\n\n")

                if not results:
                    f.write("该时间段内无销售数据\n")
                else:
                    f.write(f"{'日期':<12} {'订单数':<8} {'销售额':<12} {'客单价':<12}\n")
                    f.write("-" * 60 + "\n")

                    total_orders = 0
                    total_amount = 0.0

                    for row in results:
                        f.write(
                            f"{str(row['sale_date']):<12} {row['order_count']:<8} "
                            f"{row['daily_amount']:<12.2f} {row['avg_order_value']:<12.2f}\n"
                        )
                        total_orders += row["order_count"]
                        total_amount += row["daily_amount"]

                    f.write("-" * 60 + "\n")
                    f.write(
                        f"{'合计':<12} {total_orders:<8} {total_amount:<12.2f} "
                        f"{total_amount/total_orders if total_orders else 0:<12.2f}\n"
                    )

            logger.info(f"Sales summary generated: {report_path}")
            return str(report_path)

        except Exception as e:
            logger.error(f"Failed to generate sales summary: {e}")
            raise ReportException(f"Sales summary generation failed: {e}")

    def run_all_reports(self):
        """执行所有报表生成任务"""
        logger.info("=" * 50)
        logger.info("Report generation task started")
        logger.info("=" * 50)

        reports = []
        try:
            reports.append(self.generate_daily_order_report())
            reports.append(self.generate_inventory_report())
            reports.append(self.generate_sales_summary())
            logger.info(f"All reports generated successfully: {reports}")
        except Exception as e:
            logger.error(f"Report generation task failed: {e}")
            raise

        return reports


def main():
    """任务入口"""
    load_dotenv()
    config = load_config()
    generator = ReportGenerator(config)
    generator.run_all_reports()


if __name__ == "__main__":
    main()
