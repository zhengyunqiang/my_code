"""
Messaging Adapters Package
消息队列适配器 - Kafka
"""

from backend.adapters.messaging.kafka_producer import (
    KafkaMessage,
    ProducerMetrics,
    KafkaProducerAdapter,
    kafka_producer,
    init_kafka_producer,
)

__all__ = [
    "KafkaMessage",
    "ProducerMetrics",
    "KafkaProducerAdapter",
    "kafka_producer",
    "init_kafka_producer",
]
