#!/usr/bin/env python3
"""
直接测试Python Executor MCP服务器
"""

import asyncio
import json
import websockets.legacy.client as websockets_client
import uuid

async def test_python_executor():
    """直接测试Python Executor MCP服务器"""
    uri = "ws://localhost:8081"  # Python executor端口
    
    try:
        print(f"连接到Python Executor: {uri}...")
        async with websockets_client.connect(uri) as websocket:
            print("✅ 连接Python Executor成功")
            
            # 测试执行Python代码
            request_id = str(uuid.uuid4())
            request = {
                "type": "execute_tool_action",
                "request_id": request_id,
                "tool_id": "python-executor-mcp-server",
                "action": "python_execute",
                "parameters": {
                    "code": "print(sum(range(1, 101)))"
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
    asyncio.run(test_python_executor())