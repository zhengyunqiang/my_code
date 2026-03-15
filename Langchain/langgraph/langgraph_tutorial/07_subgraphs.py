"""
LangGraph 基础教程 07: 子图与组合 (Subgraphs)
=============================================

本示例演示如何在 LangGraph 中使用子图：
1. 创建子图
2. 将子图作为节点添加到父图
3. 父子图之间的状态传递
4. 实际应用场景

核心概念：
- 子图可以作为一个节点添加到另一个图中
- 状态通过输入/输出转换传递
- 子图可以有自己的独立状态
- 适合模块化和复用
"""

from langgraph.graph import StateGraph, START, END
from typing import TypedDict, Annotated
import operator


# ============================================
# 1. 定义状态
# ============================================

# 父图状态
class MainState(TypedDict):
    """主图状态"""
    user_input: str
    processed_text: str
    analysis_result: dict
    final_output: str
    logs: Annotated[list[str], operator.add]


# 子图1：文本处理
class TextProcessorState(TypedDict):
    """文本处理子图状态"""
    text: str
    processed: str
    word_count: int


# 子图2：情感分析
class SentimentState(TypedDict):
    """情感分析子图状态"""
    text: str
    sentiment: str
    confidence: float


# ============================================
# 2. 构建子图1：文本处理
# ============================================

def node_normalize(state: TextProcessorState) -> dict:
    """标准化文本"""
    text = state["text"].lower().strip()
    print(f"  [文本处理] 标准化: {state['text']} -> {text}")
    return {"text": text}


def node_count_words(state: TextProcessorState) -> dict:
    """统计词数"""
    count = len(state["text"].split())
    print(f"  [文本处理] 词数: {count}")
    return {"word_count": count}


def node_finalize_text(state: TextProcessorState) -> dict:
    """完成处理"""
    processed = f"[已处理] {state['text']} (词数: {state['word_count']})"
    print(f"  [文本处理] 完成: {processed}")
    return {"processed": processed}


def build_text_processor_subgraph():
    """构建文本处理子图"""
    builder = StateGraph(TextProcessorState)

    builder.add_node("normalize", node_normalize)
    builder.add_node("count_words", node_count_words)
    builder.add_node("finalize", node_finalize_text)

    builder.add_edge(START, "normalize")
    builder.add_edge("normalize", "count_words")
    builder.add_edge("count_words", "finalize")
    builder.add_edge("finalize", END)

    return builder.compile()


# ============================================
# 3. 构建子图2：情感分析
# ============================================

def node_analyze_sentiment(state: SentimentState) -> dict:
    """分析情感"""
    text = state["text"]
    # 简单的情感分析模拟
    positive_words = ["好", "棒", "优秀", "喜欢", "开心", "happy", "good"]
    negative_words = ["坏", "差", "糟糕", "讨厌", "难过", "sad", "bad"]

    positive_count = sum(1 for w in positive_words if w in text.lower())
    negative_count = sum(1 for w in negative_words if w in text.lower())

    if positive_count > negative_count:
        sentiment = "正面"
        confidence = 0.8
    elif negative_count > positive_count:
        sentiment = "负面"
        confidence = 0.8
    else:
        sentiment = "中性"
        confidence = 0.6

    print(f"  [情感分析] 结果: {sentiment} (置信度: {confidence})")
    return {"sentiment": sentiment, "confidence": confidence}


def build_sentiment_subgraph():
    """构建情感分析子图"""
    builder = StateGraph(SentimentState)

    builder.add_node("analyze", node_analyze_sentiment)

    builder.add_edge(START, "analyze")
    builder.add_edge("analyze", END)

    return builder.compile()


# ============================================
# 4. 构建父图并集成子图
# ============================================

# 状态转换函数
def text_processor_input(state: MainState) -> TextProcessorState:
    """将父图状态转换为子图输入"""
    return {"text": state["user_input"], "processed": "", "word_count": 0}


def text_processor_output(parent_state: MainState, subgraph_state: TextProcessorState) -> dict:
    """将子图输出合并到父图状态"""
    return {
        "processed_text": subgraph_state["processed"],
        "logs": [f"文本处理完成: 词数={subgraph_state['word_count']}"]
    }


def sentiment_input(state: MainState) -> SentimentState:
    """将父图状态转换为情感分析子图输入"""
    return {"text": state["processed_text"] or state["user_input"], "sentiment": "", "confidence": 0}


def sentiment_output(parent_state: MainState, subgraph_state: SentimentState) -> dict:
    """将情感分析结果合并到父图状态"""
    return {
        "analysis_result": {
            "sentiment": subgraph_state["sentiment"],
            "confidence": subgraph_state["confidence"]
        },
        "logs": [f"情感分析完成: {subgraph_state['sentiment']}"]
    }


# 父图节点
def node_input_handler(state: MainState) -> dict:
    """处理输入"""
    print(f"[主图] 接收输入: {state['user_input']}")
    return {"logs": ["输入已接收"]}


def node_generate_output(state: MainState) -> dict:
    """生成最终输出"""
    analysis = state.get("analysis_result", {})
    output = (
        f"处理结果:\n"
        f"  原文: {state['user_input']}\n"
        f"  处理后: {state['processed_text']}\n"
        f"  情感: {analysis.get('sentiment', '未知')} "
        f"(置信度: {analysis.get('confidence', 0):.0%})"
    )
    print(f"[主图] 生成输出")
    return {
        "final_output": output,
        "logs": ["输出已生成"]
    }


def build_main_graph():
    """构建主图"""
    # 创建子图实例
    text_processor = build_text_processor_subgraph()
    sentiment_analyzer = build_sentiment_subgraph()

    # 构建主图
    builder = StateGraph(MainState)

    # 添加普通节点
    builder.add_node("input_handler", node_input_handler)
    builder.add_node("generate_output", node_generate_output)

    # 添加子图作为节点
    builder.add_node(
        "text_processor",
        text_processor,
        input=text_processor_input,
        output=text_processor_output
    )

    builder.add_node(
        "sentiment_analyzer",
        sentiment_analyzer,
        input=sentiment_input,
        output=sentiment_output
    )

    # 定义边
    builder.add_edge(START, "input_handler")
    builder.add_edge("input_handler", "text_processor")
    builder.add_edge("text_processor", "sentiment_analyzer")
    builder.add_edge("sentiment_analyzer", "generate_output")
    builder.add_edge("generate_output", END)

    return builder.compile()


# ============================================
# 5. 演示子图
# ============================================

def demo_subgraphs():
    """演示子图功能"""
    print("=" * 60)
    print("子图演示")
    print("=" * 60)

    graph = build_main_graph()

    # 测试1
    print("\n--- 测试1: 正面情感 ---")
    result = graph.invoke({
        "user_input": "今天天气真好，我很开心",
        "processed_text": "",
        "analysis_result": {},
        "final_output": "",
        "logs": []
    })
    print(f"\n最终输出:\n{result['final_output']}")
    print(f"\n日志: {result['logs']}")

    # 测试2
    print("\n" + "-" * 60)
    print("--- 测试2: 负面情感 ---")
    result = graph.invoke({
        "user_input": "这个产品太糟糕了，很讨厌",
        "processed_text": "",
        "analysis_result": {},
        "final_output": "",
        "logs": []
    })
    print(f"\n最终输出:\n{result['final_output']}")


# ============================================
# 6. 更复杂的子图示例 - 订单处理系统
# ============================================

# 库存检查子图
class InventoryState(TypedDict):
    product_id: str
    quantity: int
    available: bool
    warehouse: str


def check_stock(state: InventoryState) -> dict:
    """检查库存"""
    # 模拟库存检查
    available = state["quantity"] <= 100
    warehouse = "A仓" if state["product_id"].startswith("A") else "B仓"
    print(f"  [库存检查] 产品 {state['product_id']}: {'有货' if available else '缺货'}")
    return {"available": available, "warehouse": warehouse}


def build_inventory_subgraph():
    """构建库存检查子图"""
    builder = StateGraph(InventoryState)
    builder.add_node("check", check_stock)
    builder.add_edge(START, "check")
    builder.add_edge("check", END)
    return builder.compile()


# 支付处理子图
class PaymentState(TypedDict):
    order_id: str
    amount: float
    payment_method: str
    status: str
    transaction_id: str


def process_payment(state: PaymentState) -> dict:
    """处理支付"""
    import random
    transaction_id = f"TXN-{random.randint(10000, 99999)}"
    status = "success"  # 模拟总是成功
    print(f"  [支付处理] 订单 {state['order_id']}: ¥{state['amount']} - {status}")
    return {"status": status, "transaction_id": transaction_id}


def build_payment_subgraph():
    """构建支付处理子图"""
    builder = StateGraph(PaymentState)
    builder.add_node("process", process_payment)
    builder.add_edge(START, "process")
    builder.add_edge("process", END)
    return builder.compile()


# 订单处理主图
class OrderState(TypedDict):
    order_id: str
    product_id: str
    quantity: int
    amount: float
    payment_method: str
    inventory_status: dict
    payment_status: dict
    final_status: str
    logs: Annotated[list[str], operator.add]


def inventory_input(state: OrderState) -> InventoryState:
    return {
        "product_id": state["product_id"],
        "quantity": state["quantity"],
        "available": False,
        "warehouse": ""
    }


def inventory_output(parent: OrderState, sub: InventoryState) -> dict:
    return {
        "inventory_status": {
            "available": sub["available"],
            "warehouse": sub["warehouse"]
        },
        "logs": [f"库存检查: {'有货' if sub['available'] else '缺货'}"]
    }


def payment_input(state: OrderState) -> PaymentState:
    return {
        "order_id": state["order_id"],
        "amount": state["amount"],
        "payment_method": state["payment_method"],
        "status": "",
        "transaction_id": ""
    }


def payment_output(parent: OrderState, sub: PaymentState) -> dict:
    return {
        "payment_status": {
            "status": sub["status"],
            "transaction_id": sub["transaction_id"]
        },
        "logs": [f"支付: {sub['status']}"]
    }


def check_inventory(state: OrderState) -> str:
    """检查库存是否可用"""
    if state["inventory_status"].get("available"):
        return "process_payment"
    return "cancel_order"


def finalize_order(state: OrderState) -> dict:
    """完成订单"""
    status = "已完成" if state["payment_status"].get("status") == "success" else "已取消"
    print(f"[订单系统] 最终状态: {status}")
    return {
        "final_status": status,
        "logs": [f"订单{status}"]
    }


def cancel_order(state: OrderState) -> dict:
    """取消订单"""
    print(f"[订单系统] 订单取消: 库存不足")
    return {
        "final_status": "已取消-库存不足",
        "logs": ["订单取消: 库存不足"]
    }


def build_order_system():
    """构建订单处理系统"""
    inventory_sub = build_inventory_subgraph()
    payment_sub = build_payment_subgraph()

    builder = StateGraph(OrderState)

    builder.add_node("inventory", inventory_sub, input=inventory_input, output=inventory_output)
    builder.add_node("payment", payment_sub, input=payment_input, output=payment_output)
    builder.add_node("finalize", finalize_order)
    builder.add_node("cancel", cancel_order)

    builder.add_edge(START, "inventory")
    builder.add_conditional_edges(
        "inventory",
        check_inventory,
        {
            "process_payment": "payment",
            "cancel_order": "cancel"
        }
    )
    builder.add_edge("payment", "finalize")
    builder.add_edge("finalize", END)
    builder.add_edge("cancel", END)

    return builder.compile()


def demo_order_system():
    """演示订单系统"""
    print("\n" + "=" * 60)
    print("订单处理系统演示")
    print("=" * 60)

    graph = build_order_system()

    # 订单1：正常流程
    print("\n--- 订单1: 正常流程 ---")
    result = graph.invoke({
        "order_id": "ORD-001",
        "product_id": "A001",
        "quantity": 10,
        "amount": 999.00,
        "payment_method": "credit_card",
        "inventory_status": {},
        "payment_status": {},
        "final_status": "",
        "logs": []
    })
    print(f"最终状态: {result['final_status']}")

    # 订单2：库存不足
    print("\n--- 订单2: 库存不足 ---")
    result = graph.invoke({
        "order_id": "ORD-002",
        "product_id": "B002",
        "quantity": 200,  # 超过库存
        "amount": 1999.00,
        "payment_method": "alipay",
        "inventory_status": {},
        "payment_status": {},
        "final_status": "",
        "logs": []
    })
    print(f"最终状态: {result['final_status']}")


# ============================================
# 主程序
# ============================================

def main():
    demo_subgraphs()
    demo_order_system()


if __name__ == "__main__":
    main()


# ============================================
# 学习要点总结
# ============================================
"""
1. 子图可以作为一个节点添加到父图中
2. 使用 input/output 函数转换状态
3. 子图适合模块化和代码复用
4. 可以有多层嵌套的子图

子图的应用场景：
- 将复杂流程分解为可管理的模块
- 复用通用功能（如支付、库存检查）
- 团队协作开发
- 测试独立模块

最佳实践：
- 每个子图有明确的职责
- 使用清晰的状态转换函数
- 保持子图的独立性

练习：
- 创建一个带验证的表单处理子图
- 实现一个多层嵌套的子图结构
- 将之前的工具调用示例封装为子图
"""
