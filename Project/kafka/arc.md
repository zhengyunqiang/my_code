好的，我来详细讲解 Kafka 代码架构和核心实现。

---

## 代码架构图

```
┌──────────────────────────────────────────────────────────────────────┐
│                         Kafka 代码架构                                 │
├──────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  ┌─────────────┐    ┌──────────────────────────────────────────┐     │
│  │  config.py  │───▶│  KAFKA_CONFIG / PRODUCER_CONFIG /        │     │
│  │  配置中心     │    │  CONSUMER_CONFIG / TOPICS                │     │
│  └─────────────┘    └──────────────────────────────────────────┘     │
│                           │                   │                       │
│                           ▼                   ▼                       │
│  ┌──────────────────────────────┐  ┌──────────────────────────┐     │
│  │   producer_advanced.py       │  │  consumer_advanced.py    │     │
│  │  ┌────────────────────────┐  │  │ ┌──────────────────────┐ │     │
│  │  │ KafkaProducerAdvanced  │  │  │ │ KafkaConsumerAdvanced│ │     │
│  │  │ - send()               │  │  │ │ - consume()          │ │     │
│  │  │ - send_batch()         │──│──││ │ - commit_sync()     │ │     │
│  │  │ - flush()              │  │  │ │ - seek()             │ │     │
│  │  └────────────────────────┘  │  │ └──────────────────────┘ │     │
│  │  ┌────────────────────────┐  │  │ ┌──────────────────────┐ │     │
│  │  │ CustomPartitioner      │  │  │ │ MessageHandler       │ │     │
│  │  │ - 决定消息去哪个分区     │  │  │ │ - handle()           │ │     │
│  │  └────────────────────────┘  │  │ └──────────────────────┘ │     │
│  │  ┌────────────────────────┐  │  │ ┌──────────────────────┐ │     │
│  │  │ ProducerCallback       │  │  │ │ DeadLetterQueue      │ │     │
│  │  │ - on_success()         │  │  │ │ - send_to_dlq()      │ │     │
│  │  │ - on_error()           │  │  │ └──────────────────────┘ │     │
│  │  └────────────────────────┘  │  │ ┌──────────────────────┐ │     │
│  └──────────────────────────────┘  │ │ RebalanceListener    │ │     │
│                                     │ │ - 分区分配/撤销回调    │ │     │
│                                     │ └──────────────────────┘ │     │
│                                     └──────────────────────────┘     │
│                                                                        │
│  ┌────────────────────────────────────────────────────────────┐      │
│  │              admin_tools.py / stream_processing.py          │      │
│  │              管理工具 / 流处理应用                              │      │
│  └────────────────────────────────────────────────────────────┘      │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 1. config.py - 配置中心

这是所有配置的统一入口，采用了**配置继承**的设计模式：

```python
# 基础配置
KAFKA_CONFIG = {
    'bootstrap_servers': ['localhost:9092'],  # Kafka 地址
    'security_protocol': 'PLAINTEXT',
}

# Producer 配置继承基础配置
PRODUCER_CONFIG = {
    **KAFKA_CONFIG,  # 继承基础配置
    'acks': 'all',           # 确认级别
    'retries': 3,            # 重试次数
    'batch_size': 16384,     # 批次大小
    'enable_idempotence': True,  # 幂等性
}
```

**关键配置说明：**

| 配置项 | 值 | 说明 |
|--------|-----|------|
| `acks` | `all` | 等待所有副本确认，最安全 |
| `enable_idempotence` | `True` | 防止消息重复 |
| `enable_auto_commit` | `False` | 手动提交偏移量，防止消息丢失 |
| `auto_offset_reset` | `earliest` | 新消费者从最早消息开始 |

---

## 2. producer_advanced.py - 生产者

### 核心类：`KafkaProducerAdvanced`

```python
class KafkaProducerAdvanced:
    def __init__(self, config=None, value_serializer=None, key_serializer=None):
        # 1. 保存配置
        # 2. 创建序列化器
        # 3. 初始化 Kafka Producer
        # 4. 初始化指标收集器
```

### 发送消息流程

```
┌─────────────┐
│  send()     │  用户调用发送
└──────┬──────┘
       │
       ▼
┌─────────────────┐
│  序列化消息      │  value_serializer(), key_serializer()
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  创建 Future    │  future = producer.send()
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  添加回调        │  add_callback(success), add_errback(error)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  同步/异步?     │  if sync: future.get() else return future
└────────┬────────┘
         │
         ▼
    返回结果
```

### 关键方法

```python
# 1. 同步发送 - 等待确认
metadata = producer.send(topic, value, sync=True)
# metadata.partition, metadata.offset

# 2. 异步发送 - 立即返回
future = producer.send(topic, value)
# 通过回调处理结果

# 3. 批量发送
producer.send_batch(topic, messages)

# 4. 指定分区
producer.send(topic, value, partition=0)

# 5. 使用 key 分区
producer.send(topic, value, key='user_123')
# 相同 key 的消息进入同一分区
```

---

## 3. consumer_advanced.py - 消费者

### 核心类：`KafkaConsumerAdvanced`

```python
class KafkaConsumerAdvanced:
    def __init__(self, topics, config, handler, enable_dlq=True):
        # 1. 创建 Kafka Consumer
        # 2. 设置反序列化器
        # 3. 初始化死信队列
        # 4. 设置再平衡监听器
```

### 消费消息流程

```
┌─────────────┐
│  consume()  │  启动消费循环
└──────┬──────┘
       │
       ▼
┌─────────────────┐
│  poll() 拉取消息 │  records = consumer.poll(timeout_ms=1000)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  处理每条消息    │  for msg in messages:
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  调用 handler   │  handler(message, metadata)
└────────┬────────┘
         │
    成功? ──No──▶ ┌─────────────────┐
       │          │  重试 (最多3次)   │
       Yes        └────────┬────────┘
         │                  │
         │            仍失败?
         │                  │
         ▼                  ▼
┌─────────────────┐  ┌─────────────────┐
│  提交偏移量      │  │  发送到死信队列   │
│  commit()       │  │  DeadLetterQueue │
└─────────────────┘  └─────────────────┘
```

### 关键特性

**1. 消息处理器 (MessageHandler)**

```python
class MessageHandler(ABC):
    @abstractmethod
    def handle(self, message: dict, metadata: dict) -> bool:
        # True: 处理成功
        # False: 处理失败，需要重试
```

**2. 死信队列 (DeadLetterQueue)**

```python
# 处理失败的消息发送到 DLQ
dlq.send_to_dlq(
    original_message=message,
    original_topic='orders',
    partition=0,
    offset=123,
    error=exception,
)
```

**3. 再平衡监听 (RebalanceListener)**

```python
class RebalanceListener:
    def on_partitions_assigned(self, assigned):
        # 分区分配时调用 - 初始化资源
        
    def on_partitions_revoked(self, revoked):
        # 分区撤销时调用 - 提交偏移量，清理资源
```

---

## 4. 使用示例对比

### 生产者使用

```python
from producer_advanced import KafkaProducerAdvanced
from config import TOPICS

# 方式一：上下文管理器（推荐）
with KafkaProducerAdvanced() as producer:
    producer.send(
        topic=TOPICS['ORDERS'],
        value={'order_id': '123', 'amount': 99.9},
        key='user_1',  # 相同用户进入同一分区
    )

# 方式二：手动管理
producer = KafkaProducerAdvanced()
try:
    producer.send(topic, value)
finally:
    producer.close()
```

### 消费者使用

```python
from consumer_advanced import KafkaConsumerAdvanced, MessageHandler

# 方式一：使用 MessageHandler 类
class OrderHandler(MessageHandler):
    def handle(self, message, metadata):
        print(f"Processing: {message}")
        return True  # 处理成功

with KafkaConsumerAdvanced(
    topics=['orders'],
    handler=OrderHandler(),
) as consumer:
    consumer.consume(commit_mode='sync')

# 方式二：使用函数
def process(message, metadata):
    print(f"Received: {message}")
    return True

with KafkaConsumerAdvanced(topics=['orders']) as consumer:
    consumer.consume(handler=process)
```

---

## 5. 设计模式应用

| 设计模式 | 应用位置 | 说明 |
|----------|----------|------|
| **工厂模式** | 序列化器 | 根据配置创建 JSON/Avro 序列化器 |
| **策略模式** | MessageHandler | 不同的消息处理策略 |
| **观察者模式** | ProducerCallback | 发送成功/失败的回调通知 |
| **模板方法** | consume() | 定义消费流程，子类实现 handle() |
| **上下文管理** | `with` 语句 | 自动管理资源生命周期 |

---

## 6. 核心流程图

### 端到端消息流

```
Producer                           Kafka                           Consumer
┌─────────┐                       ┌─────┐                        ┌─────────┐
│ App     │                       │Topic│                        │ App     │
└────┬────┘                       └──┬──┘                        └────┬────┘
     │                               │                               │
     │ send(message)                 │                               │
     ├──────────────────────────────▶│                               │
     │                               │                               │
     │    返回 Future                 │                               │
     │◀──────────────────────────────┤                               │
     │                               │                               │
     │    callback.on_success()      │                               │
     │    (partition=0, offset=5)    │                               │
     │                               │                               │
     │                               │    poll() 拉取                 │
     │                               ├──────────────────────────────▶│
     │                               │                               │
     │                               │    message                    │
     │                               │                               │
     │                               │    process(message)           │
     │                               │                               │
     │                               │    commit offset=5            │
     │                               │◀──────────────────────────────┤
     │                               │                               │
```

---

需要我详细讲解某个特定部分吗？比如分区策略、死信队列实现、或者流处理应用？