# Kafka 生产级应用代码

完整的 Apache Kafka 生产级应用代码，涵盖从基础到高级的所有使用场景。

## 目录

```
kafka/
├── config.py              # 配置文件
├── producer_advanced.py   # 高级生产者
├── consumer_advanced.py   # 高级消费者
├── admin_tools.py         # 管理工具
├── stream_processing.py   # 流处理应用
├── docker-compose.yml     # Docker 环境
└── README.md              # 本文档
```

## 快速开始

### 1. 启动 Kafka 环境

```bash
# 启动 Kafka 集群 (包含 Zookeeper, Kafka, Kafka UI)
docker-compose up -d

# 查看服务状态
docker-compose ps

# 访问 Kafka UI
open http://localhost:8080
```

### 2. 安装 Python 依赖

```bash
pip install kafka-python
```

### 3. 运行示例

```bash
# 运行生产者
python producer_advanced.py

# 运行消费者 (新终端)
python consumer_advanced.py

# 运行流处理应用
python stream_processing.py

# 运行管理工具
python admin_tools.py
```

## Kafka 核心概念

### 架构图

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Kafka Architecture                           │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  Producer                Kafka Cluster                   Consumer   │
│  ┌─────────┐      ┌──────────────────────────────┐     ┌─────────┐  │
│  │ App 1   │─────▶│         Topic: orders        │────▶│ App A   │  │
│  ├─────────┤      │  ┌────────┐ ┌────────┐       │     ├─────────┤  │
│  │ App 2   │─────▶│  │Part 0  │ │Part 1  │       │────▶│ App B   │  │
│  ├─────────┤      │  │0,1,2...│ │0,1,2...│       │     ├─────────┤  │
│  │ App 3   │─────▶│  └────────┘ └────────┘       │────▶│ App C   │  │
│  └─────────┘      │         ┌────────┐           │     └─────────┘  │
│                   │         │Part 2  │           │                  │
│                   │         │0,1,2...│           │                  │
│                   │         └────────┘           │                  │
│                   └──────────────────────────────┘                  │
│                                                                      │
│  核心概念:                                                           │
│  • Broker: Kafka 服务器节点                                          │
│  • Topic: 消息主题/分类                                              │
│  • Partition: 分区，实现并行处理                                      │
│  • Offset: 消息在分区中的位置                                         │
│  • Consumer Group: 消费者组，实现消息广播和负载均衡                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 消息传递模式

```
┌───────────────────────────────────────────────────────────────────────┐
│                      消息传递模式对比                                   │
├───────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  1. 点对点 (Queue) - 同一 Consumer Group                               │
│     ┌─────────┐      ┌─────────┐      ┌─────────┐                     │
│     │Producer │─────▶│ Topic   │─────▶│Consumer │ (Group A)           │
│     └─────────┘      └─────────┘      ├─────────┤                     │
│                                       │Consumer │ (Group A)           │
│                                       └─────────┘                     │
│                     每条消息只被组内一个消费者处理                        │
│                                                                        │
│  2. 发布订阅 (Pub/Sub) - 不同 Consumer Group                           │
│     ┌─────────┐      ┌─────────┐      ┌─────────┐                     │
│     │Producer │─────▶│ Topic   │─────▶│Consumer │ (Group A)           │
│     └─────────┘      └─────────┘      ├─────────┤                     │
│                                       │Consumer │ (Group B)           │
│                                       └─────────┘                     │
│                     每条消息被所有组消费一次                             │
│                                                                        │
└───────────────────────────────────────────────────────────────────────┘
```

## 模块详解

### 1. 配置文件 (config.py)

```python
from config import PRODUCER_CONFIG, CONSUMER_CONFIG, TOPICS

# 生产者配置
PRODUCER_CONFIG = {
    'bootstrap_servers': ['localhost:9092'],
    'acks': 'all',           # 消息确认级别
    'retries': 3,            # 重试次数
    'batch_size': 16384,     # 批次大小
    'linger_ms': 5,          # 等待时间
    'compression_type': 'lz4', # 压缩算法
    'enable_idempotence': True, # 幂等性
}

# 消费者配置
CONSUMER_CONFIG = {
    'bootstrap_servers': ['localhost:9092'],
    'group_id': 'my-group',
    'enable_auto_commit': False,  # 手动提交
    'auto_offset_reset': 'earliest',
}
```

### 2. 高级生产者 (producer_advanced.py)

```python
from producer_advanced import KafkaProducerAdvanced
from config import TOPICS

# 使用上下文管理器
with KafkaProducerAdvanced() as producer:
    # 异步发送
    producer.send(
        topic=TOPICS['ORDERS'],
        value={'order_id': '123', 'amount': 99.9},
        key='user_1',  # 相同 key 进入同一分区
    )

    # 同步发送
    metadata = producer.send(
        topic=TOPICS['ORDERS'],
        value={'order_id': '456'},
        sync=True,
    )
    print(f"Sent to partition {metadata.partition}")

    # 批量发送
    messages = [{'order_id': f'{i}'} for i in range(100)]
    producer.send_batch(TOPICS['ORDERS'], messages)

    # 查看指标
    print(producer.get_metrics())
```

### 3. 高级消费者 (consumer_advanced.py)

```python
from consumer_advanced import KafkaConsumerAdvanced, MessageHandler
from config import TOPICS

# 方式一：使用 MessageHandler 类
class OrderHandler(MessageHandler):
    def handle(self, message: dict, metadata: dict) -> bool:
        print(f"Processing: {message}")
        return True  # True=成功, False=失败进入死信队列

with KafkaConsumerAdvanced(
    topics=[TOPICS['ORDERS']],
    group_id='order-consumer',
    handler=OrderHandler(),
) as consumer:
    consumer.consume(commit_mode='sync')

# 方式二：使用回调函数
def process_message(message: dict, metadata: dict) -> bool:
    print(f"Received: {message}")
    return True

with KafkaConsumerAdvanced(topics=[TOPICS['ORDERS']]) as consumer:
    consumer.consume(handler=process_message)
```

### 4. 管理工具 (admin_tools.py)

```python
from admin_tools import KafkaAdminTools

with KafkaAdminTools() as admin:
    # 创建 Topic
    admin.create_topic(
        topic_name='new-topic',
        num_partitions=3,
        replication_factor=1,
    )

    # 列出所有 Topic
    topics = admin.list_topics()

    # 查看 Consumer Group
    groups = admin.list_consumer_groups()
    offsets = admin.list_consumer_group_offsets('my-group')

    # 删除 Topic
    admin.delete_topic('old-topic')
```

### 5. 流处理应用 (stream_processing.py)

```python
from stream_processing import OrderService, OrderStatus

# 创建订单服务
order_service = OrderService()

# 创建订单
order = order_service.create_order(
    user_id='user_123',
    items=[
        {'product_id': 'P001', 'price': 99.9, 'quantity': 2},
    ]
)

# 更新状态
order_service.update_order_status(order, OrderStatus.CONFIRMED)
order_service.update_order_status(order, OrderStatus.PAID)
```

## 生产环境最佳实践

### 1. 生产者配置

```python
# 高可靠性配置
PRODUCER_CONFIG = {
    'acks': 'all',              # 等待所有副本确认
    'retries': 3,               # 重试次数
    'enable_idempotence': True, # 幂等性，防止重复
    'max.in.flight.requests.per.connection': 5,
}

# 高吞吐量配置
PRODUCER_CONFIG = {
    'acks': '1',                # 只等待 Leader 确认
    'batch_size': 32768,        # 更大的批次
    'linger_ms': 20,            # 等待更多消息
    'compression_type': 'lz4',  # 压缩
    'buffer_memory': 67108864,  # 64MB 缓冲区
}
```

### 2. 消费者配置

```python
# 高可靠性配置
CONSUMER_CONFIG = {
    'enable_auto_commit': False,  # 手动提交
    'max_poll_records': 100,      # 控制处理速度
    'session_timeout_ms': 30000,  # 会话超时
    'max_poll_interval_ms': 600000,  # 处理超时
}

# 消费逻辑
def consume_loop():
    while running:
        records = consumer.poll(timeout_ms=1000)
        for topic_partition, messages in records.items():
            for msg in messages:
                try:
                    process_message(msg.value)
                    # 处理成功后手动提交
                    consumer.commit()
                except Exception as e:
                    handle_error(e)
                    # 发送到死信队列
```

### 3. 错误处理

```python
# 生产者错误处理
try:
    future = producer.send(topic, value)
    future.add_callback(on_success)
    future.add_errback(on_error)
except KafkaError as e:
    logger.error(f"Failed to send: {e}")
    # 本地存储或重试

# 消费者错误处理
def handle_message(message):
    try:
        process(message)
        return True
    except RetriableError:
        # 可重试错误
        raise
    except FatalError:
        # 致命错误，发送到死信队列
        send_to_dlq(message)
        return True  # 跳过这条消息
```

### 4. 监控指标

```python
# 关键监控指标

# 生产者
- record-send-rate: 发送速率
- record-error-rate: 错误率
- request-latency-avg: 平均延迟
- buffer-available-bytes: 可用缓冲区

# 消费者
- records-consumed-rate: 消费速率
- records-lag-max: 最大延迟
- commit-rate: 提交速率
- fetch-latency-avg: 拉取延迟

# Broker
- MessagesInPerSec: 消息流入速率
- BytesInPerSec: 字节流入速率
- UnderReplicatedPartitions: 副本不足的分区
```

## 常见问题解决

### 1. 消息丢失

```python
# 解决方案：
# 1. 生产者: acks=all, enable_idempotence=True
# 2. 消费者: enable_auto_commit=False, 手动提交
# 3. Topic: replication_factor >= 3, min.insync.replicas >= 2
```

### 2. 消息重复

```python
# 解决方案：
# 1. 生产者: enable_idempotence=True
# 2. 消费者: 实现幂等性处理
def process_message(message):
    message_id = message['id']
    if already_processed(message_id):
        return True  # 跳过已处理的消息
    # 处理消息
    mark_as_processed(message_id)
```

### 3. 消费延迟

```python
# 解决方案：
# 1. 增加 Consumer 数量（不超过分区数）
# 2. 增加分区数
# 3. 优化处理逻辑
# 4. 使用多线程处理
```

## 性能调优

### 分区数选择

```
分区数建议：
- 根据目标吞吐量计算
- 分区数 = 目标吞吐量 / 单个分区吞吐量

例如：
- 目标: 100MB/s
- 单分区: 20MB/s
- 分区数 = 100 / 20 = 5
```

### JVM 调优 (Broker)

```bash
# Kafka Broker JVM 配置
export KAFKA_HEAP_OPTS="-Xms6g -Xmx6g"
export KAFKA_JVM_PERFORMANCE_OPTS="-XX:+UseG1GC -XX:MaxGCPauseMillis=20"
```

## 参考资源

- [Kafka 官方文档](https://kafka.apache.org/documentation/)
- [Confluent 文档](https://docs.confluent.io/)
- [kafka-python 库](https://github.com/dpkp/kafka-python)

## 许可证

MIT License
