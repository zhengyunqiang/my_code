#通过递归遍历树形结构的节点，并按照 task_id 收集所有节点，将其存储在给定的字典中。
def _collect_all_nodes_local(
        node:dict,
        nodes_dict:dict,
) -> None:
    if not isinstance(node,dict):
        return
    node_task_id = node.get("task_id")
    if node_task_id:
        nodes_dict[node_task_id] = node
    children = node.get("children")
    if isinstance(children,list):
        for child in children:
            _collect_all_nodes_local(child,nodes_dict)