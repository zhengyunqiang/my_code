from langgraph.graph import StateGraph, END
from openpyxl.styles.builtins import output


#1、定义状态
class AgentState(TypedDict):
    inpput: str
    output: str
    quality_score:int

#2、定义节点函数
def generate_draft(state):
    # 调用模型生成草稿
    return {"output":"generated text..."}

def grade_draft(state):
    #评分
    score = evaluate(state[output])
    return {"quality_score":score}

#定义条件循环
def check_quality(state):
    if state['quality_score'] > 8:
        return "end" #满意，结束
    else:
        return "rewrite" #不满意,重写

workflow = StateGraph(AgentState)

workflow.add_node("writer",generate_draft)
workflow.add_node("grader",grade_draft)

workflow.set_entry_point("writer")
workflow.add_edge("writer","grader")

#条件边：从评分节点出发，决定是结束还是回到写作节点
workflow.add_conditional_edges(
    "grader",
    check_quality,
    {
        "end":END,
        "rewrite":"writer"
    }
)