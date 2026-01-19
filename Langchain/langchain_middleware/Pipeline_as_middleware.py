from langchain_core.runnables import RunnableLambda
from langchain_core.prompts import ChatPromptTemplate
from langchain_community.chat_models.tongyi import ChatTongyi
import os

# 设置阿里云百炼 API Key
os.environ["DASHSCOPE_API_KEY"] = "sk-WwCuZHoVGF"

# 1、定义一个简单的中间件函数
def logging_middleware(x):
    print(f"[Middleware Log] Input received:{x}")
    return x

def security_middleware(x):
    if "敏感词" in x["topic"]:
        raise ValueError("触发安全拦截：包含敏感词")
    return x

# 2. 核心组件
prompt = ChatPromptTemplate.from_template("讲一个关于 {topic} 的笑话")
model = ChatTongyi()

# 3. 组装：Middleware被显示的编排在流程中
#流程：Input -> Logging -> Security Check -> Prompt ->Model
chain = (
    RunnableLambda(logging_middleware)
    | RunnableLambda(security_middleware)
    | prompt
    | model
)

result = chain.invoke({"topic":"AI"})
print(f"[Final Output] {result}")