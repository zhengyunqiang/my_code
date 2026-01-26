from langgraph.graph import StateGraph,START,END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt,Command

from typing import TypedDict

class State(TypedDict):
    order:str

def humman_review_node(state:State):
    print(f"\n Bot:收到订单是'{state['order']}'。")

    #主动索取信息的模式
    user_decision = interrupt(f"'{state['order']}是否需要加辣？'")

    #当resume后，user_decision就是用户传入的值
    print(f"Bot:收到用户反馈 ->{user_decision}")

def final_step(state:State):
    print(f"Final:订单完成 -> {state['order']}")

#构建图
builder = StateGraph(State)
builder.add_node("review",humman_review_node)
builder.add_node("final",final_step)
builder.add_edge(START,"review")
builder.add_edge("review","final")
builder.add_edge("final",END)

#必须要有Checkpointer
memory = MemorySaver()
graph  = builder.compile(checkpointer = memory)

#第一阶段：触发中断流程
config = {"configurable":{"thread_id":"table-101"}}

print("+++++++开始点餐+++++++++")

#启动图
events = graph.stream({"order":"牛肉面"},config)

for event in events:
    #这里的event会包括interrupt信息
    if "__interrupt__" in event:
        print(f"系统中断：{event['__interrupt__'][0].value}")

#第二阶段：带值恢复（Resume with Value）

print("\n ---------用户回答并恢复--------------")

#使用Commamd对象，resume字段的值就是传给interrupt（）的返回值
command = Command(resume="微辣")

#再次调用stream，传入Command
events = graph.stream(command,config)

for event in events:
    print(event)

