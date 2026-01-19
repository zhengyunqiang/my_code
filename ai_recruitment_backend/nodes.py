import os
from dotenv import load_dotenv
from langchain_community.chat_models import ChatTongyi
from langchain_core.messages import AIMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from schemas import RequirementDiagnosis,JobDescription

#加载环境变量
load_dotenv()

# 初始化Qwen_MAX 模型
llm = ChatTongyi(
    model = "qwen-max",
    temperature = 0.01,
    api_key = os.getenv("DASHSCOPE_API_KEY")
)

# 模拟 RAG 检索服务
def mock_vector_search(query:str) -> str:
    """
    模拟检索业务知识库
    :param query:
    :return:
    """
    if any(k in query for k in ["物联网","IOT","移动","基地"]):
        return """
        【知识库片段 - 移动物联网基地项目】
        1. 业务规模：接入设备数超 5000 万，日均消息吞吐量 10 亿条，高并发场景。
        2. 核心痛点：上一任员工因无法处理 Netty TCP 粘包/拆包及内存泄漏问题离职；
           目前系统架构正处于从单体向 Spring Cloud Alibaba 微服务迁移阶段。
        3. 技术栈要求：Java 17, Netty (必须精通), MQTT 协议, Kafka, Docker, K8s。
        4. 硬性门槛：统招本科及以上（双证齐全），英语四级。
        5. 加班情况：季度末有版本发布压力，需接受大小周。
        """
    return "【知识库】通用Java后端开发标准要求，无特殊项目背景。"