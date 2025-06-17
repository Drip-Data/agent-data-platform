#!/usr/bin/env python3
"""
WebSocket测试客户端，用于诊断MCP连接问题
"""

import asyncio
import json
import websockets.legacy.client as websockets_client
import uuid

async def test_toolscore_connection():
    """测试与ToolScore的WebSocket连接"""
    uri = "ws://localhost:8089/websocket"
    
    try:
        print(f"连接到 {uri}...")
        async with websockets_client.connect(uri) as websocket:
            print("✅ WebSocket连接成功")
            
            # 测试1: 获取可用工具
            print("\n🔍 测试1: 获取可用工具列表")
            request_id = str(uuid.uuid4())
            request = {
                "type": "request",
                "action": "get_available_tools",
                "request_id": request_id
            }
            
            await websocket.send(json.dumps(request))
            print(f"📤 发送请求: {json.dumps(request, indent=2)}")
            
            response = await websocket.recv()
            print(f"📥 收到响应: {response}")
            response_data = json.loads(response)
            print(f"📥 解析后响应: {json.dumps(response_data, indent=2)}")
            
            # 测试2: 执行Python工具
            print("\n🔍 测试2: 执行Python工具")
            request_id = str(uuid.uuid4())
            request = {
                "type": "execute_tool",
                "request_id": request_id,
                "tool_id": "python-executor-mcp-server",
                "action": "python_execute",
                "parameters": {
                    "code": "print('Hello from WebSocket test!')"
                }
            }
            
            await websocket.send(json.dumps(request))
            print(f"📤 发送请求: {json.dumps(request, indent=2)}")
            
            response = await websocket.recv()
            print(f"📥 收到响应: {response}")
            response_data = json.loads(response)
            print(f"📥 解析后响应: {json.dumps(response_data, indent=2)}")
            
    except Exception as e:
        print(f"❌ 连接失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_toolscore_connection())