#!/usr/bin/env python3
"""
WebSocket测试脚本
"""
import asyncio
import websockets
import json
import sys

async def test_websocket():
    try:
        uri = 'ws://localhost:8081/websocket'
        print(f"连接到 {uri}...")
        
        async with websockets.connect(uri) as websocket:
            print('✅ WebSocket连接成功!')
            
            # 发送工具执行请求
            test_message = {
                'type': 'execute_tool',
                'tool_id': 'python-executor-mcp-server',
                'action': 'python_execute',
                'parameters': {
                    'code': 'print("Hello from WebSocket!")\nresult = 5 + 5\nprint(f"Result: {result}")'
                }
            }
            
            print("📤 发送执行请求...")
            await websocket.send(json.dumps(test_message))
            
            print("📥 等待响应...")
            response = await asyncio.wait_for(websocket.recv(), timeout=10.0)
            
            print('✅ 收到响应:')
            try:
                response_data = json.loads(response)
                print(json.dumps(response_data, indent=2, ensure_ascii=False))
            except:
                print(response)
                
    except asyncio.TimeoutError:
        print('❌ 响应超时')
    except Exception as e:
        print(f'❌ WebSocket测试失败: {e}')
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    asyncio.run(test_websocket()) 