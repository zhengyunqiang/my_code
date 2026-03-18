#!/usr/bin/env python3
"""
测试自然语言数据库工具 - HTTP API

使用方法：
1. 先启动服务：python backend/main.py --transport http --port 8000
2. 运行测试：python test_nl_tool_http.py
"""

import requests
import json
import time


BASE_URL = "http://localhost:8000"


def check_service():
    """检查服务是否运行"""
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        if response.status_code == 200:
            print("✅ 服务正常运行")
            return True
    except requests.exceptions.RequestException:
        pass

    print("❌ 无法连接到服务")
    print("请先启动服务: python backend/main.py --transport http --port 8000")
    return False


def test_list_tools():
    """测试1: 列出所有可用工具"""
    print("\n" + "=" * 60)
    print("测试1: 列出所有可用工具")
    print("=" * 60)

    response = requests.get(f"{BASE_URL}/tools")
    print(f"状态码: {response.status_code}")

    if response.status_code == 200:
        tools = response.json()
        print(f"\n找到 {len(tools.get('tools', []))} 个工具:\n")

        for tool in tools.get('tools', []):
            print(f"📦 {tool.get('name')}")
            print(f"   描述: {tool.get('description', '')[:80]}...")
            print()

        # 查找 nl_database_tool
        nl_tool = None
        for tool in tools.get('tools', []):
            if tool.get('name') == 'nl_database_operation':
                nl_tool = tool
                break

        if nl_tool:
            print("✅ 找到 nl_database_operation 工具")
            print(f"\n工具 Schema:")
            print(json.dumps(nl_tool.get('inputSchema', {}), ensure_ascii=False, indent=2))
            return True
        else:
            print("❌ 未找到 nl_database_operation 工具")
            return False
    else:
        print(f"❌ 请求失败: {response.text}")
        return False


def test_tool_dry_run():
    """测试2: 预演模式 - 生成 SQL 但不执行"""
    print("\n" + "=" * 60)
    print("测试2: 预演模式 - 生成测试数据（不执行）")
    print("=" * 60)

    request_data = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {
            "name": "nl_database_operation",
            "arguments": {
                "natural_language": "在 users 表中添加 2 条测试数据",
                "dry_run": True
            }
        }
    }

    print(f"请求: {json.dumps(request_data, ensure_ascii=False)}\n")

    response = requests.post(
        f"{BASE_URL}/mcp",
        json=request_data,
        headers={"Content-Type": "application/json"},
        timeout=60
    )

    print(f"状态码: {response.status_code}")

    if response.status_code == 200:
        result = response.json()
        if "result" in result:
            print("响应:")
            result_data = result["result"]
            for item in result_data:
                if item.get("type") == "text":
                    print(item.get("text"))
            return True
        else:
            print("错误响应:")
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return False
    else:
        print(f"❌ 请求失败: {response.text}")
        return False


def test_tool_insert():
    """测试3: 实际插入数据"""
    print("\n" + "=" * 60)
    print("测试3: 实际插入测试数据")
    print("=" * 60)

    request_data = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": "nl_database_operation",
            "arguments": {
                "natural_language": "在 users 表中添加 3 条测试数据"
            }
        }
    }

    print(f"请求: {json.dumps(request_data, ensure_ascii=False)}\n")

    response = requests.post(
        f"{BASE_URL}/mcp",
        json=request_data,
        headers={"Content-Type": "application/json"},
        timeout=60
    )

    print(f"状态码: {response.status_code}")

    if response.status_code == 200:
        result = response.json()
        if "result" in result:
            print("响应:")
            result_data = result["result"]
            for item in result_data:
                if item.get("type") == "text":
                    print(item.get("text"))
            return True
        else:
            print("错误响应:")
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return False
    else:
        print(f"❌ 请求失败: {response.text}")
        return False


def test_tool_select():
    """测试4: 查询数据"""
    print("\n" + "=" * 60)
    print("测试4: 查询表数据")
    print("=" * 60)

    request_data = {
        "jsonrpc": "2.0",
        "id": 4,
        "method": "tools/call",
        "params": {
            "name": "nl_database_operation",
            "arguments": {
                "natural_language": "查询 users 表的数据，显示前 5 条"
            }
        }
    }

    print(f"请求: {json.dumps(request_data, ensure_ascii=False)}\n")

    response = requests.post(
        f"{BASE_URL}/mcp",
        json=request_data,
        headers={"Content-Type": "application/json"},
        timeout=60
    )

    print(f"状态码: {response.status_code}")

    if response.status_code == 200:
        result = response.json()
        if "result" in result:
            print("响应:")
            result_data = result["result"]
            for item in result_data:
                if item.get("type") == "text":
                    print(item.get("text"))
            return True
        else:
            print("错误响应:")
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return False
    else:
        print(f"❌ 请求失败: {response.text}")
        return False


def main():
    """主测试函数"""
    print("MCP System - 自然语言数据库工具测试")
    print("=" * 60)

    # 检查服务
    if not check_service():
        return

    # 运行测试
    results = []

    results.append(("列出工具", test_list_tools()))

    if results[-1][1]:  # 只有找到工具才继续
        time.sleep(1)
        results.append(("预演模式", test_tool_dry_run()))

        time.sleep(1)
        results.append(("插入数据", test_tool_insert()))

        time.sleep(1)
        results.append(("查询数据", test_tool_select()))

    # 总结
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)

    for test_name, passed in results:
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"{test_name}: {status}")

    total = len(results)
    passed = sum(1 for _, p in results if p)
    print(f"\n总计: {passed}/{total} 测试通过")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n测试已中断")
    except Exception as e:
        print(f"\n❌ 测试出错: {e}")
        import traceback
        traceback.print_exc()
