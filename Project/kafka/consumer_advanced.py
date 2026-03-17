"""
生产级别的 Kafka Consumer
特性:
- 消费者组管理
- 手动/自动提交偏移量
- 多线程消费
- 错误处理和重试
- 消息反序列化
- 优雅关闭
- 死信队列处理
- 消费者再平衡监听
"""

import json
import time
import logging
import threading
import signal
from typing import Callable, Optional, Dict, Any, List
from dataclasses import dataclass, field
from datetime import datetime
from queue import Queue
from abc import ABC, abstractmethod

from kafka import KafkaConsumer
from kafka.errors import KafkaError, CommitFailedError, NoBrokersAvailable
from kafka.structs import TopicPartition, OffsetAndMetadata

from config import CONSUMER_CONFIG, TOPICS

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class ConsumerMetrics:
    """消费者指标"""
    messages_consumed: int = 0
    messages_processed: int = 0
    messages_failed: int = 0
    processing_errors: int = 0
    total_processing_time_ms: float = 0
    last_message_timestamp: Optional[datetime] = None

    @property
    def avg_processing_time_ms(self) -> float:
        return self.total_processing_time_ms / self.messages_processed if self.messages_processed > 0 else 0


class MessageHandler(ABC):
    """消息处理器抽象基类"""

    @abstractmethod
    def handle(self, message: dict, metadata: dict) -> bool:
        """
        处理消息

        Args:
            message: 消息内容
            metadata: 消息元数据 (topic, partition, offset, key, etc.)

        Returns:
            True: 处理成功
            False: 处理失败，需要重试或进入死信队列
        """
        pass


class JSONDeserializer:
    """JSON 反序列化器"""

    @staticmethod
    def deserialize(data: bytes) -> Any:
        """反序列化 JSON bytes"""
        if data is None:
            return None
        return json.loads(data.decode('utf-8'))


class DeadLetterQueue:
    """
    死信队列处理器
    处理无法正常消费的消息
    """

    def __init__(self, producer=None, dlq_topic: str = None):
        self.producer = producer
        self.dlq_topic = dlq_topic or TOPICS.get('DLQ', 'dead-letter-queue')
        self.failed_messages: List[dict] = []

    def send_to_dlq(
        self,
        original_message: Any,
        original_topic: str,
        partition: int,
        offset: int,
        error: Exception,
        headers: list = None,
    ):
        """
        将失败消息发送到死信队列

        Args:
            original_message: 原始消息
            original_topic: 原始主题
            partition: 分区
            offset: 偏移量
            error: 错误信息
            headers: 消息头
        """
        dlq_message = {
            'original_topic': original_topic,
            'original_partition': partition,
            'original_offset': offset,
            'original_message': original_message,
            'error': str(error),
            'failed_at': datetime.now().isoformat(),
            'headers': headers,
        }

        logger.warning(
            f"Sending message to DLQ - Topic: {original_topic}, "
            f"Partition: {partition}, Offset: {offset}, Error: {error}"
        )

        # 如果有生产者，发送到 DLQ
        if self.producer:
            try:
                self.producer.send(self.dlq_topic, dlq_message)
            except Exception as e:
                logger.error(f"Failed to send to DLQ: {e}")
                # 本地存储
                self.failed_messages.append(dlq_message)
        else:
            # 本地存储
            self.failed_messages.append(dlq_message)

    def get_failed_messages(self) -> List[dict]:
        """获取失败消息列表"""
        return self.failed_messages


class RebalanceListener:
    """
    消费者再平衡监听器
    在分区分配/撤销时执行自定义逻辑
    """

    def __init__(self, consumer):
        self.consumer = consumer
        self.assigned_partitions: List[TopicPartition] = []

    def on_partitions_assigned(self, assigned: List[TopicPartition]):
        """
        分区分配回调
        当消费者被分配新的分区时调用
        """
        self.assigned_partitions = assigned
        logger.info(f"Partitions assigned: {assigned}")

        # 可以在这里执行初始化逻辑，比如：
        # - 加载分区相关的缓存
        # - 从数据库恢复处理状态
        # - 初始化分区级别的资源

    def on_partitions_revoked(self, revoked: List[TopicPartition]):
        """
        分区撤销回调
        当消费者的分区被撤销时调用
        """
        logger.info(f"Partitions revoked: {revoked}")

        # 可以在这里执行清理逻辑，比如：
        # - 提交最后的偏移量
        # - 清理分区相关的缓存
        # - 保存处理状态

        # 提交当前偏移量
        try:
            self.consumer.commit_sync()
        except Exception as e:
            logger.error(f"Failed to commit during rebalance: {e}")

        self.assigned_partitions = []


class KafkaConsumerAdvanced:
    """
    高级 Kafka 消费者

    特性:
    - 支持单线程/多线程消费
    - 手动/自动提交
    - 消息处理重试
    - 死信队列
    - 优雅关闭
    - 再平衡监听
    """

    def __init__(
        self,
        topics: List[str],
        config: dict = None,
        group_id: str = None,
        value_deserializer: Callable = None,
        key_deserializer: Callable = None,
        handler: MessageHandler = None,
        enable_dlq: bool = True,
        dlq_producer=None,
    ):
        self.topics = topics if isinstance(topics, list) else [topics]
        self.config = config or CONSUMER_CONFIG.copy()

        # 覆盖 group_id
        if group_id:
            self.config['group_id'] = group_id

        # 反序列化器
        self.value_deserializer = value_deserializer or JSONDeserializer.deserialize
        self.key_deserializer = key_deserializer or (lambda k: k.decode('utf-8') if k else None)

        # 消息处理器
        self.handler = handler

        # 死信队列
        self.enable_dlq = enable_dlq
        self.dlq = DeadLetterQueue(dlq_producer) if enable_dlq else None

        # 指标
        self.metrics = ConsumerMetrics()

        # 控制标志
        self._running = False
        self._closed = False

        # 创建消费者
        self._create_consumer()

        # 再平衡监听器
        self.rebalance_listener = RebalanceListener(self)

        logger.info(f"Kafka Consumer initialized - Topics: {topics}, Group: {self.config['group_id']}")

    def _create_consumer(self):
        """创建 Kafka Consumer 实例"""
        try:
            self.consumer = KafkaConsumer(
                *self.topics,
                bootstrap_servers=self.config['bootstrap_servers'],
                group_id=self.config['group_id'],
                enable_auto_commit=self.config.get('enable_auto_commit', False),
                auto_commit_interval_ms=self.config.get('auto_commit_interval_ms', 5000),
                auto_offset_reset=self.config.get('auto_offset_reset', 'earliest'),
                session_timeout_ms=self.config.get('session_timeout_ms', 10000),
                heartbeat_interval_ms=self.config.get('heartbeat_interval_ms', 3000),
                max_poll_records=self.config.get('max_poll_records', 500),
                max_poll_interval_ms=self.config.get('max_poll_interval_ms', 300000),
                value_deserializer=self.value_deserializer,
                key_deserializer=self.key_deserializer,
                security_protocol=self.config.get('security_protocol', 'PLAINTEXT'),
                consumer_timeout_ms=1000,  # poll 超时时间
            )
        except NoBrokersAvailable:
            logger.error("No Kafka brokers available")
            raise
        except KafkaError as e:
            logger.error(f"Failed to create Kafka Consumer: {e}")
            raise

    def subscribe(self, topics: List[str] = None):
        """
        订阅主题

        Args:
            topics: 主题列表，None 则使用初始化时的主题
        """
        if topics:
            self.topics = topics if isinstance(topics, list) else [topics]

        self.consumer.subscribe(
            topics=self.topics,
            listener=self.rebalance_listener,
        )
        logger.info(f"Subscribed to topics: {self.topics}")

    def consume(
        self,
        handler: Callable = None,
        batch_size: int = 1,
        max_retries: int = 3,
        commit_mode: str = 'sync',  # 'sync', 'async', 'manual'
    ):
        """
        消费消息

        Args:
            handler: 消息处理函数 (message, metadata) -> bool
            batch_size: 批量处理大小
            max_retries: 最大重试次数
            commit_mode: 提交模式
        """
        if handler is None and self.handler is None:
            raise ValueError("No message handler provided")

        self._running = True

        logger.info(f"Starting consumer loop - Topics: {self.topics}")

        while self._running:
            try:
                # 拉取消息
                records = self.consumer.poll(timeout_ms=1000)

                if not records:
                    continue

                # 处理消息
                for topic_partition, messages in records.items():
                    batch = []

                    for msg in messages:
                        self.metrics.messages_consumed += 1

                        # 构建元数据
                        metadata = {
                            'topic': msg.topic,
                            'partition': msg.partition,
                            'offset': msg.offset,
                            'key': msg.key,
                            'timestamp': msg.timestamp,
                            'headers': msg.headers,
                        }

                        # 批量处理
                        if batch_size > 1:
                            batch.append((msg.value, metadata))
                            if len(batch) >= batch_size:
                                self._process_batch(
                                    batch, handler, max_retries, topic_partition
                                )
                                batch = []
                        else:
                            # 单条处理
                            self._process_single(
                                msg.value, metadata, handler, max_retries
                            )

                    # 处理剩余的批量消息
                    if batch:
                        self._process_batch(batch, handler, max_retries, topic_partition)

                    # 提交偏移量
                    if commit_mode != 'manual':
                        self._commit(commit_mode)

            except Exception as e:
                logger.error(f"Error in consumer loop: {e}")
                self.metrics.processing_errors += 1
                time.sleep(1)  # 错误后等待

        logger.info("Consumer loop stopped")

    def _process_single(
        self,
        message: Any,
        metadata: dict,
        handler: Callable,
        max_retries: int,
    ):
        """处理单条消息"""
        start_time = time.time()
        retry_count = 0
        success = False

        while retry_count <= max_retries and not success:
            try:
                # 调用处理器
                if self.handler:
                    success = self.handler.handle(message, metadata)
                else:
                    success = handler(message, metadata)

                if success:
                    self.metrics.messages_processed += 1
                    self.metrics.total_processing_time_ms += (time.time() - start_time) * 1000
                    self.metrics.last_message_timestamp = datetime.now()
                else:
                    raise ValueError("Handler returned False")

            except Exception as e:
                retry_count += 1
                self.metrics.processing_errors += 1

                if retry_count <= max_retries:
                    logger.warning(
                        f"Message processing failed (attempt {retry_count}/{max_retries}): {e}"
                    )
                    time.sleep(retry_count)  # 指数退避
                else:
                    logger.error(f"Message processing failed after {max_retries} retries: {e}")
                    self.metrics.messages_failed += 1

                    # 发送到死信队列
                    if self.enable_dlq and self.dlq:
                        self.dlq.send_to_dlq(
                            original_message=message,
                            original_topic=metadata['topic'],
                            partition=metadata['partition'],
                            offset=metadata['offset'],
                            error=e,
                            headers=metadata.get('headers'),
                        )

    def _process_batch(
        self,
        batch: List[tuple],
        handler: Callable,
        max_retries: int,
        topic_partition: TopicPartition,
    ):
        """批量处理消息"""
        for message, metadata in batch:
            self._process_single(message, metadata, handler, max_retries)

    def _commit(self, mode: str = 'sync'):
        """提交偏移量"""
        try:
            if mode == 'sync':
                self.consumer.commit()
            elif mode == 'async':
                self.consumer.commit_async()
        except CommitFailedError as e:
            logger.error(f"Commit failed: {e}")

    def commit_sync(self, offsets: Dict[TopicPartition, OffsetAndMetadata] = None):
        """
        手动同步提交

        Args:
            offsets: 指定提交的偏移量，None 则提交当前位置
        """
        try:
            if offsets:
                self.consumer.commit(offsets)
            else:
                self.consumer.commit()
        except CommitFailedError as e:
            logger.error(f"Sync commit failed: {e}")

    def commit_async(self, offsets: Dict[TopicPartition, OffsetAndMetadata] = None):
        """
        手动异步提交

        Args:
            offsets: 指定提交的偏移量
        """
        try:
            if offsets:
                self.consumer.commit_async(offsets)
            else:
                self.consumer.commit_async()
        except CommitFailedError as e:
            logger.error(f"Async commit failed: {e}")

    def seek_to_beginning(self, partitions: List[TopicPartition] = None):
        """从最早的消息开始消费"""
        if partitions:
            for tp in partitions:
                self.consumer.seek_to_beginning(tp)
        else:
            self.consumer.seek_to_beginning()
        logger.info("Seeked to beginning")

    def seek_to_end(self, partitions: List[TopicPartition] = None):
        """从最新的消息开始消费"""
        if partitions:
            for tp in partitions:
                self.consumer.seek_to_end(tp)
        else:
            self.consumer.seek_to_end()
        logger.info("Seeked to end")

    def seek(self, partition: TopicPartition, offset: int):
        """
        定位到指定偏移量

        Args:
            partition: 主题分区
            offset: 偏移量
        """
        self.consumer.seek(partition, offset)
        logger.info(f"Seeked to offset {offset} for partition {partition}")

    def pause(self, partitions: List[TopicPartition] = None):
        """暂停消费指定分区"""
        if partitions:
            self.consumer.pause(*partitions)
        else:
            self.consumer.pause()
        logger.info(f"Paused partitions: {partitions}")

    def resume(self, partitions: List[TopicPartition] = None):
        """恢复消费指定分区"""
        if partitions:
            self.consumer.resume(*partitions)
        else:
            self.consumer.resume()
        logger.info(f"Resumed partitions: {partitions}")

    def get_metrics(self) -> dict:
        """获取消费指标"""
        return {
            'messages_consumed': self.metrics.messages_consumed,
            'messages_processed': self.metrics.messages_processed,
            'messages_failed': self.metrics.messages_failed,
            'processing_errors': self.metrics.processing_errors,
            'success_rate': (
                self.metrics.messages_processed / self.metrics.messages_consumed * 100
                if self.metrics.messages_consumed > 0 else 0
            ),
            'avg_processing_time_ms': self.metrics.avg_processing_time_ms,
            'last_message_timestamp': self.metrics.last_message_timestamp.isoformat() if self.metrics.last_message_timestamp else None,
        }

    def stop(self):
        """停止消费"""
        logger.info("Stopping consumer...")
        self._running = False

    def close(self):
        """关闭消费者"""
        if self._closed:
            return

        logger.info("Closing Kafka Consumer...")

        try:
            # 停止消费循环
            self.stop()

            # 提交最后的偏移量
            self.commit_sync()

            # 打印最终指标
            logger.info(f"Final metrics: {self.get_metrics()}")

            # 关闭消费者
            self.consumer.close()
            self._closed = True

            logger.info("Kafka Consumer closed successfully")

        except Exception as e:
            logger.error(f"Error closing consumer: {e}")

    def __enter__(self):
        """上下文管理器入口"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器退出"""
        self.close()


# ============================================================
# 多线程消费者
# ============================================================

class MultiThreadConsumer:
    """
    多线程消费者
    使用多个工作线程并行处理消息
    """

    def __init__(
        self,
        topics: List[str],
        num_workers: int = 4,
        config: dict = None,
        handler: Callable = None,
    ):
        self.topics = topics
        self.num_workers = num_workers
        self.config = config or CONSUMER_CONFIG.copy()
        self.handler = handler

        self.message_queue = Queue(maxsize=10000)
        self.workers: List[threading.Thread] = []
        self._running = False

    def start(self):
        """启动消费者和工作线程"""
        self._running = True

        # 启动工作线程
        for i in range(self.num_workers):
            worker = threading.Thread(
                target=self._worker_loop,
                args=(i,),
                daemon=True,
            )
            worker.start()
            self.workers.append(worker)

        # 主消费循环
        self._consume_loop()

    def _consume_loop(self):
        """消费循环"""
        with KafkaConsumerAdvanced(
            topics=self.topics,
            config=self.config,
        ) as consumer:
            while self._running:
                records = consumer.consumer.poll(timeout_ms=1000)

                for topic_partition, messages in records.items():
                    for msg in messages:
                        self.message_queue.put((msg.value, {
                            'topic': msg.topic,
                            'partition': msg.partition,
                            'offset': msg.offset,
                            'key': msg.key,
                        }))

    def _worker_loop(self, worker_id: int):
        """工作线程循环"""
        logger.info(f"Worker {worker_id} started")

        while self._running:
            try:
                message, metadata = self.message_queue.get(timeout=1)

                if self.handler:
                    self.handler(message, metadata)

                self.message_queue.task_done()

            except Exception:
                pass  # Queue timeout

        logger.info(f"Worker {worker_id} stopped")

    def stop(self):
        """停止消费者"""
        self._running = False
        for worker in self.workers:
            worker.join(timeout=5)


# ============================================================
# 使用示例
# ============================================================

class OrderMessageHandler(MessageHandler):
    """订单消息处理器示例"""

    def handle(self, message: dict, metadata: dict) -> bool:
        """处理订单消息"""
        logger.info(
            f"Processing order - ID: {message.get('order_id')}, "
            f"User: {message.get('user')}, "
            f"Amount: {message.get('amount')}"
        )

        # 模拟业务处理
        # 1. 验证订单
        # 2. 更新数据库
        # 3. 发送通知
        # 4. 其他业务逻辑

        # 返回 True 表示处理成功
        # 返回 False 或抛出异常表示处理失败
        return True


def simple_message_handler(message: dict, metadata: dict) -> bool:
    """简单消息处理函数"""
    print(f"Received: {message}")
    print(f"Metadata: {metadata}")
    return True


def example_basic_consume():
    """基本消费示例"""
    print("\n=== 基本消费示例 ===")

    # 使用上下文管理器
    with KafkaConsumerAdvanced(
        topics=[TOPICS['ORDERS']],
        group_id='order-consumer-group',
        handler=OrderMessageHandler(),
    ) as consumer:
        # 设置信号处理，优雅关闭
        def signal_handler(sig, frame):
            print("\nReceived interrupt signal, shutting down...")
            consumer.stop()

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        # 开始消费
        consumer.consume(commit_mode='sync')


def example_functional_consume():
    """函数式消费示例"""
    print("\n=== 函数式消费示例 ===")

    with KafkaConsumerAdvanced(
        topics=[TOPICS['ORDERS']],
        group_id='functional-consumer-group',
    ) as consumer:
        # 使用函数作为处理器
        consumer.consume(
            handler=simple_message_handler,
            commit_mode='async',
        )


def example_seek_consume():
    """从指定位置开始消费示例"""
    print("\n=== 从指定位置开始消费示例 ===")

    with KafkaConsumerAdvanced(
        topics=[TOPICS['ORDERS']],
        group_id='seek-consumer-group',
    ) as consumer:
        # 从最早的消息开始
        consumer.seek_to_beginning()

        # 或者从最新的消息开始
        # consumer.seek_to_end()

        # 或者从指定偏移量开始
        # tp = TopicPartition(TOPICS['ORDERS'], 0)
        # consumer.seek(tp, 100)

        consumer.consume(handler=simple_message_handler)


if __name__ == '__main__':
    # 运行示例
    try:
        example_basic_consume()
    except KeyboardInterrupt:
        print("\nConsumer stopped by user")
    except Exception as e:
        logger.error(f"Error in example: {e}")
