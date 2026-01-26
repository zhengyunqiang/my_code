import time
import json
from kafka import KafkaProducer

# 1. 初始化生产者
producer = KafkaProducer(
    bootstrap_servers=['localhost:9092'],  # Kafka 服务器地址
    # value_serializer: 定义如何序列化数据，这里我们将字典转为 JSON bytes
    value_serializer=lambda v: json.dumps(v).encode('utf-8')
)

topic_name = 'order_topic'

print(f"开始向主题 '{topic_name}' 发送数据...")

try:
    for i in range(10):
        # 2. 构造数据
        data = {
            'order_id': i + 1000,
            'user': f'user_{i}',
            'price': 99.5 + i,
            'timestamp': time.time()
        }

        # 3. 发送消息
        # send 是异步的，它会立即返回一个 Future 对象
        future = producer.send(topic_name, value=data)

        # 4. (可选) 获取发送结果
        # 在生产环境中通常不这样做，因为会阻塞，这里仅为了演示成功
        result = future.get(timeout=10)

        print(f"发送成功: {data} -> Partition: {result.partition}, Offset: {result.offset}")

        time.sleep(2)  # 模拟每2秒产生一条数据

except Exception as e:
    print(f"发送出错: {e}")

finally:
    # 5. 关闭连接
    producer.close()