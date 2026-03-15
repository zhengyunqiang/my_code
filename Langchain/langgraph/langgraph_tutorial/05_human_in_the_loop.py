"""
LangGraph 基础教程 05: 人工干预 (Human-in-the-Loop)
==================================================

本示例演示如何在 LangGraph 中实现人工干预：
1. interrupt_before - 在节点执行前中断
2. interrupt_after - 在节点执行后中断
3. interrupt() - 在节点内部主动中断
4. Command(resume=...) - 恢复执行并传入数据

核心概念：
- interrupt_before: 指定在哪些节点前暂停
- interrupt_after: 指定在哪些节点后暂停
- interrupt(): 在节点内部主动请求人工输入
- Command(resume=value): 恢复执行并传入值
"""

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt, Command
from typing import TypedDict, Annotated
import operator


# ============================================
# 1. interrupt_before 示例 - 发布前审批
# ============================================

class PublishState(TypedDict):
    """发布状态"""
    content: str
    approved: bool
    approver: str
    comments: Annotated[list[str], operator.add]


def node_draft(state: PublishState) -> dict:
    """起草内容"""
    content = "这是一篇待发布的文章草稿..."
    print(f">>> 起草内容: {content}")
    return {
        "content": content,
        "comments": ["草稿已创建"]
    }


def node_publish(state: PublishState) -> dict:
    """发布内容"""
    print(f">>> 发布内容: {state['content']}")
    print(f">>> 审批人: {state['approver']}")
    return {
        "approved": True,
        "comments": ["内容已发布"]
    }


def build_publish_graph_with_interrupt_before():
    """构建发布图 - 使用 interrupt_before"""
    builder = StateGraph(PublishState)

    builder.add_node("draft", node_draft)
    builder.add_node("publish", node_publish)

    builder.add_edge(START, "draft")
    builder.add_edge("draft", "publish")
    builder.add_edge("publish", END)

    memory = MemorySaver()

    # 关键：在 publish 节点执行前中断
    graph = builder.compile(
        checkpointer=memory,
        interrupt_before=["publish"]  # 在 publish 之前暂停
    )

    return graph


def demo_interrupt_before():
    """演示 interrupt_before"""
    print("=" * 60)
    print("interrupt_before 示例 - 发布前审批")
    print("=" * 60)

    graph = build_publish_graph_with_interrupt_before()
    config = {"configurable": {"thread_id": "publish-1"}}

    # 阶段1：执行到中断点
    print("\n--- 阶段1: 执行到中断点 ---")
    graph.invoke({
        "content": "",
        "approved": False,
        "approver": "",
        "comments": []
    }, config)

    # 检查当前状态
    state = graph.get_state(config)
    print(f"当前节点: {state.next}")
    print(f"草稿内容: {state.values['content']}")

    # 阶段2：人工审批
    print("\n--- 阶段2: 人工审批 ---")
    print("管理员审核中...")
    # 修改状态（模拟审批）
    graph.update_state(config, {
        "approver": "张经理",
        "comments": ["内容已审核通过"]
    })

    # 阶段3：恢复执行
    print("\n--- 阶段3: 恢复执行 ---")
    result = graph.invoke(None, config)
    print(f"最终状态: approved={result['approved']}")


# ============================================
# 2. interrupt_after 示例 - 执行后审核
# ============================================

class DataProcessState(TypedDict):
    """数据处理状态"""
    raw_data: str
    processed_data: str
    reviewed: bool
    reviewer_comment: str


def node_process(state: DataProcessState) -> dict:
    """处理数据"""
    processed = f"已处理: {state['raw_data']}"
    print(f">>> 处理数据: {processed}")
    return {"processed_data": processed}


def node_finalize(state: DataProcessState) -> dict:
    """最终处理"""
    print(f">>> 最终处理: {state['processed_data']}")
    print(f">>> 审核意见: {state['reviewer_comment']}")
    return {"reviewed": True}


def build_process_graph_with_interrupt_after():
    """构建处理图 - 使用 interrupt_after"""
    builder = StateGraph(DataProcessState)

    builder.add_node("process", node_process)
    builder.add_node("finalize", node_finalize)

    builder.add_edge(START, "process")
    builder.add_edge("process", "finalize")
    builder.add_edge("finalize", END)

    memory = MemorySaver()

    # 关键：在 process 节点执行后中断
    graph = builder.compile(
        checkpointer=memory,
        interrupt_after=["process"]  # 在 process 之后暂停
    )

    return graph


def demo_interrupt_after():
    """演示 interrupt_after"""
    print("\n" + "=" * 60)
    print("interrupt_after 示例 - 处理后审核")
    print("=" * 60)

    graph = build_process_graph_with_interrupt_after()
    config = {"configurable": {"thread_id": "process-1"}}

    # 阶段1：执行到中断点（process 执行完后暂停）
    print("\n--- 阶段1: 执行处理 ---")
    graph.invoke({
        "raw_data": "原始数据ABC",
        "processed_data": "",
        "reviewed": False,
        "reviewer_comment": ""
    }, config)

    state = graph.get_state(config)
    print(f"处理后数据: {state.values['processed_data']}")
    print(f"等待审核...")

    # 阶段2：人工审核并添加意见
    print("\n--- 阶段2: 人工审核 ---")
    graph.update_state(config, {"reviewer_comment": "数据处理正确，可以继续"})

    # 阶段3：恢复执行
    print("\n--- 阶段3: 继续执行 ---")
    result = graph.invoke(None, config)
    print(f"最终状态: reviewed={result['reviewed']}")


# ============================================
# 3. interrupt() 函数示例 - 主动请求输入
# ============================================

class OrderState(TypedDict):
    """订单状态"""
    order_item: str
    quantity: int
    special_request: str
    status: str


def node_take_order(state: OrderState) -> dict:
    """接收订单"""
    print(f">>> 接收订单: {state['order_item']} x {state['quantity']}")
    return {"status": "ordering"}


def node_confirm_order(state: OrderState) -> dict:
    """确认订单 - 使用 interrupt 主动请求确认"""
    print(f">>> 确认订单...")

    # 主动中断，等待用户输入
    # interrupt() 的参数会显示给用户
    user_input = interrupt(
        f"请确认订单: {state['order_item']} x {state['quantity']}\n"
        f"请输入 'yes' 确认，或输入特殊要求"
    )

    print(f">>> 用户输入: {user_input}")

    # 根据用户输入决定下一步
    if user_input.lower() == 'yes':
        return {"status": "confirmed"}
    else:
        return {
            "special_request": user_input,
            "status": "modified"
        }


def node_prepare_order(state: OrderState) -> dict:
    """准备订单"""
    if state.get('special_request'):
        print(f">>> 准备订单 (特殊要求: {state['special_request']})")
    else:
        print(f">>> 准备订单")
    return {"status": "preparing"}


def node_complete_order(state: OrderState) -> dict:
    """完成订单"""
    print(f">>> 订单完成!")
    return {"status": "completed"}


def build_order_graph_with_interrupt():
    """构建订单图 - 使用 interrupt()"""
    builder = StateGraph(OrderState)

    builder.add_node("take_order", node_take_order)
    builder.add_node("confirm", node_confirm_order)
    builder.add_node("prepare", node_prepare_order)
    builder.add_node("complete", node_complete_order)

    builder.add_edge(START, "take_order")
    builder.add_edge("take_order", "confirm")
    builder.add_edge("confirm", "prepare")
    builder.add_edge("prepare", "complete")
    builder.add_edge("complete", END)

    memory = MemorySaver()

    # 使用 interrupt() 不需要指定 interrupt_before/after
    return builder.compile(checkpointer=memory)


def demo_interrupt_function():
    """演示 interrupt() 函数"""
    print("\n" + "=" * 60)
    print("interrupt() 示例 - 订单确认")
    print("=" * 60)

    graph = build_order_graph_with_interrupt()
    config = {"configurable": {"thread_id": "order-1"}}

    # 阶段1：执行到 interrupt() 处
    print("\n--- 阶段1: 下单 ---")
    events = graph.stream({
        "order_item": "牛肉面",
        "quantity": 2,
        "special_request": "",
        "status": ""
    }, config)

    for event in events:
        if "__interrupt__" in event:
            # 捕获中断信息
            interrupt_info = event["__interrupt__"][0]
            print(f"\n系统中断: {interrupt_info.value}")

    # 阶段2：用户确认
    print("\n--- 阶段2: 用户确认 ---")
    # 使用 Command(resume=...) 恢复执行并传入值
    user_response = "yes"  # 或者 "不要香菜"
    command = Command(resume=user_response)

    # 阶段3：恢复执行
    print("\n--- 阶段3: 恢复执行 ---")
    result = graph.invoke(command, config)
    print(f"最终状态: {result['status']}")


# ============================================
# 4. 完整示例 - 审批工作流
# ============================================

class ApprovalWorkflowState(TypedDict):
    """审批工作流状态"""
    request_id: str
    request_type: str
    amount: float
    submitter: str
    approver: str
    decision: str
    comments: Annotated[list[str], operator.add]


def node_submit(state: ApprovalWorkflowState) -> dict:
    """提交申请"""
    print(f">>> 提交申请: {state['request_type']}, 金额: {state['amount']}")
    return {"comments": [f"申请已提交 by {state['submitter']}"]}


def node_review(state: ApprovalWorkflowState) -> dict:
    """审批申请"""
    print(f">>> 等待审批...")

    # 请求审批人输入
    decision = interrupt(
        f"审批请求:\n"
        f"  ID: {state['request_id']}\n"
        f"  类型: {state['request_type']}\n"
        f"  金额: ¥{state['amount']}\n"
        f"  申请人: {state['submitter']}\n"
        f"\n请输入 'approve' 或 'reject':"
    )

    return {"decision": decision}


def node_approve(state: ApprovalWorkflowState) -> dict:
    """批准"""
    print(f">>> 申请已批准 by {state['approver']}")
    return {"comments": ["已批准"]}


def node_reject(state: ApprovalWorkflowState) -> dict:
    """拒绝"""
    print(f">>> 申请已拒绝")
    return {"comments": ["已拒绝"]}


def route_by_decision(state: ApprovalWorkflowState) -> str:
    """根据决策路由"""
    return state.get("decision", "reject")


def build_approval_workflow():
    """构建审批工作流"""
    builder = StateGraph(ApprovalWorkflowState)

    builder.add_node("submit", node_submit)
    builder.add_node("review", node_review)
    builder.add_node("approve", node_approve)
    builder.add_node("reject", node_reject)

    builder.add_edge(START, "submit")
    builder.add_edge("submit", "review")

    builder.add_conditional_edges(
        "review",
        route_by_decision,
        {
            "approve": "approve",
            "reject": "reject"
        }
    )

    builder.add_edge("approve", END)
    builder.add_edge("reject", END)

    memory = MemorySaver()
    return builder.compile(checkpointer=memory)


def demo_approval_workflow():
    """演示完整审批工作流"""
    print("\n" + "=" * 60)
    print("完整审批工作流示例")
    print("=" * 60)

    graph = build_approval_workflow()
    config = {"configurable": {"thread_id": "approval-001"}}

    # 提交申请
    print("\n--- 提交申请 ---")
    events = graph.stream({
        "request_id": "REQ-2024-001",
        "request_type": "差旅报销",
        "amount": 5000.00,
        "submitter": "李明",
        "approver": "",
        "decision": "",
        "comments": []
    }, config)

    for event in events:
        if "__interrupt__" in event:
            interrupt_info = event["__interrupt__"][0]
            print(f"\n{interrupt_info.value}")

    # 模拟审批人审批
    print("\n--- 审批人操作 ---")
    # 先更新审批人信息
    graph.update_state(config, {"approver": "王总"})

    # 提交审批决定
    command = Command(resume="approve")
    result = graph.invoke(command, config)

    print(f"\n最终状态:")
    print(f"  决策: {result['decision']}")
    print(f"  审批人: {result['approver']}")
    print(f"  评论: {result['comments']}")


# ============================================
# 主程序
# ============================================

def main():
    demo_interrupt_before()
    demo_interrupt_after()
    demo_interrupt_function()
    demo_approval_workflow()


if __name__ == "__main__":
    main()


# ============================================
# 学习要点总结
# ============================================
"""
1. interrupt_before: 在指定节点执行前暂停
2. interrupt_after: 在指定节点执行后暂停
3. interrupt(): 在节点内部主动请求人工输入
4. Command(resume=value): 恢复执行并传入值
5. update_state(): 手动更新状态

人工干预的应用场景：
- 审批流程
- 数据验证
- 用户确认
- 错误处理
- 内容审核

最佳实践：
- 使用 interrupt() 获取具体输入
- 使用 interrupt_before/after 进行简单暂停
- 使用 update_state() 修改状态
- 使用 thread_id 管理多个会话

练习：
- 创建一个多级审批流程
- 实现一个带确认删除的功能
- 创建一个可以编辑 AI 输出的流程
"""
