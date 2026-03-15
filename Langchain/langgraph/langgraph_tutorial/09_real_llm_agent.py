"""
LangGraph 综合示例: 完整的 AI 代理
===================================

本示例展示如何使用 LangGraph 构建一个完整的 AI 代理，
包括工具调用、记忆、人工干预等功能。

注意：运行此示例需要设置 OPENAI_API_KEY 环境变量
或者修改代码使用其他 LLM 提供商。
"""

from langgraph.graph import StateGraph, START, END, MessagesState
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt, Command
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from typing import Literal
import os


# ============================================
# 1. 定义工具
# ============================================

@tool
def search_web(query: str) -> str:
    """
    在网上搜索信息

    Args:
        query: 搜索关键词

    Returns:
        搜索结果
    """
    # 模拟搜索结果
    mock_results = {
        "天气": "今天北京晴天，温度15-22°C",
        "新闻": "最新头条：科技行业持续发展",
        "股票": "上证指数今日收盘3050点",
    }

    for key, value in mock_results.items():
        if key in query:
            return f"搜索结果: {value}"

    return f"未找到关于 '{query}' 的相关信息"


@tool
def create_todo(task: str, priority: Literal["high", "medium", "low"] = "medium") -> str:
    """
    创建一个待办事项

    Args:
        task: 任务描述
        priority: 优先级 (high/medium/low)

    Returns:
        创建结果
    """
    todo_id = f"TODO-{hash(task) % 10000:04d}"
    return f"已创建待办事项 [{todo_id}]: {task} (优先级: {priority})"


@tool
def send_email(to: str, subject: str, body: str) -> str:
    """
    发送电子邮件

    Args:
        to: 收件人邮箱
        subject: 邮件主题
        body: 邮件正文

    Returns:
        发送结果
    """
    # 需要人工确认
    return f"邮件已发送至 {to}\n主题: {subject}\n正文: {body[:50]}..."


@tool
def get_user_info(user_id: str) -> str:
    """
    获取用户信息

    Args:
        user_id: 用户ID

    Returns:
        用户信息
    """
    # 模拟用户数据
    users = {
        "001": {"name": "张三", "role": "管理员", "email": "zhangsan@example.com"},
        "002": {"name": "李四", "role": "用户", "email": "lisi@example.com"},
    }

    if user_id in users:
        user = users[user_id]
        return f"用户信息: 姓名={user['name']}, 角色={user['role']}, 邮箱={user['email']}"

    return f"未找到用户 {user_id}"


# ============================================
# 2. 模拟 LLM（用于演示）
# ============================================

class MockChatModel:
    """模拟聊天模型"""

    def __init__(self, tools=None):
        self.tools = {t.name: t for t in (tools or [])}
        self.tools_list = tools or []

    def bind_tools(self, tools):
        """绑定工具"""
        return MockChatModel(tools)

    def invoke(self, messages):
        """处理消息"""
        # 获取最后一条用户消息
        last_user_msg = None
        for msg in reversed(messages):
            if isinstance(msg, HumanMessage):
                last_user_msg = msg.content.lower()
                break

        if not last_user_msg:
            return AIMessage(content="您好！有什么我可以帮助您的吗？")

        # 根据内容决定响应
        if "搜索" in last_user_msg:
            query = last_user_msg.replace("搜索", "").strip()
            return AIMessage(
                content="",
                tool_calls=[{
                    "name": "search_web",
                    "args": {"query": query or "默认搜索"},
                    "id": "call_search"
                }]
            )

        elif "待办" in last_user_msg or "todo" in last_user_msg:
            task = last_user_msg.replace("待办", "").replace("创建", "").strip()
            return AIMessage(
                content="",
                tool_calls=[{
                    "name": "create_todo",
                    "args": {"task": task or "新任务", "priority": "medium"},
                    "id": "call_todo"
                }]
            )

        elif "邮件" in last_user_msg or "email" in last_user_msg:
            return AIMessage(
                content="",
                tool_calls=[{
                    "name": "send_email",
                    "args": {
                        "to": "user@example.com",
                        "subject": "测试邮件",
                        "body": "这是一封测试邮件"
                    },
                    "id": "call_email"
                }]
            )

        elif "用户" in last_user_msg:
            return AIMessage(
                content="",
                tool_calls=[{
                    "name": "get_user_info",
                    "args": {"user_id": "001"},
                    "id": "call_user"
                }]
            )

        # 检查是否有工具结果需要处理
        for msg in reversed(messages):
            if hasattr(msg, 'tool_calls') and msg.tool_calls:
                # 有工具调用，生成响应
                tool_name = msg.tool_calls[0]["name"]
                return AIMessage(content=f"我已经为您处理了 {tool_name} 请求。还有其他需要帮助的吗？")

        # 默认响应
        return AIMessage(content="我可以帮您搜索信息、创建待办事项、发送邮件或查询用户信息。请问您需要什么帮助？")


# ============================================
# 3. 构建代理图
# ============================================

def build_agent_graph():
    """构建完整的代理图"""
    # 创建工具
    tools = [search_web, create_todo, send_email, get_user_info]
    tool_node = ToolNode(tools)

    # 创建模型（使用模拟模型）
    model = MockChatModel(tools)

    # 定义代理节点
    def agent_node(state: MessagesState) -> dict:
        # 添加系统消息
        messages = state["messages"]
        if not any(isinstance(m, SystemMessage) for m in messages):
            messages = [SystemMessage(content="你是一个有用的AI助手，可以使用工具帮助用户完成任务。")] + list(messages)

        response = model.invoke(messages)
        return {"messages": [response]}

    # 构建图
    builder = StateGraph(MessagesState)

    builder.add_node("agent", agent_node)
    builder.add_node("tools", tool_node)

    builder.add_edge(START, "agent")

    # 使用预建的条件路由
    builder.add_conditional_edges(
        "agent",
        tools_condition,
        {
            "tools": "tools",
            END: END
        }
    )

    builder.add_edge("tools", "agent")

    # 添加持久化
    memory = MemorySaver()
    return builder.compile(checkpointer=memory)


# ============================================
# 4. 带人工审批的代理
# ============================================

def build_agent_with_approval():
    """构建带人工审批的代理"""
    tools = [search_web, create_todo, send_email, get_user_info]
    tool_node = ToolNode(tools)
    model = MockChatModel(tools)

    def agent_node(state: MessagesState) -> dict:
        messages = state["messages"]
        response = model.invoke(messages)
        return {"messages": [response]}

    def approval_node(state: MessagesState) -> dict:
        """人工审批节点"""
        # 获取最后一个工具调用
        last_ai_msg = None
        for msg in reversed(state["messages"]):
            if isinstance(msg, AIMessage) and hasattr(msg, 'tool_calls') and msg.tool_calls:
                last_ai_msg = msg
                break

        if last_ai_msg:
            tool_calls = last_ai_msg.tool_calls
            tool_info = "\n".join([
                f"  - {tc['name']}: {tc['args']}"
                for tc in tool_calls
            ])

            # 请求人工确认
            decision = interrupt(
                f"以下工具调用需要审批:\n{tool_info}\n\n"
                f"请输入 'approve' 批准 或 'reject' 拒绝:"
            )

            if decision.lower() == "approve":
                return {"messages": [AIMessage(content="[已批准执行工具]")]}

        return {"messages": [AIMessage(content="[操作已取消]")]}

    def should_approve(state: MessagesState) -> str:
        """检查是否需要审批"""
        for msg in reversed(state["messages"]):
            if isinstance(msg, AIMessage) and hasattr(msg, 'tool_calls') and msg.tool_calls:
                # 检查是否是敏感操作
                for tc in msg.tool_calls:
                    if tc["name"] in ["send_email", "create_todo"]:
                        return "need_approval"
        return "direct"

    builder = StateGraph(MessagesState)

    builder.add_node("agent", agent_node)
    builder.add_node("tools", tool_node)
    builder.add_node("approval", approval_node)

    builder.add_edge(START, "agent")

    builder.add_conditional_edges(
        "agent",
        should_approve,
        {
            "need_approval": "approval",
            "direct": "tools"
        }
    )

    builder.add_edge("approval", "tools")
    builder.add_conditional_edges("tools", tools_condition, {"tools": "agent", END: END})
    builder.add_edge("agent", END)

    memory = MemorySaver()
    return builder.compile(
        checkpointer=memory,
        interrupt_before=["approval"]  # 在审批节点前中断
    )


# ============================================
# 5. 演示
# ============================================

def demo_basic_agent():
    """演示基础代理"""
    print("=" * 60)
    print("基础 AI 代理演示")
    print("=" * 60)

    agent = build_agent_graph()
    config = {"configurable": {"thread_id": "demo-1"}}

    # 测试不同场景
    test_cases = [
        "帮我搜索天气信息",
        "创建一个待办事项：完成项目报告",
        "查询用户001的信息",
    ]

    for user_input in test_cases:
        print(f"\n用户: {user_input}")
        result = agent.invoke(
            {"messages": [HumanMessage(content=user_input)]},
            config
        )

        # 打印响应
        for msg in reversed(result["messages"]):
            if isinstance(msg, AIMessage) and msg.content:
                print(f"AI: {msg.content}")
                break
            elif hasattr(msg, 'content') and msg.content and not isinstance(msg, HumanMessage):
                print(f"工具结果: {msg.content}")
                break


def demo_multi_turn_conversation():
    """演示多轮对话"""
    print("\n" + "=" * 60)
    print("多轮对话演示")
    print("=" * 60)

    agent = build_agent_graph()
    config = {"configurable": {"thread_id": "multi-turn"}}

    conversations = [
        "你好",
        "帮我搜索新闻",
        "再创建一个待办：开会",
        "查询用户002",
    ]

    for user_input in conversations:
        print(f"\n用户: {user_input}")
        result = agent.invoke(
            {"messages": [HumanMessage(content=user_input)]},
            config
        )

        # 只打印最后的 AI 响应
        for msg in reversed(result["messages"]):
            if isinstance(msg, AIMessage) and msg.content:
                print(f"AI: {msg.content}")
                break


def demo_with_approval():
    """演示带审批的代理"""
    print("\n" + "=" * 60)
    print("带人工审批的代理演示")
    print("=" * 60)

    agent = build_agent_with_approval()
    config = {"configurable": {"thread_id": "approval-demo"}}

    # 触发需要审批的操作
    print("\n用户: 发送一封测试邮件")
    events = agent.invoke(
        {"messages": [HumanMessage(content="发送一封测试邮件")]},
        config
    )

    # 检查是否需要审批
    state = agent.get_state(config)
    if state.next and "approval" in state.next:
        print("\n[系统] 需要人工审批...")
        print("[系统] 模拟审批通过")

        # 恢复执行
        command = Command(resume="approve")
        result = agent.invoke(command, config)

        for msg in result["messages"]:
            if isinstance(msg, AIMessage) and msg.content:
                print(f"AI: {msg.content}")


# ============================================
# 6. 使用真实 LLM 的示例代码
# ============================================

def real_llm_example():
    """使用真实 LLM 的示例代码"""
    print("\n" + "=" * 60)
    print("使用真实 LLM 的示例代码")
    print("=" * 60)

    code = '''
# 使用 OpenAI 的示例

from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, MessagesState
from langgraph.prebuilt import ToolNode, tools_condition

# 1. 创建模型
model = ChatOpenAI(model="gpt-4", temperature=0)

# 2. 定义工具
@tool
def my_tool(query: str) -> str:
    """工具描述"""
    return "结果"

tools = [my_tool]

# 3. 绑定工具到模型
model_with_tools = model.bind_tools(tools)

# 4. 定义代理节点
def agent_node(state: MessagesState):
    response = model_with_tools.invoke(state["messages"])
    return {"messages": [response]}

# 5. 构建图
builder = StateGraph(MessagesState)
builder.add_node("agent", agent_node)
builder.add_node("tools", ToolNode(tools))

builder.add_edge(START, "agent")
builder.add_conditional_edges("agent", tools_condition)
builder.add_edge("tools", "agent")

agent = builder.compile()

# 6. 使用
result = agent.invoke({"messages": [HumanMessage(content="你好")]})
'''

    print(code)


# ============================================
# 主程序
# ============================================

def main():
    print("LangGraph 完整 AI 代理示例\n")

    demo_basic_agent()
    demo_multi_turn_conversation()
    demo_with_approval()
    real_llm_example()

    print("\n" + "=" * 60)
    print("教程完成！")
    print("=" * 60)
    print("""
学习总结:

1. 基础概念:
   - State: 状态定义
   - Node: 节点函数
   - Edge: 边和条件边
   - Graph: 图的构建和编译

2. 高级特性:
   - 循环: 通过条件边实现
   - 持久化: Checkpointer
   - 人工干预: interrupt_before/after, interrupt()
   - 子图: 模块化设计

3. 预建组件:
   - ToolNode: 工具执行
   - tools_condition: 条件路由
   - MessagesState: 消息状态
   - create_react_agent: 快速创建代理

4. 最佳实践:
   - 使用类型注解
   - 合理设计状态结构
   - 使用 checkpointer 保存状态
   - 模块化复杂逻辑

下一步:
- 尝试使用真实 LLM
- 添加更多工具
- 实现复杂的业务流程
- 集成到实际项目中

参考资源:
- LangGraph 文档: https://langchain-ai.github.io/langgraph/
- LangChain 文档: https://python.langchain.com/
""")


if __name__ == "__main__":
    main()
