"""
Kafka 配置文件
生产环境配置最佳实践
"""

# Kafka 集群配置
KAFKA_CONFIG = {
    # Kafka 服务器地址列表（生产环境建议至少3个节点）
    'bootstrap_servers': [
        'localhost:9092',
        # 'kafka-broker-1:9092',
        # 'kafka-broker-2:9092',
        # 'kafka-broker-3:9092',
    ],

    # 安全配置（生产环境必须启用）
    'security_protocol': 'PLAINTEXT',  # PLAINTEXT, SSL, SASL_PLAINTEXT, SASL_SSL
    # 'sasl_mechanism': 'PLAIN',
    # 'sasl_plain_username': 'your_username',
    # 'sasl_plain_password': 'your_password',
    # 'ssl_cafile': '/path/to/ca.pem',
    # 'ssl_certfile': '/path/to/cert.pem',
    # 'ssl_keyfile': '/path/to/key.pem',
}

# Producer 配置
PRODUCER_CONFIG = {
    **KAFKA_CONFIG,

    # 消息确认级别
    # 0: 不等待确认（最快，可能丢失消息）
    # 1: 等待 Leader 确认（默认，平衡性能和可靠性）
    # all/-1: 等待所有 ISR 副本确认（最安全，性能较低）
    'acks': 'all',

    # 重试配置
    'retries': 3,  # 重试次数
    'retry_backoff_ms': 100,  # 重试间隔

    # 批处理配置（提高吞吐量）
    'batch_size': 16384,  # 批次大小（字节）
    'linger_ms': 5,  # 等待时间，积累更多消息
    'buffer_memory': 33554432,  # 缓冲区大小（32MB）

    # 消息压缩（减少网络传输和存储）
    # 需要 pip install lz4 或 snappy 才能使用压缩
    'compression_type': None,  # none, gzip, snappy, lz4, zstd

    # 幂等性（防止消息重复）
    'enable_idempotence': True,

    # 事务支持（跨分区原子写入）
    # 'transactional_id': 'my-transactional-producer',

    # 消息最大大小
    'max_request_size': 1048576,  # 1MB

    # 请求超时
    'request_timeout_ms': 30000,  # 30秒
}

# Consumer 配置
CONSUMER_CONFIG = {
    **KAFKA_CONFIG,

    # 消费者组 ID（同一组内的消费者分担消费）
    'group_id': 'my-consumer-group',

    # 自动提交偏移量
    'enable_auto_commit': False,  # 生产环境建议手动提交
    'auto_commit_interval_ms': 5000,

    # 没有初始偏移量时的行为
    # earliest: 从最早的消息开始
    # latest: 从最新的消息开始（默认）
    # none: 抛出异常
    'auto_offset_reset': 'earliest',

    # 消费者会话超时（超过此时间认为消费者失效）
    'session_timeout_ms': 10000,  # 10秒

    # 心跳间隔（必须小于 session_timeout_ms）
    'heartbeat_interval_ms': 3000,  # 3秒

    # 最大轮询间隔（两次 poll 之间的最大间隔）
    'max_poll_interval_ms': 300000,  # 5分钟

    # 单次 poll 返回的最大记录数
    'max_poll_records': 500,

    # 预取字节数
    'fetch_min_bytes': 1,
    'fetch_max_bytes': 52428800,  # 50MB

    # 隔离级别
    # read_uncommitted: 读取所有消息
    # read_committed: 只读取已提交事务的消息
    'isolation_level': 'read_uncommitted',
}

# Topic 配置
TOPIC_CONFIG = {
    'num_partitions': 3,  # 分区数（影响并行度）
    'replication_factor': 1,  # 副本数（生产环境建议 >= 3）
    'retention_ms': 604800000,  # 消息保留时间（7天）
    'retention_bytes': -1,  # 消息保留大小（-1 表示无限制）
}

# Topic 名称
TOPICS = {
    'ORDERS': 'orders',
    'PAYMENTS': 'payments',
    'NOTIFICATIONS': 'notifications',
    'DLQ': 'dead-letter-queue',  # 死信队列
}
