"""
LangGraph 基础教程 03: 循环与迭代 (Loops)
=========================================

本示例演示如何在 LangGraph 中实现循环：
1. 使用条件边创建循环
2. 状态驱动的迭代
3. 实现重试机制
4. 循环终止条件

核心概念：
- 循环是通过条件边回到之前的节点实现的
- 必须有明确的终止条件，否则会无限循环
- 状态中需要跟踪迭代次数或条件
"""

from langgraph.graph import StateGraph, START, END
from typing import TypedDict, Annotated
import operator
import random


# ============================================
# 1. 基础循环示例 - 计数器
# ============================================

class CounterState(TypedDict):
    """计数器状态"""
    count: int
    max_count: int
    history: Annotated[list[str], operator.add]


def node_increment(state: CounterState) -> dict:
    """递增节点"""
    new_count = state["count"] + 1
    print(f">>> 计数: {new_count}/{state['max_count']}")
    return {
        "count": new_count,
        "history": [f"步骤 {new_count}"]
    }


def should_continue(state: CounterState) -> str:
    """决定是否继续循环"""
    if state["count"] < state["max_count"]:
        return "continue"
    else:
        return "finish"


def build_counter_loop():
    """构建计数器循环图"""
    builder = StateGraph(CounterState)

    builder.add_node("increment", node_increment)

    # 入口边
    builder.add_edge(START, "increment")

    # 条件边 - 实现循环的关键
    builder.add_conditional_edges(
        "increment",
        should_continue,
        {
            "continue": "increment",  # 回到自己，形成循环
            "finish": END
        }
    )

    return builder.compile()


# ============================================
# 2. 重试机制示例
# ============================================

class RetryState(TypedDict):
    """重试状态"""
    attempt: int
    max_attempts: int
    success: bool
    result: str
    logs: Annotated[list[str], operator.add]


def node_attempt_task(state: RetryState) -> dict:
    """尝试执行任务"""
    attempt = state["attempt"] + 1

    # 模拟任务执行（有概率失败）
    # 随着尝试次数增加，成功概率提高
    success_rate = 0.3 + (attempt * 0.2)  # 50%, 70%, 90%, ...
    success = random.random() < success_rate

    status = "✅ 成功" if success else "❌ 失败"
    print(f">>> 第 {attempt} 次尝试 (成功率: {success_rate:.0%}): {status}")

    return {
        "attempt": attempt,
        "success": success,
        "result": f"任务{'成功' if success else '失败'}" if success or attempt >= state["max_attempts"] else "",
        "logs": [f"尝试 #{attempt}: {status}"]
    }


def should_retry(state: RetryState) -> str:
    """决定是否重试"""
    if state["success"]:
        return "success"
    elif state["attempt"] >= state["max_attempts"]:
        return "max_retries"
    else:
        return "retry"


def node_handle_success(state: RetryState) -> dict:
    """处理成功"""
    print(">>> 任务最终成功!")
    return {"logs": ["最终状态: 成功"]}


def node_handle_failure(state: RetryState) -> dict:
    """处理失败"""
    print(f">>> 达到最大重试次数 ({state['max_attempts']}次)，任务失败")
    return {"logs": ["最终状态: 失败"]}


def build_retry_graph():
    """构建重试机制图"""
    builder = StateGraph(RetryState)

    builder.add_node("attempt", node_attempt_task)
    builder.add_node("success_handler", node_handle_success)
    builder.add_node("failure_handler", node_handle_failure)

    builder.add_edge(START, "attempt")

    # 核心循环逻辑
    builder.add_conditional_edges(
        "attempt",
        should_retry,
        {
            "success": "success_handler",
            "max_retries": "failure_handler",
            "retry": "attempt"  # 回到 attempt 节点，形成循环
        }
    )

    builder.add_edge("success_handler", END)
    builder.add_edge("failure_handler", END)

    return builder.compile()


# ============================================
# 3. 工作流迭代示例 - 逐步完善
# ============================================

class WorkflowState(TypedDict):
    """工作流状态"""
    content: str
    quality_score: int
    iteration: int
    max_iterations: int
    improvement_history: Annotated[list[dict], operator.add]


def node_analyze(state: WorkflowState) -> dict:
    """分析内容质量"""
    # 模拟质量评估
    content_length = len(state["content"])
    base_score = min(100, content_length)

    # 每次迭代质量提升
    quality_score = min(100, base_score + state["iteration"] * 15)

    print(f">>> 分析内容: 长度={content_length}, 质量分数={quality_score}")

    return {
        "quality_score": quality_score,
        "improvement_history": [{
            "iteration": state["iteration"],
            "quality": quality_score
        }]
    }


def node_improve(state: WorkflowState) -> dict:
    """改进内容"""
    iteration = state["iteration"] + 1

    # 模拟内容改进
    current_content = state["content"]
    improved_content = current_content + f" [改进{iteration}]"

    print(f">>> 改进内容 (迭代 {iteration})")

    return {
        "content": improved_content,
        "iteration": iteration
    }


def check_quality(state: WorkflowState) -> str:
    """检查质量是否达标"""
    if state["quality_score"] >= 80:
        return "done"
    elif state["iteration"] >= state["max_iterations"]:
        return "max_iterations"
    else:
        return "continue"


def node_finalize(state: WorkflowState) -> dict:
    """最终处理"""
    print(f">>> 内容最终完成! 质量分数: {state['quality_score']}")
    return {}


def build_workflow_graph():
    """构建工作流迭代图"""
    builder = StateGraph(WorkflowState)

    builder.add_node("analyze", node_analyze)
    builder.add_node("improve", node_improve)
    builder.add_node("finalize", node_finalize)

    # 流程: START -> analyze -> (检查) -> improve (循环) 或 finalize
    builder.add_edge(START, "analyze")

    builder.add_conditional_edges(
        "analyze",
        check_quality,
        {
            "done": "finalize",
            "max_iterations": "finalize",
            "continue": "improve"
        }
    )

    # 改进后回到分析节点，形成循环
    builder.add_edge("improve", "analyze")
    builder.add_edge("finalize", END)

    return builder.compile()


# ============================================
# 主程序
# ============================================

def main():
    print("=" * 60)
    print("示例1: 基础计数循环")
    print("=" * 60)

    counter_graph = build_counter_loop()
    result = counter_graph.invoke({
        "count": 0,
        "max_count": 5,
        "history": []
    })
    print(f"\n最终历史: {result['history']}")

    print("\n" + "=" * 60)
    print("示例2: 重试机制")
    print("=" * 60)

    retry_graph = build_retry_graph()
    result = retry_graph.invoke({
        "attempt": 0,
        "max_attempts": 5,
        "success": False,
        "result": "",
        "logs": []
    })
    print(f"\n最终结果: {result['result']}")
    print(f"尝试次数: {result['attempt']}")

    print("\n" + "=" * 60)
    print("示例3: 工作流迭代改进")
    print("=" * 60)

    workflow_graph = build_workflow_graph()
    result = workflow_graph.invoke({
        "content": "初始内容",
        "quality_score": 0,
        "iteration": 0,
        "max_iterations": 5,
        "improvement_history": []
    })
    print(f"\n最终内容: {result['content']}")
    print(f"质量分数: {result['quality_score']}")
    print(f"迭代历史: {result['improvement_history']}")

    print("\n" + "=" * 60)
    print("可视化迭代过程 (使用 stream)")
    print("=" * 60)

    print("\n逐步执行过程:")
    for event in workflow_graph.stream({
        "content": "初始内容",
        "quality_score": 0,
        "iteration": 0,
        "max_iterations": 3,
        "improvement_history": []
    }):
        node_name = list(event.keys())[0]
        print(f"  -> 执行节点: {node_name}")


if __name__ == "__main__":
    main()


# ============================================
# 学习要点总结
# ============================================
"""
1. 循环通过条件边回到之前的节点实现
2. 必须有明确的终止条件，防止无限循环
3. 常见的终止条件：
   - 计数器达到最大值
   - 质量分数达标
   - 任务成功
4. 状态中跟踪迭代次数很重要

常见模式：
- 重试机制
- 迭代改进
- 轮询/等待
- 批处理

练习：
- 实现一个指数退避重试机制
- 创建一个数据处理管道，直到数据质量达标
- 实现一个带超时的轮询机制
"""
