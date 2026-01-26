from langgraph.graph import StateGraph, START,END
from langgraph.checkpoint.memory import MemorySaver
from typing import TypedDict

#定义状态
class State(TypedDict):
    content:str
    feedback:str

#定义节点函数
def write_draft(state:State):
    print("Agent:正在撰写草稿...")
    return {"content":"这是Agent生成的初始草稿"}

def publish(state:State):
    print(f"System:已发布内容->{state['content']}")
    return {"content":"已发布"}

#构建图
builder = StateGraph(State)
builder.add_node("writer",write_draft)
builder.add_node("publisher",publish)

builder.add_edge(START,"writer")
builder.add_edge("writer","publisher")
builder.add_edge("publisher",END)

#设定Checkpointer(内容存储)
memory = MemorySaver()

#编译图
#这里指定在“publisher”节点执行“之前”中断
graph = builder.compile(
    checkpointer = memory,
    interrupt_before = ["publisher"]
)

#设置线程ID（对上下文恢复至关重要）
config  = {"configurable":{"thread_id":"thread-1"}}

print("第一阶段：执行到中断点")
#初始输入
events = graph.stream({"content":"","feedback":""},config)
for event in events:
    print(event)

#此时程序会执行完“writer”,然后暂停
#publisher 尚未执行

print("\n第二节点：人类介入")

#获取当前状态快照
snapshot = graph.get_state(config)
print(f"当前暂停在节点：{snapshot.next}") #应该显示（‘publisher’，）
print(f"当前内容：{snapshot.values['content']}")

# 模拟人类修改了草稿（这里是Human-in-the-loop的精髓）
new_content = "这是人类修改后的完美草稿。"
graph.update_state(config,{"content":new_content})
print("人类已修改草稿内容")

#恢复执行
print("\n第三阶段：恢复执行")
#传入None 代表继续执行，不提供新输入（因为此时已经用update_state修改过）
events = graph.stream(None,config)
for event in events:
    print(event)

#此时“publisher” 会执行，并打印出修改后的内容