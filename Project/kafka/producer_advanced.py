"""
生产级别的 Kafka Producer
特性:
- 异步发送 + 回调处理
- 消息序列化
- 分区策略
- 错误处理和重试
- 优雅关闭
- 性能监控
"""

import json
import time
import logging
import threading
from typing import Optional, Callable, Dict, Any
from dataclasses import dataclass
from datetime import datetime
from kafka import KafkaProducer
from kafka.errors import KafkaError, KafkaTimeoutError
from kafka.partitioner import DefaultPartitioner

from config import PRODUCER_CONFIG, TOPICS

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class ProducerMetrics:
    """生产者指标"""
    messages_sent: int = 0
    messages_failed: int = 0
    total_latency_ms: float = 0

    @property
    #这里计算的是平均时延
    def avg_latency_ms(self) -> float:
        return self.total_latency_ms / self.messages_sent if self.messages_sent > 0 else 0

class CustomPartitioner:
    """
    自定义分区器
    实现消息到分区的映射策略
    """

    def __init__(self, partitions: Optional[list] = None):
        self.partitions = partitions or []
        self.default_partitioner = DefaultPartitioner()

    def __call__(self, key: Optional[bytes], partitions: list, available: list) -> int:
        """
        分区选择逻辑

        Args:
            key: 消息的 key（bytes）
            partitions: 所有分区列表
            available: 可用分区列表

        Returns:
            分区号
        """
        if not partitions:
            return 0

        if key is None:
            # 没有 key，轮询分区
            return self.default_partitioner(key, partitions, available)

        # 有 key，根据 key 哈希分区（保证相同 key 的消息进入同一分区）
        key_str = key.decode('utf-8')

        # 业务逻辑：例如根据用户ID分区
        if key_str.startswith('user_'):
            # 提取用户ID数字部分
            try:
                user_id = int(key_str.split('_')[1])
                return user_id % len(partitions)
            except (IndexError, ValueError):
                pass

        # 默认：一致性哈希
        return hash(key) % len(partitions)


class JSONSerializer:
    """JSON 序列化器"""

    @staticmethod
    def serialize(data: Any) -> bytes:
        """序列化数据为 JSON bytes"""
        def default_handler(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

        return json.dumps(data, default=default_handler).encode('utf-8')


class AvroSerializer:
    """
    Avro 序列化器（需要 confluent-kafka 或 fastavro）
    更高效的序列化格式，适合大数据场景
    """

    def __init__(self, schema: dict):
        self.schema = schema
        # 实际使用需要安装: pip install fastavro
        # import fastavro.schema
        # self.parsed_schema = fastavro.schema.parse_schema(schema)

    def serialize(self, data: dict) -> bytes:
        """Avro 序列化"""
        # 这里提供框架，实际需要 fastavro 库
        raise NotImplementedError("Install fastavro and implement this method")


class ProducerCallback:
    """
    发送回调处理
    """

    def __init__(self, message: dict, metrics: ProducerMetrics, logger: logging.Logger):
        self.message = message
        self.metrics = metrics
        self.logger = logger
        self.start_time = time.time()

    def on_success(self, record_metadata):
        """发送成功回调"""
        latency = (time.time() - self.start_time) * 1000
        self.metrics.messages_sent += 1
        self.metrics.total_latency_ms += latency

        self.logger.debug(
            f"Message sent successfully - Topic: {record_metadata.topic}, "
            f"Partition: {record_metadata.partition}, "
            f"Offset: {record_metadata.offset}, "
            f"Latency: {latency:.2f}ms"
        )

    def on_error(self, exception):
        """发送失败回调"""
        self.metrics.messages_failed += 1
        self.logger.error(
            f"Failed to send message: {self.message}, Error: {exception}"
        )


class KafkaProducerAdvanced:
    """
    高级 Kafka 生产者

    特性:
    - 支持同步/异步发送
    - 自动序列化
    - 自定义分区
    - 消息回调
    - 性能指标
    - 优雅关闭
    """

    def __init__(
        self,
        config: dict = None,
        value_serializer: Callable = None,
        key_serializer: Callable = None,
    ):
        self.config = config or PRODUCER_CONFIG
        self.metrics = ProducerMetrics()

        # 序列化器
        self.value_serializer = value_serializer or JSONSerializer.serialize
        self.key_serializer = key_serializer or (lambda k: k.encode('utf-8') if k else None)

        # 创建生产者实例
        self._create_producer()

        # 关闭标志
        self._closed = False

        logger.info("Kafka Producer initialized successfully")

    def _create_producer(self):
        """创建 Kafka Producer 实例"""
        try:
            self.producer = KafkaProducer(
                bootstrap_servers=self.config['bootstrap_servers'],
                acks=self.config.get('acks', 'all'),
                retries=self.config.get('retries', 3),
                batch_size=self.config.get('batch_size', 16384),
                linger_ms=self.config.get('linger_ms', 5),
                buffer_memory=self.config.get('buffer_memory', 33554432),
                compression_type=self.config.get('compression_type', None),
                enable_idempotence=self.config.get('enable_idempotence', True),
                max_request_size=self.config.get('max_request_size', 1048576),
                request_timeout_ms=self.config.get('request_timeout_ms', 30000),
                security_protocol=self.config.get('security_protocol', 'PLAINTEXT'),
            )
        except KafkaError as e:
            logger.error(f"Failed to create Kafka Producer: {e}")
            raise

    def send(
        self,
        topic: str,
        value: Any,
        key: Optional[str] = None,
        partition: Optional[int] = None,
        headers: Optional[list] = None,
        callback: bool = True,
        sync: bool = False,
    ) -> Optional[Any]:
        """
        发送消息

        Args:
            topic: 主题名称
            value: 消息内容
            key: 消息键（用于分区）
            partition: 指定分区（None 则自动选择）
            headers: 消息头 [(key, value), ...]
            callback: 是否使用回调
            sync: 是否同步发送

        Returns:
            sync=True: 返回 RecordMetadata
            sync=False: 返回 Future
        """
        if self._closed:
            raise RuntimeError("Producer is closed")

        # 序列化
        serialized_value = self.value_serializer(value)
        serialized_key = self.key_serializer(key) if key else None

        # 准备发送参数
        send_kwargs = {
            'topic': topic,
            'value': serialized_value,
        }
        if serialized_key:
            send_kwargs['key'] = serialized_key
        if partition is not None:
            send_kwargs['partition'] = partition
        if headers:
            send_kwargs['headers'] = headers

        try:
            future = self.producer.send(**send_kwargs)

            # 添加回调
            if callback:
                cb = ProducerCallback(value, self.metrics, logger)
                future.add_callback(cb.on_success)
                future.add_errback(cb.on_error)

            # 同步发送
            if sync:
                return future.get(timeout=10)

            return future

        except KafkaTimeoutError:
            logger.error(f"Timeout sending message to topic {topic}")
            self.metrics.messages_failed += 1
            raise
        except KafkaError as e:
            logger.error(f"Error sending message: {e}")
            self.metrics.messages_failed += 1
            raise

    def send_batch(
        self,
        topic: str,
        messages: list,
        key_extractor: Optional[Callable] = None,
    ) -> int:
        """
        批量发送消息

        Args:
            topic: 主题
            messages: 消息列表
            key_extractor: 从消息中提取 key 的函数

        Returns:
            成功发送的消息数量
        """
        success_count = 0

        for msg in messages:
            key = key_extractor(msg) if key_extractor else None
            try:
                self.send(topic, msg, key=key, callback=False)
                success_count += 1
            except KafkaError as e:
                logger.error(f"Failed to send message in batch: {e}")

        # 确保所有消息都已发送
        self.flush()
        return success_count

    def flush(self, timeout: Optional[float] = None):
        """
        刷新缓冲区，等待所有消息发送完成

        Args:
            timeout: 超时时间（秒）
        """
        self.producer.flush(timeout=timeout)

    def get_metrics(self) -> dict:
        """获取性能指标"""
        return {
            'messages_sent': self.metrics.messages_sent,
            'messages_failed': self.metrics.messages_failed,
            'success_rate': (
                self.metrics.messages_sent /
                (self.metrics.messages_sent + self.metrics.messages_failed) * 100
                if (self.metrics.messages_sent + self.metrics.messages_failed) > 0 else 0
            ),
            'avg_latency_ms': self.metrics.avg_latency_ms,
        }

    def close(self, timeout: float = 10):
        """
        优雅关闭生产者

        Args:
            timeout: 等待消息发送完成的超时时间
        """
        if self._closed:
            return

        logger.info("Closing Kafka Producer...")

        try:
            # 刷新所有待发送的消息
            self.flush(timeout=timeout)

            # 打印最终指标
            metrics = self.get_metrics()
            logger.info(f"Final metrics: {metrics}")

            # 关闭生产者
            self.producer.close(timeout=timeout)
            self._closed = True

            logger.info("Kafka Producer closed successfully")

        except Exception as e:
            logger.error(f"Error closing producer: {e}")
            raise

    def __enter__(self):
        """上下文管理器入口"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器退出"""
        self.close()


# ============================================================
# 使用示例
# ============================================================

def example_basic_send():
    """基本发送示例"""
    print("\n=== 基本发送示例 ===")

    with KafkaProducerAdvanced() as producer:
        for i in range(5):
            message = {
                'order_id': f'ORD_{i:04d}',
                'user': f'user_{i}',
                'amount': 100.0 + i * 10,
                'timestamp': datetime.now().isoformat(),
            }

            # 异步发送
            producer.send(
                topic=TOPICS['ORDERS'],
                value=message,
                key=f'user_{i}',  # 使用 key 保证同一用户的订单进入同一分区
            )

            print(f"Sent: {message}")

        # 查看指标
        print(f"\nMetrics: {producer.get_metrics()}")


def example_sync_send():
    """同步发送示例"""
    print("\n=== 同步发送示例 ===")

    with KafkaProducerAdvanced() as producer:
        message = {'event': 'sync_test', 'timestamp': datetime.now().isoformat()}

        # 同步发送，等待确认
        metadata = producer.send(
            topic=TOPICS['ORDERS'],
            value=message,
            sync=True,
        )

        print(f"Message sent to partition {metadata.partition} at offset {metadata.offset}")


def example_batch_send():
    """批量发送示例"""
    print("\n=== 批量发送示例 ===")

    with KafkaProducerAdvanced() as producer:
        # 准备批量消息
        messages = [
            {'order_id': f'ORD_{i:04d}', 'status': 'pending'}
            for i in range(100)
        ]

        # 批量发送
        count = producer.send_batch(
            topic=TOPICS['ORDERS'],
            messages=messages,
            key_extractor=lambda msg: msg['order_id'],
        )

        print(f"Sent {count} messages")
        print(f"Metrics: {producer.get_metrics()}")


def example_with_headers():
    """带消息头的发送示例"""
    print("\n=== 带消息头的发送示例 ===")

    with KafkaProducerAdvanced() as producer:
        message = {'event': 'test_with_headers'}

        # 添加消息头
        headers = [
            ('source', b'web_app'),
            ('version', b'1.0'),
            ('trace_id', b'abc123'),
        ]

        producer.send(
            topic=TOPICS['ORDERS'],
            value=message,
            headers=headers,
        )

        print("Sent message with headers")


def example_custom_partition():
    """自定义分区示例"""
    print("\n=== 自定义分区示例 ===")

    with KafkaProducerAdvanced() as producer:
        # 发送到指定分区
        for partition in range(3):
            message = {
                'partition_test': True,
                'target_partition': partition,
            }

            producer.send(
                topic=TOPICS['ORDERS'],
                value=message,
                partition=partition,  # 指定分区
            )

            print(f"Sent to partition {partition}")


if __name__ == '__main__':
    # 运行示例
    try:
        example_basic_send()
        # example_sync_send()
        # example_batch_send()
        # example_with_headers()
        # example_custom_partition()
    except Exception as e:
        logger.error(f"Error in example: {e}")
