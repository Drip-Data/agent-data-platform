#!/usr/bin/env python3
"""
测试 MCP 连接
"""
import asyncio
import json
import websockets.legacy.client as websockets_client

async def test_mcp_connection():
    """测试连接到 python-executor-mcp-server"""
    url = "ws://localhost:8081"
    try:
        print(f"连接到: {url}")
        async with websockets_client.connect(url) as websocket:
            print("连接成功！")
            
            # 发送一个测试请求
            test_request = {
                "type": "execute_tool",
                "tool_id": "python-executor-mcp-server", 
                "action": "python_execute",
                "parameters": {"code": "print(sum(range(1, 101)))"}
            }
            
            await websocket.send(json.dumps(test_request))
            print("请求已发送")
            
            response = await websocket.recv()
            print(f"收到响应: {response}")
            
    except Exception as e:
        print(f"连接失败: {e}")

if __name__ == "__main__":
    asyncio.run(test_mcp_connection())