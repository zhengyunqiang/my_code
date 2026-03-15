"""
LangGraph 基础教程 08: 预建组件 (Prebuilt Components)
=====================================================

本示例演示 LangGraph 的预建组件：
1. ToolNode - 工具执行节点
2. tools_condition - 工具调用条件路由
3. create_react_agent - 创建 ReAct 代理
4. MessageGraph - 消息图

预建组件可以快速构建常见的代理模式，减少样板代码。

注意：部分功能需要 langchain 相关依赖
"""

from langgraph.graph import StateGraph, START, END, MessagesState
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.checkpoint.memory import MemorySaver
from typing import TypedDict, Annotated, Sequence
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage
import operator


# ============================================
# 1. ToolNode - 预建的工具执行节点
# ============================================

@tool
def add_numbers(a: int, b: int) -> int:
    """Add two numbers together."""
    return a + b


@tool
def multiply_numbers(a: int, b: int) -> int:
    """Multiply two numbers together."""
    return a * b


@tool
def get_current_time() -> str:
    """Get the current time."""
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def demo_tool_node():
    """演示 ToolNode"""
    print("=" * 60)
    print("ToolNode 演示")
    print("=" * 60)

    # 创建工具列表
    tools = [add_numbers, multiply_numbers, get_current_time]

    # 创建 ToolNode
    tool_node = ToolNode(tools)

    # 直接使用 ToolNode
    print("\n--- 直接使用 ToolNode ---")

    # 模拟 AI 的工具调用
    ai_message = AIMessage(
        content="",
        tool_calls=[
            {"name": "add_numbers", "args": {"a": 5, "b": 3}, "id": "call_1"}
        ]
    )

    # ToolNode 期望的消息格式
    result = tool_node.invoke({"messages": [ai_message]})
    print(f"工具执行结果: {result['messages'][0].content}")

    # 多个工具调用
    print("\n--- 多个工具调用 ---")
    ai_message = AIMessage(
        content="",
        tool_calls=[
            {"name": "add_numbers", "args": {"a": 10, "b": 20}, "id": "call_2"},
            {"name": "multiply_numbers", "args": {"a": 5, "b": 6}, "id": "call_3"},
            {"name": "get_current_time", "args": {}, "id": "call_4"}
        ]
    )

    result = tool_node.invoke({"messages": [ai_message]})
    for msg in result["messages"]:
        print(f"  {msg.content}")


# ============================================
# 2. tools_condition - 预建的条件路由
# ============================================

def demo_tools_condition():
    """演示 tools_condition"""
    print("\n" + "=" * 60)
    print("tools_condition 演示")
    print("=" * 60)

    # tools_condition 是一个预建的条件函数
    # 检查最后一条消息是否有 tool_calls

    # 有工具调用的消息
    msg_with_tools = AIMessage(
        content="",
        tool_calls=[{"name": "some_tool", "args": {}, "id": "1"}]
    )
    state_with_tools = {"messages": [msg_with_tools]}
    result = tools_condition(state_with_tools)
    print(f"有工具调用: tools_condition 返回 '{result}'")

    # 没有工具调用的消息
    msg_without_tools = AIMessage(content="这是一个普通回复")
    state_without_tools = {"messages": [msg_without_tools]}
    result = tools_condition(state_without_tools)
    print(f"无工具调用: tools_condition 返回 '{result}'")


# ============================================
# 3. 构建完整的工具调用代理
# ============================================

class AgentState(TypedDict):
    """代理状态"""
    messages: Annotated[Sequence[BaseMessage], operator.add]


class MockChatModel:
    """模拟聊天模型"""

    def __init__(self, tools=None):
        self.tools = {t.name: t for t in (tools or [])}

    def bind_tools(self, tools):
        return MockChatModel(tools)

    def invoke(self, messages):
        last_message = messages[-1] if messages else None

        if isinstance(last_message, HumanMessage):
            content = last_message.content.lower()

            if "加" in content or "+" in content:
                import re
                numbers = re.findall(r'\d+', content)
                if len(numbers) >= 2:
                    return AIMessage(
                        content="",
                        tool_calls=[{
                            "name": "add_numbers",
                            "args": {"a": int(numbers[0]), "b": int(numbers[1])},
                            "id": "call_add"
                        }]
                    )

            elif "乘" in content or "*" in content or "x" in content:
                import re
                numbers = re.findall(r'\d+', content)
                if len(numbers) >= 2:
                    return AIMessage(
                        content="",
                        tool_calls=[{
                            "name": "multiply_numbers",
                            "args": {"a": int(numbers[0]), "b": int(numbers[1])},
                            "id": "call_mul"
                        }]
                    )

            elif "时间" in content or "time" in content:
                return AIMessage(
                    content="",
                    tool_calls=[{
                        "name": "get_current_time",
                        "args": {},
                        "id": "call_time"
                    }]
                )

        # 默认响应
        return AIMessage(content="我可以帮您进行加法、乘法计算或查询当前时间。")


def build_tool_agent():
    """构建工具调用代理"""
    tools = [add_numbers, multiply_numbers, get_current_time]
    tool_node = ToolNode(tools)
    model = MockChatModel(tools)

    def agent_node(state: AgentState) -> dict:
        response = model.invoke(state["messages"])
        return {"messages": [response]}

    builder = StateGraph(AgentState)

    builder.add_node("agent", agent_node)
    builder.add_node("tools", tool_node)

    builder.add_edge(START, "agent")

    # 使用预建的 tools_condition
    builder.add_conditional_edges(
        "agent",
        tools_condition,  # 预建的条件函数
        {
            "tools": "tools",
            END: END
        }
    )

    builder.add_edge("tools", "agent")

    return builder.compile()


def demo_tool_agent():
    """演示工具调用代理"""
    print("\n" + "=" * 60)
    print("完整工具调用代理演示")
    print("=" * 60)

    graph = build_tool_agent()

    # 测试加法
    print("\n--- 测试加法 ---")
    result = graph.invoke({
        "messages": [HumanMessage(content="帮我计算 15 + 27")]
    })
    for msg in result["messages"]:
        if hasattr(msg, 'content') and msg.content:
            print(f"  {type(msg).__name__}: {msg.content}")

    # 测试乘法
    print("\n--- 测试乘法 ---")
    result = graph.invoke({
        "messages": [HumanMessage(content="计算 8 x 9")]
    })
    for msg in result["messages"]:
        if hasattr(msg, 'content') and msg.content:
            print(f"  {type(msg).__name__}: {msg.content}")


# ============================================
# 4. MessagesState - 预建的消息状态
# ============================================

def demo_messages_state():
    """演示 MessagesState"""
    print("\n" + "=" * 60)
    print("MessagesState 演示")
    print("=" * 60)

    # MessagesState 是预建的状态类型
    # messages: Annotated[list[AnyMessage], add_messages]

    # 直接使用 MessagesState 构建图
    def echo_node(state: MessagesState) -> dict:
        last_message = state["messages"][-1]
        response = AIMessage(content=f"Echo: {last_message.content}")
        return {"messages": [response]}

    builder = StateGraph(MessagesState)
    builder.add_node("echo", echo_node)
    builder.add_edge(START, "echo")
    builder.add_edge("echo", END)

    graph = builder.compile()

    result = graph.invoke({
        "messages": [HumanMessage(content="Hello!")]
    })
    print(f"消息历史:")
    for msg in result["messages"]:
        print(f"  {type(msg).__name__}: {msg.content}")


# ============================================
# 5. 带持久化的代理
# ============================================

def build_persistent_agent():
    """构建带持久化的代理"""
    tools = [add_numbers, multiply_numbers, get_current_time]
    tool_node = ToolNode(tools)
    model = MockChatModel(tools)

    def agent_node(state: AgentState) -> dict:
        response = model.invoke(state["messages"])
        return {"messages": [response]}

    builder = StateGraph(AgentState)

    builder.add_node("agent", agent_node)
    builder.add_node("tools", tool_node)

    builder.add_edge(START, "agent")
    builder.add_conditional_edges("agent", tools_condition, {"tools": "tools", END: END})
    builder.add_edge("tools", "agent")

    # 添加持久化
    memory = MemorySaver()
    return builder.compile(checkpointer=memory)


def demo_persistent_agent():
    """演示带持久化的代理"""
    print("\n" + "=" * 60)
    print("带持久化的代理演示")
    print("=" * 60)

    graph = build_persistent_agent()
    config = {"configurable": {"thread_id": "session-1"}}

    # 多轮对话
    conversations = [
        "帮我计算 10 + 20",
        "当前时间是多少",
    ]

    for user_input in conversations:
        print(f"\n用户: {user_input}")
        result = graph.invoke({
            "messages": [HumanMessage(content=user_input)]
        }, config)

        # 找到最后一条 AI 或 Tool 消息
        for msg in reversed(result["messages"]):
            if isinstance(msg, (AIMessage, type(None))):
                continue
            if hasattr(msg, 'content') and msg.content and not isinstance(msg, HumanMessage):
                print(f"系统: {msg.content}")
                break


# ============================================
# 6. 预建图模式总结
# ============================================

def demo_prebuilt_patterns():
    """演示预建模式总结"""
    print("\n" + "=" * 60)
    print("预建组件总结")
    print("=" * 60)

    print("""
LangGraph 预建组件:

1. ToolNode
   - 自动执行工具调用
   - 处理 ToolMessage 创建

2. tools_condition
   - 预建的条件路由函数
   - 检查是否有工具调用

3. MessagesState
   - 预建的消息状态类型
   - 自动处理消息追加

4. create_react_agent (需要 langchain)
   - 一行代码创建 ReAct 代理
   - 自动绑定工具和模型

使用预建组件的好处:
- 减少样板代码
- 遵循最佳实践
- 更容易维护
- 快速原型开发

真实 LLM 示例:
```python
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

model = ChatOpenAI(model="gpt-4")
tools = [add_numbers, multiply_numbers]

agent = create_react_agent(model, tools)
result = agent.invoke({"messages": [HumanMessage(content="计算 1+1")]})
```
""")


# ============================================
# 主程序
# ============================================

def main():
    demo_tool_node()
    demo_tools_condition()
    demo_tool_agent()
    demo_messages_state()
    demo_persistent_agent()
    demo_prebuilt_patterns()


if __name__ == "__main__":
    main()


# ============================================
# 学习要点总结
# ============================================
"""
1. ToolNode 自动执行工具，返回 ToolMessage
2. tools_condition 是预建的条件路由
3. MessagesState 是预建的消息状态
4. create_react_agent 可以快速创建代理

预建组件适用场景:
- 快速原型开发
- 标准 ReAct 代理
- 工具调用场景

何时自定义:
- 需要特殊的状态管理
- 复杂的代理逻辑
- 自定义路由规则

练习:
- 使用真实 LLM 测试
- 添加更多工具
- 实现带记忆的多轮对话
"""
