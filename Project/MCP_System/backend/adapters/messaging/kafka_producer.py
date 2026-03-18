"""
Kafka Producer Adapter
Kafka 生产者适配器 - 复用 Kafka 项目的生产者
"""

import json
import asyncio
from typing import Any, Dict, Optional, Callable
from dataclasses import dataclass
from datetime import datetime

from backend.core.logging import get_logger
from backend.config import settings

logger = get_logger(__name__)


@dataclass
class KafkaMessage:
    """Kafka 消息"""
    topic: str
    value: Any
    key: Optional[str] = None
    partition: Optional[int] = None
    headers: Optional[Dict[str, str]] = None
    timestamp: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "topic": self.topic,
            "value": self.value,
            "key": self.key,
            "partition": self.partition,
            "headers": self.headers,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }


@dataclass
class ProducerMetrics:
    """生产者指标"""
    messages_sent: int = 0
    messages_failed: int = 0
    bytes_sent: int = 0
    last_error: Optional[str] = None


class KafkaProducerAdapter:
    """
    Kafka 生产者适配器

    异步发送消息到 Kafka
    """

    def __init__(self, bootstrap_servers: Optional[list] = None):
        """
        初始化 Kafka 生产者

        Args:
            bootstrap_servers: Kafka 服务器列表
        """
        self.bootstrap_servers = bootstrap_servers or settings.KAFKA_BOOTSTRAP_SERVERS
        self._producer = None
        self._metrics = ProducerMetrics()
        self._enabled = settings.KAFKA_ENABLED

    async def start(self) -> None:
        """启动生产者"""
        if not self._enabled:
            logger.info("Kafka is disabled, skipping producer initialization")
            return

        try:
            from confluent_kafka import Producer as ConfluentProducer

            config = {
                "bootstrap.servers": ",".join(self.bootstrap_servers),
                "security.protocol": settings.KAFKA_SECURITY_PROTOCOL,
                "acks": "all",
                "retries": 3,
                "client.id": f"mcp-system-producer-{id(self)}",
            }

            self._producer = ConfluentProducer(config)
            logger.info(f"Kafka producer started: {self.bootstrap_servers}")

        except ImportError:
            logger.warning("confluent-kafka not installed, Kafka producer disabled")
            self._enabled = False
        except Exception as e:
            logger.error(f"Failed to start Kafka producer: {e}")
            self._enabled = False

    async def stop(self) -> None:
        """停止生产者"""
        if self._producer:
            try:
                # 冲刷缓冲区
                self._producer.flush(timeout=10)
                logger.info("Kafka producer stopped")
            except Exception as e:
                logger.error(f"Error stopping Kafka producer: {e}")

    async def send(
        self,
        message: KafkaMessage,
        callback: Optional[Callable] = None,
    ) -> bool:
        """
        发送消息

        Args:
            message: Kafka 消息
            callback: 回调函数

        Returns:
            是否成功
        """
        if not self._enabled or not self._producer:
            logger.debug("Kafka producer not enabled, message not sent")
            return False

        try:
            # 序列化值
            if isinstance(message.value, (dict, list)):
                value = json.dumps(message.value).encode("utf-8")
            else:
                value = str(message.value).encode("utf-8")

            # 序列化键
            key = message.key.encode("utf-8") if message.key else None

            # 创建 Kafka 消息
            from confluent_kafka import Message as ConfluentMessage

            def delivery_callback(err, msg):
                if err:
                    self._metrics.messages_failed += 1
                    self._metrics.last_error = str(err)
                    logger.error(f"Kafka delivery error: {err}")
                else:
                    self._metrics.messages_sent += 1
                    self._metrics.bytes_sent += len(value)

                if callback:
                    callback(err, msg)

            # 发送消息
            self._producer.produce(
                topic=message.topic,
                value=value,
                key=key,
                partition=message.partition,
                headers=message.headers,
                timestamp=int(message.timestamp.timestamp() * 1000) if message.timestamp else None,
                on_delivery=delivery_callback,
            )

            # 触发轮询（确保回调被执行）
            self._producer.poll(0)

            return True

        except Exception as e:
            self._metrics.messages_failed += 1
            self._metrics.last_error = str(e)
            logger.error(f"Error sending Kafka message: {e}")
            return False

    async def send_batch(
        self,
        messages: list[KafkaMessage],
    ) -> int:
        """
        批量发送消息

        Args:
            messages: Kafka 消息列表

        Returns:
            成功发送的数量
        """
        success_count = 0

        for message in messages:
            if await self.send(message):
                success_count += 1

        # 冲刷缓冲区
        if self._producer:
            self._producer.flush(timeout=10)

        return success_count

    async def poll(self, timeout: float = 0.0) -> None:
        """
        轮询事件

        Args:
            timeout: 超时时间（秒）
        """
        if self._producer:
            self._producer.poll(timeout=timeout)

    def get_metrics(self) -> Dict[str, Any]:
        """
        获取指标

        Returns:
            指标字典
        """
        return {
            "messages_sent": self._metrics.messages_sent,
            "messages_failed": self._metrics.messages_failed,
            "bytes_sent": self._metrics.bytes_sent,
            "last_error": self._metrics.last_error,
        }


# 全局 Kafka 生产者实例
kafka_producer: Optional[KafkaProducerAdapter] = None


async def init_kafka_producer(
    bootstrap_servers: Optional[list] = None,
) -> Optional[KafkaProducerAdapter]:
    """
    初始化 Kafka 生产者

    Args:
        bootstrap_servers: Kafka 服务器列表

    Returns:
        KafkaProducerAdapter 实例或 None
    """
    global kafka_producer
    kafka_producer = KafkaProducerAdapter(bootstrap_servers)
    await kafka_producer.start()
    return kafka_producer


__all__ = [
    "KafkaMessage",
    "ProducerMetrics",
    "KafkaProducerAdapter",
    "kafka_producer",
    "init_kafka_producer",
]
