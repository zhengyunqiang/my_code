"""
LangGraph 基础教程 04: 持久化与检查点 (Checkpointer)
===================================================

本示例演示 LangGraph 的持久化功能：
1. 使用 MemorySaver 进行内存持久化
2. 线程 ID 和会话管理
3. 状态快照和恢复
4. 时间旅行 (Time Travel)

核心概念：
- Checkpointer: 保存图执行状态的组件
- thread_id: 标识不同的会话/线程
- get_state(): 获取当前状态
- get_state_history(): 获取历史状态
- update_state(): 手动更新状态
"""

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from typing import TypedDict, Annotated
import operator
import time


# ============================================
# 1. 定义状态
# ============================================

class ConversationState(TypedDict):
    """对话状态"""
    messages: Annotated[list[str], operator.add]
    turn_count: int
    context: str


# ============================================
# 2. 定义节点
# ============================================

def node_user_input(state: ConversationState) -> dict:
    """模拟用户输入节点"""
    turn = state["turn_count"] + 1
    message = f"用户消息 #{turn}"
    print(f">>> [用户] 发送消息: {message}")
    return {
        "messages": [message],
        "turn_count": turn
    }


def node_ai_response(state: ConversationState) -> dict:
    """模拟 AI 响应节点"""
    turn = state["turn_count"]
    response = f"AI响应 #{turn}: 收到你的消息"
    print(f">>> [AI] 响应: {response}")
    return {
        "messages": [response],
        "context": f"对话上下文 - 轮次: {turn}"
    }


def node_should_continue(state: ConversationState) -> str:
    """决定是否继续对话"""
    if state["turn_count"] >= 3:
        return "end"
    return "continue"


# ============================================
# 3. 构建带持久化的图
# ============================================

def build_persistent_graph():
    """构建带持久化的对话图"""
    builder = StateGraph(ConversationState)

    builder.add_node("user_input", node_user_input)
    builder.add_node("ai_response", node_ai_response)

    builder.add_edge(START, "user_input")
    builder.add_edge("user_input", "ai_response")

    builder.add_conditional_edges(
        "ai_response",
        node_should_continue,
        {
            "continue": "user_input",
            "end": END
        }
    )

    # 创建内存检查点保存器
    checkpointer = MemorySaver()

    # 编译时传入 checkpointer
    return builder.compile(checkpointer=checkpointer)


# ============================================
# 4. 状态管理示例
# ============================================

def demo_basic_checkpointer():
    """演示基本的检查点功能"""
    print("=" * 60)
    print("基本检查点功能演示")
    print("=" * 60)

    graph = build_persistent_graph()

    # 使用 thread_id 区分不同的会话
    config = {"configurable": {"thread_id": "conversation-1"}}

    print("\n--- 第一次执行 ---")
    result = graph.invoke(
        {"messages": [], "turn_count": 0, "context": ""},
        config
    )
    print(f"消息数: {len(result['messages'])}")

    print("\n--- 获取当前状态 ---")
    snapshot = graph.get_state(config)
    print(f"当前轮次: {snapshot.values['turn_count']}")
    print(f"消息列表: {snapshot.values['messages']}")
    print(f"下一步节点: {snapshot.next}")

    print("\n--- 继续同一会话 ---")
    # 使用相同的 thread_id 继续
    result = graph.invoke(None, config)  # 传入 None 继续执行
    print(f"消息数: {len(result['messages'])}")


def demo_multiple_threads():
    """演示多线程/多会话"""
    print("\n" + "=" * 60)
    print("多会话管理演示")
    print("=" * 60)

    graph = build_persistent_graph()

    # 会话 A
    config_a = {"configurable": {"thread_id": "session-A"}}
    print("\n--- 会话 A ---")
    graph.invoke({"messages": [], "turn_count": 0, "context": "主题A"}, config_a)
    state_a = graph.get_state(config_a)
    print(f"会话A 状态: {state_a.values['messages']}")

    # 会话 B
    config_b = {"configurable": {"thread_id": "session-B"}}
    print("\n--- 会话 B ---")
    graph.invoke({"messages": [], "turn_count": 0, "context": "主题B"}, config_b)
    state_b = graph.get_state(config_b)
    print(f"会话B 状态: {state_b.values['messages']}")

    # 恢复会话 A
    print("\n--- 恢复会话 A ---")
    state_a = graph.get_state(config_a)
    print(f"会话A 当前轮次: {state_a.values['turn_count']}")


def demo_state_history():
    """演示状态历史（时间旅行）"""
    print("\n" + "=" * 60)
    print("状态历史（时间旅行）演示")
    print("=" * 60)

    graph = build_persistent_graph()
    config = {"configurable": {"thread_id": "history-demo"}}

    # 执行多次，产生历史状态
    print("\n--- 执行图 ---")
    graph.invoke({"messages": [], "turn_count": 0, "context": ""}, config)

    print("\n--- 获取所有历史状态 ---")
    history = list(graph.get_state_history(config))

    print(f"历史状态数量: {len(history)}")
    for i, state in enumerate(history):
        print(f"  状态 {i}: turn_count={state.values.get('turn_count', 0)}, "
              f"next={state.next}, config={state.config}")


def demo_update_state():
    """演示手动更新状态"""
    print("\n" + "=" * 60)
    print("手动更新状态演示")
    print("=" * 60)

    graph = build_persistent_graph()
    config = {"configurable": {"thread_id": "update-demo"}}

    # 初始执行
    print("\n--- 初始执行 ---")
    graph.invoke({"messages": [], "turn_count": 0, "context": ""}, config)
    state = graph.get_state(config)
    print(f"当前消息: {state.values['messages']}")

    # 手动更新状态
    print("\n--- 手动更新状态 ---")
    graph.update_state(config, {"messages": ["[管理员插入的消息]"]})
    state = graph.get_state(config)
    print(f"更新后消息: {state.values['messages']}")

    # 继续执行
    print("\n--- 继续执行 ---")
    graph.invoke(None, config)
    state = graph.get_state(config)
    print(f"最终消息: {state.values['messages']}")


# ============================================
# 5. 实际应用示例 - 可中断的工作流
# ============================================

class TaskState(TypedDict):
    """任务状态"""
    task_name: str
    status: str
    progress: int
    logs: Annotated[list[str], operator.add]


def node_process_task(state: TaskState) -> dict:
    """处理任务"""
    print(f">>> 处理任务: {state['task_name']}")
    return {
        "status": "processing",
        "progress": 50,
        "logs": [f"开始处理: {state['task_name']}"]
    }


def node_complete_task(state: TaskState) -> dict:
    """完成任务"""
    print(f">>> 完成任务: {state['task_name']}")
    return {
        "status": "completed",
        "progress": 100,
        "logs": ["任务完成"]
    }


def build_task_graph():
    """构建任务处理图"""
    builder = StateGraph(TaskState)

    builder.add_node("process", node_process_task)
    builder.add_node("complete", node_complete_task)

    builder.add_edge(START, "process")
    builder.add_edge("process", "complete")
    builder.add_edge("complete", END)

    return builder.compile(checkpointer=MemorySaver())


def demo_task_persistence():
    """演示任务持久化"""
    print("\n" + "=" * 60)
    print("任务持久化演示")
    print("=" * 60)

    graph = build_task_graph()

    # 任务 1
    config1 = {"configurable": {"thread_id": "task-001"}}
    print("\n--- 处理任务 1 ---")
    result1 = graph.invoke({
        "task_name": "数据导出",
        "status": "pending",
        "progress": 0,
        "logs": []
    }, config1)
    print(f"任务1状态: {result1['status']}, 进度: {result1['progress']}%")

    # 任务 2
    config2 = {"configurable": {"thread_id": "task-002"}}
    print("\n--- 处理任务 2 ---")
    result2 = graph.invoke({
        "task_name": "报表生成",
        "status": "pending",
        "progress": 0,
        "logs": []
    }, config2)
    print(f"任务2状态: {result2['status']}, 进度: {result2['progress']}%")

    # 查询任务 1 的状态
    print("\n--- 查询任务 1 历史状态 ---")
    state1 = graph.get_state(config1)
    print(f"任务1: {state1.values['task_name']} - {state1.values['status']}")


# ============================================
# 主程序
# ============================================

def main():
    demo_basic_checkpointer()
    demo_multiple_threads()
    demo_state_history()
    demo_update_state()
    demo_task_persistence()


if __name__ == "__main__":
    main()


# ============================================
# 学习要点总结
# ============================================
"""
1. Checkpointer 用于持久化图的状态
2. MemorySaver 是最简单的内存持久化实现
3. thread_id 用于区分不同的会话
4. get_state() 获取当前状态快照
5. get_state_history() 获取所有历史状态
6. update_state() 手动更新状态

持久化的应用场景：
- 多轮对话
- 任务状态跟踪
- 会话管理
- 错误恢复
- 审计日志

进阶：
- 使用 SqliteSaver 进行 SQLite 持久化
- 使用 RedisSaver 进行 Redis 持久化
- 自定义 Checkpointer 实现

练习：
- 创建一个可以保存和恢复的聊天机器人
- 实现一个任务队列系统
- 使用 SQLite 替代 MemorySaver
"""
