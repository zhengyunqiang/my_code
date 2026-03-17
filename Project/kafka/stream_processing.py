"""
Kafka 流处理应用示例
展示实际生产中的典型使用场景:
1. 订单处理系统
2. 实时数据分析
3. 事件溯源
4. 日志收集
"""

import json
import time
import logging
import threading
from datetime import datetime
from typing import Dict, Any, List
from dataclasses import dataclass, asdict
from enum import Enum

from producer_advanced import KafkaProducerAdvanced
from consumer_advanced import KafkaConsumerAdvanced, MessageHandler
from config import TOPICS, PRODUCER_CONFIG, CONSUMER_CONFIG

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================
# 订单处理系统
# ============================================================

class OrderStatus(Enum):
    """订单状态"""
    PENDING = "pending"
    CONFIRMED = "confirmed"
    PAID = "paid"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


@dataclass
class Order:
    """订单数据结构"""
    order_id: str
    user_id: str
    items: List[dict]
    total_amount: float
    status: OrderStatus
    created_at: str
    updated_at: str

    def to_dict(self) -> dict:
        data = asdict(self)
        data['status'] = self.status.value
        return data

    @classmethod
    def from_dict(cls, data: dict) -> 'Order':
        data['status'] = OrderStatus(data['status'])
        return cls(**data)


class OrderService:
    """
    订单服务
    演示完整的订单处理流程
    """

    def __init__(self):
        self.producer = KafkaProducerAdvanced(config=PRODUCER_CONFIG)

    def create_order(self, user_id: str, items: List[dict]) -> Order:
        """
        创建订单

        Args:
            user_id: 用户ID
            items: 商品列表

        Returns:
            订单对象
        """
        # 计算总金额
        total_amount = sum(item.get('price', 0) * item.get('quantity', 1) for item in items)

        # 创建订单
        order = Order(
            order_id=f"ORD_{int(time.time() * 1000)}",
            user_id=user_id,
            items=items,
            total_amount=total_amount,
            status=OrderStatus.PENDING,
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
        )

        # 发送订单创建事件
        self.producer.send(
            topic=TOPICS['ORDERS'],
            value={
                'event_type': 'ORDER_CREATED',
                'order': order.to_dict(),
                'timestamp': datetime.now().isoformat(),
            },
            key=order.order_id,
        )

        logger.info(f"Order created: {order.order_id}")
        return order

    def update_order_status(self, order: Order, new_status: OrderStatus):
        """
        更新订单状态

        Args:
            order: 订单对象
            new_status: 新状态
        """
        old_status = order.status
        order.status = new_status
        order.updated_at = datetime.now().isoformat()

        # 发送状态变更事件
        self.producer.send(
            topic=TOPICS['ORDERS'],
            value={
                'event_type': 'ORDER_STATUS_CHANGED',
                'order_id': order.order_id,
                'old_status': old_status.value,
                'new_status': new_status.value,
                'timestamp': datetime.now().isoformat(),
            },
            key=order.order_id,
        )

        logger.info(f"Order {order.order_id} status changed: {old_status.value} -> {new_status.value}")

    def close(self):
        self.producer.close()


class OrderEventHandler(MessageHandler):
    """订单事件处理器"""

    def __init__(self):
        # 模拟数据库
        self.orders_db: Dict[str, Order] = {}

    def handle(self, message: dict, metadata: dict) -> bool:
        """处理订单事件"""
        event_type = message.get('event_type')

        if event_type == 'ORDER_CREATED':
            return self._handle_order_created(message)
        elif event_type == 'ORDER_STATUS_CHANGED':
            return self._handle_status_changed(message)
        else:
            logger.warning(f"Unknown event type: {event_type}")
            return True

    def _handle_order_created(self, message: dict) -> bool:
        """处理订单创建事件"""
        order_data = message.get('order')
        order = Order.from_dict(order_data)

        # 保存到数据库
        self.orders_db[order.order_id] = order

        logger.info(f"Order saved to DB: {order.order_id}")

        # 触发后续流程（如发送通知）
        # ...

        return True

    def _handle_status_changed(self, message: dict) -> bool:
        """处理状态变更事件"""
        order_id = message.get('order_id')
        new_status = message.get('new_status')

        # 更新数据库
        if order_id in self.orders_db:
            self.orders_db[order_id].status = OrderStatus(new_status)
            logger.info(f"Order {order_id} status updated to {new_status}")

        return True


# ============================================================
# 实时数据分析
# ============================================================

class RealTimeAnalytics:
    """
    实时数据分析
    统计订单金额、数量等指标
    """

    def __init__(self):
        self.metrics = {
            'total_orders': 0,
            'total_amount': 0.0,
            'orders_by_status': {},
            'orders_by_user': {},
            'hourly_stats': {},
        }
        self._lock = threading.Lock()

    def process_event(self, message: dict, metadata: dict) -> bool:
        """处理订单事件并更新统计"""
        event_type = message.get('event_type')

        with self._lock:
            if event_type == 'ORDER_CREATED':
                order = message.get('order', {})
                self.metrics['total_orders'] += 1
                self.metrics['total_amount'] += order.get('total_amount', 0)

                # 按状态统计
                status = order.get('status', 'unknown')
                self.metrics['orders_by_status'][status] = \
                    self.metrics['orders_by_status'].get(status, 0) + 1

                # 按用户统计
                user_id = order.get('user_id', 'unknown')
                self.metrics['orders_by_user'][user_id] = \
                    self.metrics['orders_by_user'].get(user_id, 0) + 1

                # 按小时统计
                hour = datetime.now().strftime('%Y-%m-%d %H:00')
                if hour not in self.metrics['hourly_stats']:
                    self.metrics['hourly_stats'][hour] = {'count': 0, 'amount': 0}
                self.metrics['hourly_stats'][hour]['count'] += 1
                self.metrics['hourly_stats'][hour]['amount'] += order.get('total_amount', 0)

        return True

    def get_metrics(self) -> dict:
        """获取统计指标"""
        with self._lock:
            return self.metrics.copy()

    def print_metrics(self):
        """打印统计指标"""
        metrics = self.get_metrics()
        print("\n" + "=" * 50)
        print("实时订单统计")
        print("=" * 50)
        print(f"总订单数: {metrics['total_orders']}")
        print(f"总金额: ¥{metrics['total_amount']:.2f}")
        print(f"平均订单金额: ¥{metrics['total_amount'] / metrics['total_orders']:.2f}"
              if metrics['total_orders'] > 0 else "N/A")
        print(f"\n按状态统计:")
        for status, count in metrics['orders_by_status'].items():
            print(f"  {status}: {count}")
        print("=" * 50)


# ============================================================
# 事件溯源 (Event Sourcing)
# ============================================================

class EventStore:
    """
    事件存储
    实现事件溯源模式
    """

    def __init__(self):
        # 事件流 (topic -> events)
        self.event_streams: Dict[str, List[dict]] = {}

    def append_event(self, stream_id: str, event: dict):
        """
        追加事件到流

        Args:
            stream_id: 流ID (通常是聚合根ID)
            event: 事件数据
        """
        if stream_id not in self.event_streams:
            self.event_streams[stream_id] = []

        event['_version'] = len(self.event_streams[stream_id]) + 1
        event['_timestamp'] = datetime.now().isoformat()

        self.event_streams[stream_id].append(event)

    def get_events(self, stream_id: str, from_version: int = 0) -> List[dict]:
        """
        获取事件流

        Args:
            stream_id: 流ID
            from_version: 起始版本号

        Returns:
            事件列表
        """
        events = self.event_streams.get(stream_id, [])
        return [e for e in events if e.get('_version', 0) > from_version]


class OrderAggregate:
    """
    订单聚合根
    通过重放事件恢复状态
    """

    def __init__(self, order_id: str):
        self.order_id = order_id
        self.user_id = None
        self.items = []
        self.total_amount = 0.0
        self.status = None
        self.version = 0

    def apply_event(self, event: dict):
        """应用事件，更新状态"""
        event_type = event.get('event_type')

        if event_type == 'ORDER_CREATED':
            order_data = event.get('order', {})
            self.user_id = order_data.get('user_id')
            self.items = order_data.get('items', [])
            self.total_amount = order_data.get('total_amount', 0)
            self.status = order_data.get('status')

        elif event_type == 'ORDER_STATUS_CHANGED':
            self.status = event.get('new_status')

        self.version = event.get('_version', self.version + 1)

    def rebuild_from_events(self, events: List[dict]):
        """从事件重建状态"""
        for event in events:
            self.apply_event(event)


# ============================================================
# 日志收集系统
# ============================================================

@dataclass
class LogEntry:
    """日志条目"""
    timestamp: str
    level: str
    service: str
    message: str
    metadata: dict

    def to_dict(self) -> dict:
        return asdict(self)


class LogCollector:
    """
    日志收集器
    收集各服务的日志并发送到 Kafka
    """

    def __init__(self, service_name: str):
        self.service_name = service_name
        self.producer = KafkaProducerAdvanced(config=PRODUCER_CONFIG)

    def log(self, level: str, message: str, metadata: dict = None):
        """
        发送日志

        Args:
            level: 日志级别
            message: 日志消息
            metadata: 元数据
        """
        entry = LogEntry(
            timestamp=datetime.now().isoformat(),
            level=level,
            service=self.service_name,
            message=message,
            metadata=metadata or {},
        )

        self.producer.send(
            topic='logs',
            value=entry.to_dict(),
            key=self.service_name,
        )

    def info(self, message: str, metadata: dict = None):
        self.log('INFO', message, metadata)

    def warning(self, message: str, metadata: dict = None):
        self.log('WARNING', message, metadata)

    def error(self, message: str, metadata: dict = None):
        self.log('ERROR', message, metadata)

    def close(self):
        self.producer.close()


class LogAggregator:
    """
    日志聚合器
    收集并分析日志
    """

    def __init__(self):
        self.error_count = 0
        self.warning_count = 0
        self.logs_by_service: Dict[str, List[LogEntry]] = {}

    def process_log(self, message: dict, metadata: dict) -> bool:
        """处理日志"""
        level = message.get('level')
        service = message.get('service')

        # 统计
        if level == 'ERROR':
            self.error_count += 1
        elif level == 'WARNING':
            self.warning_count += 1

        # 按服务存储
        if service not in self.logs_by_service:
            self.logs_by_service[service] = []
        self.logs_by_service[service].append(LogEntry(**message))

        return True

    def get_summary(self) -> dict:
        """获取日志摘要"""
        return {
            'total_errors': self.error_count,
            'total_warnings': self.warning_count,
            'services': list(self.logs_by_service.keys()),
            'log_count_by_service': {
                k: len(v) for k, v in self.logs_by_service.items()
            },
        }


# ============================================================
# 完整应用示例
# ============================================================

def run_order_processing_system():
    """运行订单处理系统"""
    print("\n" + "=" * 60)
    print("订单处理系统启动")
    print("=" * 60)

    # 创建 Topic (如果不存在)
    # 实际生产中可以使用 admin_tools 创建

    # 启动消费者 (在后台线程)
    analytics = RealTimeAnalytics()
    event_handler = OrderEventHandler()

    consumer = KafkaConsumerAdvanced(
        topics=[TOPICS['ORDERS']],
        group_id='order-processing-group',
        handler=lambda msg, meta: (
            event_handler.handle(msg, meta) and
            analytics.process_event(msg, meta)
        ),
    )

    consumer_thread = threading.Thread(
        target=consumer.consume,
        kwargs={'commit_mode': 'sync'},
        daemon=True,
    )
    consumer_thread.start()

    # 创建订单
    order_service = OrderService()

    try:
        # 模拟订单流程
        for i in range(5):
            # 创建订单
            order = order_service.create_order(
                user_id=f"user_{i % 3}",
                items=[
                    {'product_id': 'P001', 'name': 'Product A', 'price': 99.9, 'quantity': 2},
                    {'product_id': 'P002', 'name': 'Product B', 'price': 49.9, 'quantity': 1},
                ]
            )

            time.sleep(1)

            # 更新状态
            order_service.update_order_status(order, OrderStatus.CONFIRMED)
            time.sleep(0.5)

            order_service.update_order_status(order, OrderStatus.PAID)
            time.sleep(0.5)

            # 打印实时统计
            analytics.print_metrics()

    except KeyboardInterrupt:
        print("\n停止中...")
    finally:
        order_service.close()
        consumer.close()


def run_log_collection_system():
    """运行日志收集系统"""
    print("\n" + "=" * 60)
    print("日志收集系统启动")
    print("=" * 60)

    # 创建日志收集器
    collector1 = LogCollector('order-service')
    collector2 = LogCollector('payment-service')

    # 发送日志
    collector1.info('Order service started')
    collector1.info('Processing order ORD_001')
    collector1.warning('Order validation took too long', {'order_id': 'ORD_001'})
    collector1.error('Failed to connect to inventory service')

    collector2.info('Payment service started')
    collector2.info('Processing payment for ORD_001')
    collector2.warning('Payment timeout, retrying')

    # 刷新并关闭
    collector1.close()
    collector2.close()

    print("Logs sent successfully")


if __name__ == '__main__':
    # 运行订单处理系统
    run_order_processing_system()

    # 或运行日志收集系统
    # run_log_collection_system()
