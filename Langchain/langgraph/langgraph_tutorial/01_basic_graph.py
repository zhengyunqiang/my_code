"""
LangGraph 基础教程 01: 基本图结构
=====================================

本示例演示 LangGraph 的核心概念：
1. State（状态）- 在节点之间共享的数据结构
2. Node（节点）- 执行操作的函数
3. Edge（边）- 定义节点之间的流转
4. StateGraph - 构建和编译图

核心概念：
- StateGraph(State): 创建一个图，指定状态类型
- add_node(name, func): 添加节点
- add_edge(from, to): 添加边
- START/END: 特殊的入口和出口节点
- compile(): 编译图为可执行的图
"""

from langgraph.graph import StateGraph, START, END
from typing import TypedDict, Annotated
import operator


# ============================================
# 1. 定义状态 (State)
# ============================================
# State 是在图中流转的数据结构
# 使用 TypedDict 定义类型，确保类型安全

class BasicState(TypedDict):
    """基础状态定义"""
    messages: list[str]  # 消息列表
    count: int           # 计数器


# 使用 Annotated 可以定义特殊的合并行为
class AdvancedState(TypedDict):
    """高级状态 - 带有 reducer"""
    # Annotated[list, operator.add] 表示新值会与旧值合并（追加）
    # 而不是直接覆盖
    messages: Annotated[list[str], operator.add]
    current_step: str


# ============================================
# 2. 定义节点函数 (Nodes)
# ============================================
# 节点函数接收 state 作为参数，返回状态的更新部分

def node_greet(state: BasicState) -> dict:
    """问候节点"""
    print(">>> 执行 node_greet")
    return {
        "messages": ["Hello! 欢迎来到 LangGraph"],
        "count": 1
    }


def node_process(state: BasicState) -> dict:
    """处理节点"""
    print(f">>> 执行 node_process, 当前 count: {state['count']}")
    new_message = f"正在处理第 {state['count']} 次请求"
    return {
        "messages": state["messages"] + [new_message],
        "count": state["count"] + 1
    }


def node_goodbye(state: BasicState) -> dict:
    """告别节点"""
    print(">>> 执行 node_goodbye")
    return {
        "messages": state["messages"] + ["Goodbye! 感谢使用"],
    }


# ============================================
# 3. 构建图 (Build Graph)
# ============================================

def build_basic_graph():
    """构建基础线性图"""
    # 创建图构建器，指定状态类型
    builder = StateGraph(BasicState)

    # 添加节点
    builder.add_node("greet", node_greet)
    builder.add_node("process", node_process)
    builder.add_node("goodbye", node_goodbye)

    # 添加边，定义执行顺序
    # START -> greet -> process -> goodbye -> END
    builder.add_edge(START, "greet")
    builder.add_edge("greet", "process")
    builder.add_edge("process", "goodbye")
    builder.add_edge("goodbye", END)

    # 编译图
    graph = builder.compile()

    return graph


# ============================================
# 4. 运行图 (Run Graph)
# ============================================

def main():
    print("=" * 60)
    print("LangGraph 基础示例")
    print("=" * 60)

    # 构建并编译图
    graph = build_basic_graph()

    # 打印图结构
    print("\n图结构:")
    print(f"节点: {graph.nodes.keys()}")
    print(f"边: {graph.builder.edges}")

    # 运行图 - 使用 invoke 获取最终结果
    print("\n" + "=" * 60)
    print("方式1: 使用 invoke() 获取最终结果")
    print("=" * 60)

    initial_state = {"messages": [], "count": 0}
    result = graph.invoke(initial_state)
    print(f"\n最终状态: {result}")

    # 运行图 - 使用 stream 获取每一步的结果
    print("\n" + "=" * 60)
    print("方式2: 使用 stream() 获取每步结果")
    print("=" * 60)

    initial_state = {"messages": [], "count": 0}
    for event in graph.stream(initial_state):
        # event 是一个字典，key 是节点名，value 是该节点返回的状态更新
        node_name = list(event.keys())[0]
        node_output = event[node_name]
        print(f"\n节点 '{node_name}' 输出: {node_output}")

    # 运行图 - 使用 stream_mode 获取不同模式的结果
    print("\n" + "=" * 60)
    print("方式3: 使用 stream(mode='values') 获取完整状态")
    print("=" * 60)

    initial_state = {"messages": [], "count": 0}
    for state in graph.stream(initial_state, stream_mode="values"):
        print(f"\n当前完整状态: messages={len(state['messages'])}条, count={state['count']}")


if __name__ == "__main__":
    main()


# ============================================
# 学习要点总结
# ============================================
"""
1. State 定义了在图中流转的数据结构
2. Node 是处理状态的函数，返回状态的更新部分
3. Edge 定义节点之间的流转顺序
4. START 和 END 是特殊的入口和出口节点
5. invoke() 获取最终结果，stream() 获取每步结果
6. stream_mode="values" 可以获取每次更新后的完整状态

练习：
- 尝试添加一个新的节点
- 尝试修改状态结构，添加更多字段
- 尝试使用不同的 stream_mode
"""
