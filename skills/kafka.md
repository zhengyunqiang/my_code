---
description: Apache Kafka 生产级应用开发指南 - 包含 Producer、Consumer、Admin Tools 和流处理的完整实现
---

# Apache Kafka 生产级应用开发

本指南提供了完整的 Kafka 生产级应用代码，涵盖从基础到高级的所有使用场景。

## 项目位置

```
/Users/ywwl/P_my_code/Project/kafka/
```

## 快速启动

### 1. 启动 Kafka 环境

```bash
cd /Users/ywwl/P_my_code/Project/kafka
docker-compose up -d
```

等待约 30 秒让服务完全启动。

### 2. 安装依赖

```bash
pip install kafka-python
```

### 3. 运行示例

```bash
# 生产者
python producer_advanced.py

# 消费者（新终端）
python consumer_advanced.py

# 流处理应用
python stream_processing.py

# 管理工具
python admin_tools.py
```

### 4. 访问 Kafka UI

浏览器打开: http://localhost:8080

## 核心模块

### 配置文件 (config.py)

```python
# Producer 配置
PRODUCER_CONFIG = {
    'bootstrap_servers': ['localhost:9092'],
    'acks': 'all',              # 消息确认级别 (0/1/all)
    'retries': 3,               # 重试次数
    'enable_idempotence': True, # 幂等性，防止消息重复
    'compression_type': None,   # 压缩（需安装 lz4）
}

# Consumer 配置
CONSUMER_CONFIG = {
    'bootstrap_servers': ['localhost:9092'],
    'group_id': 'my-consumer-group',
    'enable_auto_commit': False,  # 手动提交偏移量
    'auto_offset_reset': 'earliest', # 从最早消息开始
}
```

### 生产者使用

```python
from producer_advanced import KafkaProducerAdvanced
from config import TOPICS

# 异步发送（推荐）
with KafkaProducerAdvanced() as producer:
    producer.send(
        topic=TOPICS['ORDERS'],
        value={'order_id': '123', 'amount': 99.9},
        key='user_1',  # 相同 key 进入同一分区
    )

# 同步发送
metadata = producer.send(topic, value, sync=True)
print(f"Partition: {metadata.partition}, Offset: {metadata.offset}")

# 批量发送
producer.send_batch(topic, messages)

# 指定分区
producer.send(topic, value, partition=0)
```

### 消费者使用

```python
from consumer_advanced import KafkaConsumerAdvanced, MessageHandler

# 方式一：使用 MessageHandler 类
class OrderHandler(MessageHandler):
    def handle(self, message, metadata):
        print(f"Processing: {message}")
        return True  # True=成功, False=失败进入死信队列

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

### 管理工具

```python
from admin_tools import KafkaAdminTools

with KafkaAdminTools() as admin:
    # 创建 Topic
    admin.create_topic('new-topic', num_partitions=3, replication_factor=1)

    # 列出 Topic
    topics = admin.list_topics()

    # 查看 Consumer Group
    groups = admin.list_consumer_groups()

    # 获取 Topic 详情
    info = admin.describe_topic('orders')
```

## Kafka 核心概念

### 架构图

```
Producer                Kafka Cluster                   Consumer
┌─────────┐      ┌──────────────────────┐     ┌─────────┐
│ App 1   │─────▶│      Topic: orders   │─────▶│ App A   │
├─────────┤      │  ┌────────┐ ┌───────┐│     ├─────────┤
│ App 2   │─────▶│  │Part 0  │ │Part 1 ││─────▶│ App B   │
└─────────┘      │  │0,1,2...│ │0,1,2..││     └─────────┘
                 │  └────────┘ └───────┘│
                 │      ┌────────┐      │
                 │      │Part 2  │      │
                 │      │0,1,2...│      │
                 │      └────────┘      │
                 └──────────────────────┘
```

### 消息传递模式

**点对点（Queue）** - 同一 Consumer Group
- 每条消息只被组内一个消费者处理
- 实现负载均衡

**发布订阅（Pub/Sub）** - 不同 Consumer Group
- 每条消息被所有组消费一次
- 实现消息广播

## 核心配置说明

### Producer 配置

| 配置项 | 值 | 说明 |
|--------|-----|------|
| `acks` | `all` | 等待所有副本确认（最安全）|
| `retries` | `3` | 失败重试次数 |
| `batch_size` | `16384` | 批次大小（字节）|
| `linger_ms` | `5` | 等待时间积累更多消息 |
| `enable_idempotence` | `True` | 幂等性，防止重复 |

### Consumer 配置

| 配置项 | 值 | 说明 |
|--------|-----|------|
| `group_id` | 自定义 | 消费者组 ID |
| `enable_auto_commit` | `False` | 手动提交偏移量 |
| `auto_offset_reset` | `earliest` | 从最早消息开始 |
| `session_timeout_ms` | `10000` | 会话超时（毫秒）|
| `max_poll_records` | `500` | 单次拉取最大记录数 |

## 生产环境最佳实践

### 高可靠性配置

```python
# Producer
'acks': 'all',                    # 等待所有副本确认
'enable_idempotence': True,       # 防止消息重复
'retries': 3,                     # 重试次数

# Consumer
'enable_auto_commit': False,      # 手动提交
'isolation_level': 'read_committed', # 只读已提交消息

# Topic
'replication_factor': 3,          # 至少3个副本
'min.insync.replicas': 2,         # 至少2个同步副本
```

### 高吞吐量配置

```python
'batch_size': 32768,              # 更大批次
'linger_ms': 20,                  # 等待积累消息
'compression_type': 'lz4',        # 压缩（需 pip install lz4）
'buffer_memory': 67108864,        # 64MB 缓冲
'fetch_max_bytes': 52428800,      # 50MB 预取
```

### 错误处理与死信队列

```python
# 失败消息自动进入死信队列
class DeadLetterQueue:
    def send_to_dlq(self, message, topic, partition, offset, error):
        dlq_message = {
            'original_message': message,
            'original_topic': topic,
            'error': str(error),
            'failed_at': datetime.now().isoformat(),
        }
        self.producer.send('dead-letter-queue', dlq_message)
```

## 常见问题解决

### 消息丢失

**原因**: 生产者未等待确认、消费者自动提交失败

**解决**:
```python
# 生产者: acks='all', enable_idempotence=True
# 消费者: enable_auto_commit=False, 手动提交
# Topic: replication_factor >= 3
```

### 消息重复

**原因**: 网络重试导致重复发送

**解决**:
```python
# 生产者: enable_idempotence=True
# 消费者: 实现幂等性处理
def process_message(message):
    message_id = message['id']
    if already_processed(message_id):
        return True  # 跳过
    # 处理消息
    mark_as_processed(message_id)
```

### 消费延迟

**原因**: 消费速度 < 生产速度

**解决**:
```python
# 1. 增加 Consumer 数量（不超过分区数）
# 2. 增加分区数
# 3. 优化处理逻辑
# 4. 使用多线程处理
```

## 监控指标

| 指标 | 说明 | 阈值 |
|------|------|------|
| `record-send-rate` | 发送速率 | - |
| `record-error-rate` | 错误率 | < 0.1% |
| `request-latency-avg` | 平均延迟 | < 100ms |
| `records-consumed-rate` | 消费速率 | - |
| `records-lag-max` | 最大消费延迟 | < 1000 |

## 文件结构

```
kafka/
├── config.py              # 配置文件（Producer/Consumer/Topic）
├── producer_advanced.py   # 高级生产者（异步/同步/批量/回调）
├── consumer_advanced.py   # 高级消费者（消费者组/重试/死信队列）
├── admin_tools.py         # 管理工具（Topic/Consumer Group 管理）
├── stream_processing.py   # 流处理应用（订单/分析/事件溯源）
├── docker-compose.yml     # Docker 环境（Kafka/Zookeeper/UI）
├── requirements.txt       # Python 依赖
└── README.md              # 详细文档
```

## 关键类和方法

### KafkaProducerAdvanced

```python
# 初始化
producer = KafkaProducerAdvanced(config=None)

# 发送消息
producer.send(topic, value, key=None, partition=None, headers=None, callback=True, sync=False)

# 批量发送
producer.send_batch(topic, messages, key_extractor=None)

# 刷新缓冲区
producer.flush(timeout=None)

# 获取指标
producer.get_metrics()  # {'messages_sent': 100, 'success_rate': 100.0}

# 关闭
producer.close(timeout=10)
```

### KafkaConsumerAdvanced

```python
# 初始化
consumer = KafkaConsumerAdvanced(topics, config, group_id, handler)

# 消费消息
consumer.consume(handler=None, batch_size=1, max_retries=3, commit_mode='sync')

# 手动提交
consumer.commit_sync(offsets=None)
consumer.commit_async(offsets=None)

# 定位消费位置
consumer.seek_to_beginning(partitions=None)
consumer.seek_to_end(partitions=None)
consumer.seek(partition, offset)

# 暂停/恢复
consumer.pause(partitions=None)
consumer.resume(partitions=None)

# 获取指标
consumer.get_metrics()
```

### KafkaAdminTools

```python
# Topic 管理
admin.create_topic(topic_name, num_partitions, replication_factor)
admin.delete_topic(topic_name)
admin.list_topics()
admin.describe_topic(topic_name)

# Consumer Group 管理
admin.list_consumer_groups()
admin.describe_consumer_group(group_id)
admin.delete_consumer_group(group_id)
admin.list_consumer_group_offsets(group_id)

# 配置管理
admin.get_topic_config(topic_name)
admin.alter_topic_config(topic_name, config_updates)

# 集群信息
admin.describe_cluster()
```

## 设计模式

| 设计模式 | 应用位置 | 说明 |
|----------|----------|------|
| 工厂模式 | 序列化器 | 根据配置创建 JSON/Avro 序列化器 |
| 策略模式 | MessageHandler | 不同的消息处理策略 |
| 观察者模式 | ProducerCallback | 发送成功/失败的回调通知 |
| 模板方法 | consume() | 定义消费流程，子类实现 handle() |
| 上下文管理 | `with` 语句 | 自动管理资源生命周期 |

## 端到端消息流

```
Producer                           Kafka                           Consumer
┌─────────┐                       ┌─────┐                        ┌─────────┐
│ App     │                       │Topic│                        │ App     │
└────┬────┘                       └──┬──┘                        └────┬────┘
     │                               │                               │
     │ send(message)                 │                               │
     ├──────────────────────────────▶│                               │
     │                               │                               │
     │    返回 Future                │                               │
     │◀──────────────────────────────┤                               │
     │                               │                               │
     │    callback.on_success()      │                               │
     │    (partition=0, offset=5)    │                               │
     │                               │                               │
     │                               │    poll() 拉取                │
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

## 参考资源

- [Kafka 官方文档](https://kafka.apache.org/documentation/)
- [Confluent 文档](https://docs.confluent.io/)
- [kafka-python](https://github.com/dpkp/kafka-python)
- [Kafka UI](https://github.com/provectus/kafka-ui)
