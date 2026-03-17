"""
Kafka Admin 管理工具
用于管理 Topic、Consumer Group、配置等
"""

import json
import logging
from typing import List, Dict, Optional
from kafka import KafkaAdminClient
from kafka.admin import NewTopic, ConfigResource, ConfigResourceType
from kafka.errors import TopicAlreadyExistsError, UnknownTopicOrPartitionError

from config import KAFKA_CONFIG, TOPIC_CONFIG

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class KafkaAdminTools:
    """
    Kafka 管理工具

    功能:
    - Topic 创建/删除/修改
    - Consumer Group 管理
    - 配置管理
    - 集群信息查询
    """

    def __init__(self, config: dict = None):
        self.config = config or KAFKA_CONFIG
        self.admin_client = None
        self._connect()

    def _connect(self):
        """连接到 Kafka 集群"""
        try:
            self.admin_client = KafkaAdminClient(
                bootstrap_servers=self.config['bootstrap_servers'],
                security_protocol=self.config.get('security_protocol', 'PLAINTEXT'),
            )
            logger.info("Connected to Kafka cluster")
        except Exception as e:
            logger.error(f"Failed to connect to Kafka: {e}")
            raise

    # ============================================================
    # Topic 管理
    # ============================================================

    def create_topic(
        self,
        topic_name: str,
        num_partitions: int = 3,
        replication_factor: int = 1,
        topic_config: dict = None,
    ) -> bool:
        """
        创建 Topic

        Args:
            topic_name: Topic 名称
            num_partitions: 分区数
            replication_factor: 副本因子
            topic_config: Topic 配置

        Returns:
            是否创建成功
        """
        # 默认配置
        config = {
            'retention.ms': str(TOPIC_CONFIG.get('retention_ms', 604800000)),
            'retention.bytes': str(TOPIC_CONFIG.get('retention_bytes', -1)),
        }
        if topic_config:
            config.update(topic_config)

        new_topic = NewTopic(
            name=topic_name,
            num_partitions=num_partitions,
            replication_factor=replication_factor,
            topic_configs=config,
        )

        try:
            self.admin_client.create_topics([new_topic])
            logger.info(f"Topic '{topic_name}' created successfully")
            return True
        except TopicAlreadyExistsError:
            logger.warning(f"Topic '{topic_name}' already exists")
            return False
        except Exception as e:
            logger.error(f"Failed to create topic '{topic_name}': {e}")
            raise

    def delete_topic(self, topic_name: str) -> bool:
        """
        删除 Topic

        Args:
            topic_name: Topic 名称

        Returns:
            是否删除成功
        """
        try:
            self.admin_client.delete_topics([topic_name])
            logger.info(f"Topic '{topic_name}' deleted successfully")
            return True
        except UnknownTopicOrPartitionError:
            logger.warning(f"Topic '{topic_name}' does not exist")
            return False
        except Exception as e:
            logger.error(f"Failed to delete topic '{topic_name}': {e}")
            raise

    def list_topics(self) -> List[str]:
        """
        列出所有 Topic

        Returns:
            Topic 名称列表
        """
        try:
            topics = self.admin_client.list_topics()
            return topics
        except Exception as e:
            logger.error(f"Failed to list topics: {e}")
            raise

    def describe_topic(self, topic_name: str) -> dict:
        """
        获取 Topic 详细信息

        Args:
            topic_name: Topic 名称

        Returns:
            Topic 详细信息
        """
        try:
            topics_info = self.admin_client.describe_topics([topic_name])
            if topics_info:
                return topics_info[0]
            return {}
        except Exception as e:
            logger.error(f"Failed to describe topic '{topic_name}': {e}")
            raise

    def create_topics_batch(self, topics: List[dict]) -> Dict[str, bool]:
        """
        批量创建 Topic

        Args:
            topics: Topic 配置列表

        Returns:
            创建结果
        """
        results = {}
        for topic_config in topics:
            topic_name = topic_config['name']
            try:
                success = self.create_topic(
                    topic_name=topic_name,
                    num_partitions=topic_config.get('num_partitions', 3),
                    replication_factor=topic_config.get('replication_factor', 1),
                    topic_config=topic_config.get('config', {}),
                )
                results[topic_name] = success
            except Exception as e:
                results[topic_name] = False
                logger.error(f"Failed to create topic '{topic_name}': {e}")

        return results

    # ============================================================
    # Consumer Group 管理
    # ============================================================

    def list_consumer_groups(self) -> List[str]:
        """
        列出所有 Consumer Group

        Returns:
            Consumer Group ID 列表
        """
        try:
            groups = self.admin_client.list_consumer_groups()
            return [g[0] for g in groups]  # 返回 group_id
        except Exception as e:
            logger.error(f"Failed to list consumer groups: {e}")
            raise

    def describe_consumer_group(self, group_id: str) -> dict:
        """
        获取 Consumer Group 详细信息

        Args:
            group_id: Consumer Group ID

        Returns:
            Consumer Group 详细信息
        """
        try:
            groups = self.admin_client.describe_consumer_groups([group_id])
            if groups:
                return groups[0]
            return {}
        except Exception as e:
            logger.error(f"Failed to describe consumer group '{group_id}': {e}")
            raise

    def delete_consumer_group(self, group_id: str) -> bool:
        """
        删除 Consumer Group

        Args:
            group_id: Consumer Group ID

        Returns:
            是否删除成功
        """
        try:
            self.admin_client.delete_consumer_groups([group_id])
            logger.info(f"Consumer group '{group_id}' deleted successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to delete consumer group '{group_id}': {e}")
            raise

    def list_consumer_group_offsets(self, group_id: str) -> dict:
        """
        获取 Consumer Group 的偏移量信息

        Args:
            group_id: Consumer Group ID

        Returns:
            偏移量信息
        """
        try:
            from kafka.structs import TopicPartition
            offsets = self.admin_client.list_consumer_group_offsets(group_id)
            result = {}
            for tp, offset_meta in offsets.items():
                result[f"{tp.topic}:{tp.partition}"] = {
                    'offset': offset_meta.offset,
                    'metadata': offset_meta.metadata,
                }
            return result
        except Exception as e:
            logger.error(f"Failed to list consumer group offsets: {e}")
            raise

    # ============================================================
    # 配置管理
    # ============================================================

    def get_topic_config(self, topic_name: str) -> dict:
        """
        获取 Topic 配置

        Args:
            topic_name: Topic 名称

        Returns:
            Topic 配置
        """
        try:
            resource = ConfigResource(ConfigResourceType.TOPIC, topic_name)
            configs = self.admin_client.describe_configs([resource])
            return configs[resource]
        except Exception as e:
            logger.error(f"Failed to get topic config: {e}")
            raise

    def alter_topic_config(self, topic_name: str, config_updates: dict) -> bool:
        """
        修改 Topic 配置

        Args:
            topic_name: Topic 名称
            config_updates: 配置更新

        Returns:
            是否修改成功
        """
        try:
            resource = ConfigResource(ConfigResourceType.TOPIC, topic_name)
            resource.set_config_dict(config_updates)
            self.admin_client.alter_configs([resource])
            logger.info(f"Topic '{topic_name}' config updated: {config_updates}")
            return True
        except Exception as e:
            logger.error(f"Failed to alter topic config: {e}")
            raise

    # ============================================================
    # 集群信息
    # ============================================================

    def describe_cluster(self) -> dict:
        """
        获取集群信息

        Returns:
            集群信息
        """
        try:
            cluster_info = {
                'brokers': [],
                'controller_id': None,
            }

            # 获取 Broker 列表
            brokers = self.admin_client.describe_cluster()
            for broker in brokers:
                # 兼容不同版本的 kafka-python
                if hasattr(broker, 'nodeId'):
                    cluster_info['brokers'].append({
                        'id': broker.nodeId,
                        'host': broker.host,
                        'port': broker.port,
                    })
                else:
                    # 新版本返回字符串
                    cluster_info['brokers'].append({
                        'id': str(broker),
                        'host': 'localhost',
                        'port': 9092,
                    })

            return cluster_info
        except Exception as e:
            logger.error(f"Failed to describe cluster: {e}")
            raise

    def close(self):
        """关闭管理客户端"""
        if self.admin_client:
            self.admin_client.close()
            logger.info("Admin client closed")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# ============================================================
# 使用示例
# ============================================================

def example_topic_management():
    """Topic 管理示例"""
    print("\n=== Topic 管理示例 ===")

    with KafkaAdminTools() as admin:
        # 列出所有 Topic
        print("Current topics:", admin.list_topics())

        # 创建新 Topic
        admin.create_topic(
            topic_name='test-topic',
            num_partitions=3,
            replication_factor=1,
        )

        # 获取 Topic 详细信息
        topic_info = admin.describe_topic('test-topic')
        print(f"Topic info: {json.dumps(topic_info, indent=2, default=str)}")

        # 获取 Topic 配置
        config = admin.get_topic_config('test-topic')
        print(f"Topic config: {config}")

        # 修改 Topic 配置
        admin.alter_topic_config('test-topic', {
            'retention.ms': '86400000'  # 1天
        })

        # 删除 Topic
        # admin.delete_topic('test-topic')


def example_consumer_group_management():
    """Consumer Group 管理示例"""
    print("\n=== Consumer Group 管理示例 ===")

    with KafkaAdminTools() as admin:
        # 列出所有 Consumer Group
        print("Consumer groups:", admin.list_consumer_groups())

        # 获取 Consumer Group 详细信息
        group_info = admin.describe_consumer_group('my-consumer-group')
        print(f"Group info: {json.dumps(group_info, indent=2, default=str)}")

        # 获取 Consumer Group 偏移量
        offsets = admin.list_consumer_group_offsets('my-consumer-group')
        print(f"Offsets: {offsets}")


def example_cluster_info():
    """集群信息示例"""
    print("\n=== 集群信息示例 ===")

    with KafkaAdminTools() as admin:
        cluster_info = admin.describe_cluster()
        print(f"Cluster info: {json.dumps(cluster_info, indent=2)}")


if __name__ == '__main__':
    example_topic_management()
    # example_consumer_group_management()
    # example_cluster_info()
