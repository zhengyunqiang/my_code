"""
LangGraph 基础教程 02: 条件边 (Conditional Edges)
================================================

本示例演示如何使用条件边实现分支逻辑：
1. 基于状态值决定下一步执行哪个节点
2. 使用 add_conditional_edges 添加条件边
3. 实现复杂的决策流程

核心概念：
- add_conditional_edges(source, path_func, path_map)
- path_func: 根据状态返回下一个节点名称的函数
- path_map: 可选，映射函数返回值到节点名称
"""

from langgraph.graph import StateGraph, START, END
from typing import TypedDict, Literal
import random


# ============================================
# 1. 定义状态
# ============================================

class RouterState(TypedDict):
    """路由器状态"""
    input_value: int
    route_decision: str
    result: str
    history: list[str]


# ============================================
# 2. 定义路由函数
# ============================================

def route_by_value(state: RouterState) -> str:
    """根据输入值决定路由"""
    value = state["input_value"]

    if value < 30:
        return "low_path"
    elif value < 70:
        return "medium_path"
    else:
        return "high_path"


def route_by_decision(state: RouterState) -> Literal["approve", "reject", "review"]:
    """根据决策字段路由"""
    return state.get("route_decision", "review")


# ============================================
# 3. 定义节点函数
# ============================================

def node_input(state: RouterState) -> dict:
    """输入节点"""
    value = state["input_value"]
    print(f">>> 输入节点: 接收到值 {value}")
    return {"history": [f"输入值: {value}"]}


def node_low(state: RouterState) -> dict:
    """低值处理"""
    print(">>> 低值路径: 执行轻量处理")
    return {
        "result": f"轻量处理完成 (值: {state['input_value']})",
        "history": ["路径: 低值处理"]
    }


def node_medium(state: RouterState) -> dict:
    """中等值处理"""
    print(">>> 中等路径: 执行标准处理")
    return {
        "result": f"标准处理完成 (值: {state['input_value']})",
        "history": ["路径: 标准处理"]
    }


def node_high(state: RouterState) -> dict:
    """高值处理"""
    print(">>> 高值路径: 执行深度处理")
    return {
        "result": f"深度处理完成 (值: {state['input_value']})",
        "history": ["路径: 深度处理"]
    }


def node_output(state: RouterState) -> dict:
    """输出节点"""
    print(f">>> 输出节点: {state['result']}")
    return {"history": ["处理完成"]}


# ============================================
# 4. 构建条件边图
# ============================================

def build_conditional_graph():
    """构建带条件边的图"""
    builder = StateGraph(RouterState)

    # 添加节点
    builder.add_node("input", node_input)
    builder.add_node("low_handler", node_low)
    builder.add_node("medium_handler", node_medium)
    builder.add_node("high_handler", node_high)
    builder.add_node("output", node_output)

    # 添加固定边
    builder.add_edge(START, "input")

    # 添加条件边 - 核心部分
    # add_conditional_edges(源节点, 路由函数, 路由映射)
    builder.add_conditional_edges(
        "input",              # 从哪个节点出发
        route_by_value,       # 路由函数，返回下一个节点名
        {
            "low_path": "low_handler",
            "medium_path": "medium_handler",
            "high_path": "high_handler"
        }
    )

    # 所有处理节点都指向输出节点
    builder.add_edge("low_handler", "output")
    builder.add_edge("medium_handler", "output")
    builder.add_edge("high_handler", "output")
    builder.add_edge("output", END)

    return builder.compile()


# ============================================
# 5. 更复杂的条件边示例 - 审批流程
# ============================================

class ApprovalState(TypedDict):
    """审批状态"""
    amount: float          # 金额
    approver_level: str    # 审批人级别
    decision: str          # 决策结果
    comments: list[str]


def check_amount(state: ApprovalState) -> str:
    """检查金额决定审批路径"""
    if state["amount"] <= 1000:
        return "auto_approve"
    elif state["amount"] <= 10000:
        return "manager_review"
    else:
        return "director_review"


def node_auto_approve(state: ApprovalState) -> dict:
    """自动审批"""
    print(f">>> 自动审批: 金额 {state['amount']} 已自动批准")
    return {
        "decision": "approved",
        "comments": ["系统自动审批通过"]
    }


def node_manager_review(state: ApprovalState) -> dict:
    """经理审批"""
    # 模拟审批决策
    approved = random.choice([True, True, False])  # 2/3 概率通过
    decision = "approved" if approved else "rejected"
    print(f">>> 经理审批: 金额 {state['amount']}, 结果: {decision}")
    return {
        "decision": decision,
        "approver_level": "manager",
        "comments": [f"经理审批: {decision}"]
    }


def node_director_review(state: ApprovalState) -> dict:
    """总监审批"""
    approved = random.choice([True, False])  # 50% 概率通过
    decision = "approved" if approved else "rejected"
    print(f">>> 总监审批: 金额 {state['amount']}, 结果: {decision}")
    return {
        "decision": decision,
        "approver_level": "director",
        "comments": [f"总监审批: {decision}"]
    }


def node_final(state: ApprovalState) -> dict:
    """最终处理"""
    status = "✅ 通过" if state["decision"] == "approved" else "❌ 拒绝"
    print(f">>> 最终结果: {status}")
    return {"comments": [f"流程结束: {status}"]}


def build_approval_graph():
    """构建审批流程图"""
    builder = StateGraph(ApprovalState)

    # 添加节点
    builder.add_node("auto_approve", node_auto_approve)
    builder.add_node("manager_review", node_manager_review)
    builder.add_node("director_review", node_director_review)
    builder.add_node("final", node_final)

    # 添加条件边 - 从 START 开始就进行路由
    builder.add_conditional_edges(
        START,
        check_amount,
        {
            "auto_approve": "auto_approve",
            "manager_review": "manager_review",
            "director_review": "director_review"
        }
    )

    # 所有审批节点都指向最终节点
    builder.add_edge("auto_approve", "final")
    builder.add_edge("manager_review", "final")
    builder.add_edge("director_review", "final")
    builder.add_edge("final", END)

    return builder.compile()


# ============================================
# 主程序
# ============================================

def main():
    print("=" * 60)
    print("示例1: 基于数值的条件路由")
    print("=" * 60)

    graph = build_conditional_graph()

    # 测试不同的输入值
    test_values = [15, 50, 85]

    for value in test_values:
        print(f"\n--- 测试输入值: {value} ---")
        result = graph.invoke({"input_value": value, "route_decision": "", "result": "", "history": []})
        print(f"结果: {result['result']}")

    print("\n" + "=" * 60)
    print("示例2: 审批流程（条件边从START开始）")
    print("=" * 60)

    approval_graph = build_approval_graph()

    # 测试不同金额的审批
    amounts = [500, 5000, 50000]

    for amount in amounts:
        print(f"\n--- 申请金额: ¥{amount} ---")
        result = approval_graph.invoke({
            "amount": amount,
            "approver_level": "",
            "decision": "",
            "comments": []
        })
        print(f"审批结果: {result['decision']}")


if __name__ == "__main__":
    main()


# ============================================
# 学习要点总结
# ============================================
"""
1. add_conditional_edges 用于添加条件边
2. 条件边可以根据状态值动态决定下一个节点
3. 路由函数返回的是节点名称或映射后的键
4. 条件边可以从任何节点开始，包括 START
5. 条件边可以实现复杂的分支逻辑

常见模式：
- 基于数值范围路由
- 基于状态字段路由
- 基于外部条件路由
- 实现审批流程
- 实现错误处理分支

练习：
- 创建一个基于字符串内容的路由
- 实现一个多层审批流程
- 添加一个"需要更多信息"的分支
"""
