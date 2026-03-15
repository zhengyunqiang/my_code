"""
LangGraph 基础教程 06: 工具调用 (Tool Calling)
==============================================

本示例演示如何在 LangGraph 中使用工具：
1. 定义工具
2. 使用 ToolNode
3. 绑定工具到 LLM
4. 工具调用循环

核心概念：
- @tool 装饰器：定义工具
- ToolNode：预建的节点，用于执行工具
- bind_tools()：将工具绑定到 LLM
- 工具调用循环：LLM 决定调用工具 -> 执行工具 -> 返回结果

注意：本示例需要安装 langchain 和相关依赖
"""

from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver
from typing import TypedDict, Annotated
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
import operator
import json


# ============================================
# 1. 定义工具
# ============================================

@tool
def get_weather(city: str) -> str:
    """
    获取指定城市的天气信息

    Args:
        city: 城市名称

    Returns:
        天气信息字符串
    """
    # 模拟天气数据
    weather_data = {
        "北京": "晴天，温度 15°C，空气质量良好",
        "上海": "多云，温度 18°C，有轻微雾霾",
        "深圳": "小雨，温度 22°C，湿度较高",
        "成都": "阴天，温度 12°C，适合室内活动"
    }
    return weather_data.get(city, f"未找到 {city} 的天气信息")


@tool
def calculate(expression: str) -> str:
    """
    计算数学表达式

    Args:
        expression: 数学表达式，如 "2 + 3 * 4"

    Returns:
        计算结果
    """
    try:
        # 安全地计算表达式（仅用于演示，生产环境需要更安全的方式）
        allowed_chars = set("0123456789+-*/.() ")
        if not all(c in allowed_chars for c in expression):
            return "错误：表达式包含不允许的字符"

        result = eval(expression)
        return f"计算结果: {expression} = {result}"
    except Exception as e:
        return f"计算错误: {str(e)}"


@tool
def search_database(query: str) -> str:
    """
    在数据库中搜索信息

    Args:
        query: 搜索查询

    Returns:
        搜索结果
    """
    # 模拟数据库
    database = {
        "产品": ["产品A - ¥100", "产品B - ¥200", "产品C - ¥300"],
        "订单": ["订单 #001 - 已发货", "订单 #002 - 处理中"],
        "用户": ["用户张三", "用户李四"]
    }

    results = []
    for key, values in database.items():
        if key in query:
            results.extend(values)

    if results:
        return f"找到 {len(results)} 条结果: " + ", ".join(results)
    return "未找到相关结果"


# ============================================
# 2. 定义状态（使用消息列表）
# ============================================

class ToolAgentState(TypedDict):
    """工具代理状态"""
    messages: Annotated[list, operator.add]


# ============================================
# 3. 模拟 LLM 响应（无真实 LLM 的演示）
# ============================================

class MockLLM:
    """模拟 LLM，用于演示工具调用流程"""

    def __init__(self, tools):
        self.tools = {t.name: t for t in tools}
        self.tools_list = tools

    def bind_tools(self, tools):
        """绑定工具"""
        return self

    def invoke(self, messages):
        """模拟 LLM 响应"""
        last_message = messages[-1] if messages else None

        if isinstance(last_message, HumanMessage):
            content = last_message.content.lower()

            # 根据用户输入决定调用哪个工具
            if "天气" in content or "weather" in content:
                # 提取城市名
                for city in ["北京", "上海", "深圳", "成都"]:
                    if city in content:
                        return AIMessage(
                            content="",
                            tool_calls=[{
                                "name": "get_weather",
                                "args": {"city": city},
                                "id": "call_1"
                            }]
                        )

            elif "计算" in content or "+" in content or "*" in content:
                # 提取表达式
                import re
                expr = re.search(r'[\d+\-*/().\s]+', content)
                if expr:
                    return AIMessage(
                        content="",
                        tool_calls=[{
                            "name": "calculate",
                            "args": {"expression": expr.group().strip()},
                            "id": "call_2"
                        }]
                    )

            elif "搜索" in content or "查询" in content:
                return AIMessage(
                    content="",
                    tool_calls=[{
                        "name": "search_database",
                        "args": {"query": "产品"},
                        "id": "call_3"
                    }]
                )

        # 默认返回文本响应
        return AIMessage(content="我可以帮您查询天气、进行计算或搜索数据库。请问您需要什么帮助？")


# ============================================
# 4. 构建工具调用图
# ============================================

def build_tool_graph():
    """构建工具调用图"""
    # 创建工具列表
    tools = [get_weather, calculate, search_database]

    # 创建 ToolNode（预建节点，自动执行工具）
    tool_node = ToolNode(tools)

    # 创建模拟 LLM
    model = MockLLM(tools)

    # 定义代理节点
    def agent_node(state: ToolAgentState) -> dict:
        """代理节点 - 调用 LLM"""
        response = model.invoke(state["messages"])
        return {"messages": [response]}

    # 定义路由函数
    def should_continue(state: ToolAgentState) -> str:
        """决定是否继续调用工具"""
        last_message = state["messages"][-1]

        # 如果有 tool_calls，继续执行工具
        if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
            return "tools"

        return "end"

    # 构建图
    builder = StateGraph(ToolAgentState)

    builder.add_node("agent", agent_node)
    builder.add_node("tools", tool_node)

    builder.add_edge(START, "agent")

    builder.add_conditional_edges(
        "agent",
        should_continue,
        {
            "tools": "tools",
            "end": END
        }
    )

    # 工具执行后返回代理
    builder.add_edge("tools", "agent")

    return builder.compile()


# ============================================
# 5. 演示工具调用
# ============================================

def demo_tool_calling():
    """演示工具调用"""
    print("=" * 60)
    print("工具调用演示")
    print("=" * 60)

    graph = build_tool_graph()

    # 测试1：天气查询
    print("\n--- 测试1: 天气查询 ---")
    result = graph.invoke({
        "messages": [HumanMessage(content="北京今天天气怎么样？")]
    })
    print(f"对话历史:")
    for msg in result["messages"]:
        if isinstance(msg, HumanMessage):
            print(f"  用户: {msg.content}")
        elif isinstance(msg, AIMessage):
            if msg.content:
                print(f"  AI: {msg.content}")
            if hasattr(msg, 'tool_calls') and msg.tool_calls:
                print(f"  AI 调用工具: {msg.tool_calls}")
        elif isinstance(msg, ToolMessage):
            print(f"  工具结果: {msg.content}")

    # 测试2：计算
    print("\n--- 测试2: 数学计算 ---")
    result = graph.invoke({
        "messages": [HumanMessage(content="帮我计算 123 + 456")]
    })
    for msg in result["messages"]:
        if isinstance(msg, ToolMessage):
            print(f"  计算结果: {msg.content}")

    # 测试3：搜索
    print("\n--- 测试3: 数据库搜索 ---")
    result = graph.invoke({
        "messages": [HumanMessage(content="搜索产品信息")]
    })
    for msg in result["messages"]:
        if isinstance(msg, ToolMessage):
            print(f"  搜索结果: {msg.content}")


# ============================================
# 6. 手动实现工具节点（理解原理）
# ============================================

def build_manual_tool_graph():
    """手动实现工具调用图（理解原理）"""
    tools = [get_weather, calculate, search_database]
    tools_map = {t.name: t for t in tools}
    model = MockLLM(tools)

    def agent_node(state: ToolAgentState) -> dict:
        """代理节点"""
        response = model.invoke(state["messages"])
        return {"messages": [response]}

    def tool_executor_node(state: ToolAgentState) -> dict:
        """工具执行节点 - 手动实现"""
        last_message = state["messages"][-1]
        tool_calls = last_message.tool_calls

        tool_messages = []
        for tool_call in tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            tool_id = tool_call["id"]

            # 执行工具
            tool = tools_map[tool_name]
            result = tool.invoke(tool_args)

            # 创建 ToolMessage
            tool_messages.append(ToolMessage(
                content=result,
                tool_call_id=tool_id
            ))

        return {"messages": tool_messages}

    def should_continue(state: ToolAgentState) -> str:
        last_message = state["messages"][-1]
        if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
            return "tools"
        return "end"

    builder = StateGraph(ToolAgentState)

    builder.add_node("agent", agent_node)
    builder.add_node("tool_executor", tool_executor_node)

    builder.add_edge(START, "agent")
    builder.add_conditional_edges("agent", should_continue, {"tools": "tool_executor", "end": END})
    builder.add_edge("tool_executor", "agent")

    return builder.compile()


def demo_manual_tool_graph():
    """演示手动实现的工具图"""
    print("\n" + "=" * 60)
    print("手动实现工具调用演示")
    print("=" * 60)

    graph = build_manual_tool_graph()

    print("\n--- 测试天气查询 ---")
    for event in graph.stream({
        "messages": [HumanMessage(content="上海天气")]
    }):
        node_name = list(event.keys())[0]
        print(f"执行节点: {node_name}")


# ============================================
# 7. 带状态的多次工具调用
# ============================================

def demo_multi_turn_tools():
    """演示多次工具调用"""
    print("\n" + "=" * 60)
    print("多次工具调用演示")
    print("=" * 60)

    graph = build_tool_graph()
    checkpointer = MemorySaver()

    # 重新编译带 checkpointer 的图
    tools = [get_weather, calculate, search_database]
    tool_node = ToolNode(tools)
    model = MockLLM(tools)

    def agent_node(state: ToolAgentState) -> dict:
        response = model.invoke(state["messages"])
        return {"messages": [response]}

    def should_continue(state: ToolAgentState) -> str:
        last_message = state["messages"][-1]
        if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
            return "tools"
        return "end"

    builder = StateGraph(ToolAgentState)
    builder.add_node("agent", agent_node)
    builder.add_node("tools", tool_node)
    builder.add_edge(START, "agent")
    builder.add_conditional_edges("agent", should_continue, {"tools": "tools", "end": END})
    builder.add_edge("tools", "agent")

    graph = builder.compile(checkpointer=checkpointer)

    config = {"configurable": {"thread_id": "multi-turn"}}

    # 第一轮对话
    print("\n--- 第一轮 ---")
    result = graph.invoke({
        "messages": [HumanMessage(content="深圳天气")]
    }, config)
    for msg in result["messages"]:
        if isinstance(msg, ToolMessage):
            print(f"天气结果: {msg.content}")


# ============================================
# 主程序
# ============================================

def main():
    print("LangGraph 工具调用教程\n")

    # 显示可用工具
    print("可用工具:")
    tools = [get_weather, calculate, search_database]
    for t in tools:
        print(f"  - {t.name}: {t.description}")
    print()

    demo_tool_calling()
    demo_manual_tool_graph()
    demo_multi_turn_tools()


if __name__ == "__main__":
    main()


# ============================================
# 学习要点总结
# ============================================
"""
1. @tool 装饰器用于定义工具
2. ToolNode 是预建节点，自动执行工具调用
3. 工具调用流程：
   - LLM 决定调用工具
   - 执行工具
   - 返回结果给 LLM
   - LLM 生成最终响应

4. 消息类型：
   - HumanMessage: 用户消息
   - AIMessage: AI 响应（可能包含 tool_calls）
   - ToolMessage: 工具执行结果

5. 可以手动实现 ToolNode 来理解原理

使用真实 LLM 的代码示例：

```python
from langchain_openai import ChatOpenAI

model = ChatOpenAI(model="gpt-4")
model_with_tools = model.bind_tools(tools)

def agent_node(state):
    response = model_with_tools.invoke(state["messages"])
    return {"messages": [response]}
```

练习：
- 添加更多自定义工具
- 使用真实的 LLM（如 OpenAI）
- 实现一个复杂的工具调用链
"""
