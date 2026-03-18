#!/usr/bin/env python3
"""快速测试 MCP 工具调用"""
import requests
import json

BASE_URL = "http://localhost:8000"

# 检查服务状态
try:
    response = requests.get(f"{BASE_URL}/health", timeout=5)
    if response.status_code != 200:
        print("❌ 服务未运行")
        exit(1)
    print("✅ 服务正常运行")
except Exception as e:
    print(f"❌ 无法连接服务: {e}")
    exit(1)

# 测试工具列表
print("\n获取工具列表...")
response = requests.get(f"{BASE_URL}/tools")
if response.status_code == 200:
    tools = response.json()
    print(f"找到 {len(tools.get('tools', []))} 个工具")
    for tool in tools.get('tools', [])[:3]:
        print(f"  - {tool.get('name')}")
else:
    print(f"❌ 获取工具列表失败: {response.status_code}")
    exit(1)

# 测试 nl_database_operation
print("\n测试 nl_database_operation (dry_run)...")
request_data = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
        "name": "nl_database_operation",
        "arguments": {
            "natural_language": "生成 2 条测试数据",
            "dry_run": True
        }
    }
}

response = requests.post(
    f"{BASE_URL}/mcp",
    json=request_data,
    headers={"Content-Type": "application/json"},
    timeout=60
)

print(f"状态码: {response.status_code}")
result = response.json()

if "result" in result:
    print("✅ 调用成功")
    for item in result["result"].get("content", []):
        if item.get("type") == "text":
            # 只显示前 500 字符
            text = item.get("text", "")
            if len(text) > 500:
                text = text[:500] + "..."
            print(f"\n响应:\n{text}")
else:
    print(f"❌ 调用失败: {result.get('error')}")
