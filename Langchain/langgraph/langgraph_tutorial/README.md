# LangGraph 完整学习教程

本教程涵盖 LangGraph 的所有核心概念和高级特性，从基础到高级逐步深入。

## 目录结构

```
langgraph_tutorial/
├── 01_basic_graph.py          # 基础图结构
├── 02_conditional_edges.py    # 条件边
├── 03_loops.py                # 循环与迭代
├── 04_checkpointer.py         # 持久化与检查点
├── 05_human_in_the_loop.py    # 人工干预
├── 06_tools.py                # 工具调用
├── 07_subgraphs.py            # 子图与组合
├── 08_prebuilt.py             # 预建组件
├── 09_real_llm_agent.py       # 完整 AI 代理示例
└── README.md                  # 本文件
```

## 快速开始

### 安装依赖

```bash
pip install langgraph langchain-core
```

### 运行示例

```bash
# 运行基础示例
python 01_basic_graph.py

# 运行条件边示例
python 02_conditional_edges.py

# 依此类推...
```

## 教程内容

### 01. 基础图结构 (`01_basic_graph.py`)

学习 LangGraph 的核心概念：
- **State（状态）**: 在节点之间共享的数据结构
- **Node（节点）**: 执行操作的函数
- **Edge（边）**: 定义节点之间的流转
- **StateGraph**: 构建和编译图

```python
from langgraph.graph import StateGraph, START, END

class MyState(TypedDict):
    count: int

def my_node(state: MyState) -> dict:
    return {"count": state["count"] + 1}

builder = StateGraph(MyState)
builder.add_node("increment", my_node)
builder.add_edge(START, "increment")
builder.add_edge("increment", END)

graph = builder.compile()
result = graph.invoke({"count": 0})
```

### 02. 条件边 (`02_conditional_edges.py`)

学习如何使用条件边实现分支逻辑：
- 基于状态值决定下一步执行哪个节点
- 使用 `add_conditional_edges` 添加条件边
- 实现复杂的决策流程

```python
def route_by_value(state) -> str:
    if state["value"] < 50:
        return "low_path"
    return "high_path"

builder.add_conditional_edges(
    "node_a",
    route_by_value,
    {"low_path": "node_b", "high_path": "node_c"}
)
```

### 03. 循环与迭代 (`03_loops.py`)

学习如何在 LangGraph 中实现循环：
- 使用条件边创建循环
- 状态驱动的迭代
- 实现重试机制

```python
def should_continue(state) -> str:
    if state["count"] < state["max"]:
        return "continue"
    return "finish"

builder.add_conditional_edges(
    "process",
    should_continue,
    {"continue": "process", "finish": END}
)
```

### 04. 持久化与检查点 (`04_checkpointer.py`)

学习 LangGraph 的持久化功能：
- 使用 `MemorySaver` 进行内存持久化
- 线程 ID 和会话管理
- 状态快照和恢复
- 时间旅行 (Time Travel)

```python
from langgraph.checkpoint.memory import MemorySaver

memory = MemorySaver()
graph = builder.compile(checkpointer=memory)

config = {"configurable": {"thread_id": "session-1"}}
result = graph.invoke({"input": "data"}, config)

# 获取状态
state = graph.get_state(config)

# 获取历史
history = list(graph.get_state_history(config))
```

### 05. 人工干预 (`05_human_in_the_loop.py`)

学习如何在 LangGraph 中实现人工干预：
- `interrupt_before`: 在节点执行前中断
- `interrupt_after`: 在节点执行后中断
- `interrupt()`: 在节点内部主动中断
- `Command(resume=...)`: 恢复执行并传入数据

```python
# 方式1: interrupt_before
graph = builder.compile(
    checkpointer=memory,
    interrupt_before=["sensitive_node"]
)

# 方式2: interrupt() 函数
def approval_node(state):
    decision = interrupt("需要审批，请确认:")
    return {"approved": decision == "yes"}

# 恢复执行
from langgraph.types import Command
command = Command(resume="yes")
result = graph.invoke(command, config)
```

### 06. 工具调用 (`06_tools.py`)

学习如何在 LangGraph 中使用工具：
- 使用 `@tool` 装饰器定义工具
- 使用 `ToolNode` 执行工具
- 绑定工具到 LLM
- 工具调用循环

```python
from langchain_core.tools import tool
from langgraph.prebuilt import ToolNode

@tool
def my_tool(query: str) -> str:
    """工具描述"""
    return "结果"

tools = [my_tool]
tool_node = ToolNode(tools)
```

### 07. 子图与组合 (`07_subgraphs.py`)

学习如何在 LangGraph 中使用子图：
- 创建子图
- 将子图作为节点添加到父图
- 父子图之间的状态传递

```python
# 创建子图
subgraph = subgraph_builder.compile()

# 添加到父图
builder.add_node(
    "subgraph_node",
    subgraph,
    input=lambda state: {"text": state["input"]},
    output=lambda parent, sub: {"result": sub["output"]}
)
```

### 08. 预建组件 (`08_prebuilt.py`)

学习 LangGraph 的预建组件：
- `ToolNode`: 工具执行节点
- `tools_condition`: 工具调用条件路由
- `MessagesState`: 预建的消息状态

```python
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.graph import MessagesState

# 使用预建组件
builder.add_node("tools", ToolNode(tools))
builder.add_conditional_edges("agent", tools_condition)
```

### 09. 完整 AI 代理 (`09_real_llm_agent.py`)

综合示例，展示如何构建一个完整的 AI 代理：
- 工具调用
- 记忆管理
- 人工干预
- 多轮对话

## 核心概念速查

### 状态定义

```python
from typing import TypedDict, Annotated
import operator

class State(TypedDict):
    # 普通字段（覆盖更新）
    text: str
    count: int

    # 带 reducer 的字段（追加更新）
    messages: Annotated[list, operator.add]
```

### 图的构建

```python
from langgraph.graph import StateGraph, START, END

builder = StateGraph(State)

# 添加节点
builder.add_node("name", node_function)

# 添加边
builder.add_edge(START, "node_a")
builder.add_edge("node_a", "node_b")
builder.add_edge("node_b", END)

# 添加条件边
builder.add_conditional_edges(
    "node_a",
    routing_function,
    {"path_1": "node_b", "path_2": "node_c"}
)

# 编译
graph = builder.compile(checkpointer=memory)
```

### 执行图

```python
# 获取最终结果
result = graph.invoke(initial_state, config)

# 流式获取每步结果
for event in graph.stream(initial_state, config):
    print(event)

# 获取完整状态流
for state in graph.stream(initial_state, config, stream_mode="values"):
    print(state)
```

## 使用真实 LLM

```python
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

# 创建模型
model = ChatOpenAI(model="gpt-4")

# 定义工具
@tool
def my_tool(query: str) -> str:
    """工具描述"""
    return "结果"

# 创建代理
agent = create_react_agent(model, [my_tool])

# 使用
result = agent.invoke({"messages": [HumanMessage(content="你好")]})
```

## 最佳实践

1. **使用类型注解**: 使用 TypedDict 定义状态，确保类型安全

2. **合理设计状态**: 状态应该包含所有需要的信息，但不要过于复杂

3. **使用 checkpointer**: 保存状态以便恢复和调试

4. **模块化设计**: 使用子图将复杂逻辑分解为可管理的模块

5. **错误处理**: 在节点中添加适当的错误处理

6. **日志记录**: 添加日志以便调试和监控

## 常见问题

### Q: 如何调试图？

A: 使用 `stream()` 方法逐步查看执行过程，或使用 `get_state()` 查看当前状态。

### Q: 如何处理长时间运行的任务？

A: 使用 checkpointer 保存状态，可以随时恢复执行。

### Q: 如何实现并行执行？

A: LangGraph 支持并行边，可以同时执行多个节点。

### Q: 如何与外部系统集成？

A: 通过工具（tools）和自定义节点函数与外部系统集成。

## 参考资源

- [LangGraph 官方文档](https://langchain-ai.github.io/langgraph/)
- [LangChain 官方文档](https://python.langchain.com/)
- [LangGraph GitHub](https://github.com/langchain-ai/langgraph)
- [示例库](https://github.com/langchain-ai/langgraph/tree/main/examples)

## 许可证

本教程仅供学习参考。
