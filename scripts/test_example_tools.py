#!/usr/bin/env python3
"""
示例工具测试脚本
用于验证所有示例工具是否正常工作
"""

import asyncio
import sys
import os
import time
import logging
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_demo_function_tool():
    """测试演示Function Tool"""
    print("\n=== 测试演示Function Tool ===")
    
    try:
        from tools.examples.demo_function_tool import DemoFunctionTool
        
        tool = DemoFunctionTool()
        
        # 测试用例
        test_cases = [
            {
                "name": "多语言问候",
                "action": "greet",
                "params": {"name": "测试用户", "language": "zh"}
            },
            {
                "name": "英文问候",
                "action": "greet", 
                "params": {"name": "TestUser", "language": "en"}
            },
            {
                "name": "斐波那契计算",
                "action": "calculate_fibonacci",
                "params": {"n": 8}
            },
            {
                "name": "随机数生成",
                "action": "generate_random",
                "params": {"type": "number", "count": 3, "min": 1, "max": 100}
            },
            {
                "name": "获取统计信息",
                "action": "get_statistics",
                "params": {}
            },
            {
                "name": "工作负载模拟",
                "action": "simulate_work",
                "params": {"duration": 0.5, "work_type": "light"}
            }
        ]
        
        success_count = 0
        
        for test_case in test_cases:
            try:
                print(f"\n测试: {test_case['name']}")
                result = await tool.execute(test_case['action'], test_case['params'])
                
                if result.get('success'):
                    print(f"✅ 成功: {result}")
                    success_count += 1
                else:
                    print(f"❌ 失败: {result}")
                    
            except Exception as e:
                print(f"❌ 异常: {e}")
        
        # 测试工具能力描述
        capabilities = tool.get_capabilities()
        print(f"\n工具能力数量: {len(capabilities)}")
        
        # 测试工具描述
        description = tool.get_description()
        print(f"工具描述长度: {len(description)} 字符")
        
        print(f"\n演示Function Tool测试结果: {success_count}/{len(test_cases)} 成功")
        return success_count == len(test_cases)
        
    except Exception as e:
        print(f"❌ 演示Function Tool测试失败: {e}")
        return False


async def test_simple_mcp_server():
    """测试简易MCP服务器"""
    print("\n=== 测试简易MCP服务器 ===")
    
    try:
        from tools.mcp_server.simple_mcp_server import SimpleMCPServer
        import aiohttp
        
        # 创建服务器实例
        server = SimpleMCPServer(port=8081)  # 使用不同端口避免冲突
        
        try:
            # 启动服务器
            await server.start_server()
            print("✅ MCP服务器启动成功")
            
            # 等待服务器完全启动
            await asyncio.sleep(0.5)
            
            # 测试健康检查
            async with aiohttp.ClientSession() as session:
                try:
                    async with session.get(f'http://localhost:8081/health') as resp:
                        health_data = await resp.json()
                        print(f"✅ 健康检查成功: {health_data}")
                except Exception as e:
                    print(f"❌ 健康检查失败: {e}")
                    return False
                
                # 测试能力查询
                try:
                    async with session.get(f'http://localhost:8081/capabilities') as resp:
                        capabilities = await resp.json()
                        print(f"✅ 能力查询成功: {len(capabilities.get('methods', []))} 个方法")
                except Exception as e:
                    print(f"❌ 能力查询失败: {e}")
                
                # 测试MCP协议请求
                test_requests = [
                    {
                        "name": "回显测试",
                        "data": {
                            "id": 1,
                            "method": "echo",
                            "params": {"message": "Hello MCP Server!"}
                        }
                    },
                    {
                        "name": "时间获取",
                        "data": {
                            "id": 2,
                            "method": "get_time",
                            "params": {"format": "iso"}
                        }
                    },
                    {
                        "name": "计算测试",
                        "data": {
                            "id": 3,
                            "method": "calculate",
                            "params": {"expression": "10 + 20 * 2"}
                        }
                    }
                ]
                
                success_count = 0
                
                for test_request in test_requests:
                    try:
                        async with session.post(
                            f'http://localhost:8081/mcp', 
                            json=test_request['data']
                        ) as resp:
                            result = await resp.json()
                            
                            if result.get('result', {}).get('success'):
                                print(f"✅ {test_request['name']} 成功: {result}")
                                success_count += 1
                            else:
                                print(f"❌ {test_request['name']} 失败: {result}")
                                
                    except Exception as e:
                        print(f"❌ {test_request['name']} 异常: {e}")
                
                print(f"\nMCP服务器测试结果: {success_count}/{len(test_requests)} 成功")
                
                return success_count == len(test_requests)
                
        finally:
            # 停止服务器
            await server.stop_server()
            print("✅ MCP服务器已停止")
            
    except Exception as e:
        print(f"❌ MCP服务器测试失败: {e}")
        return False


async def test_tool_library_integration():
    """测试工具库集成"""
    print("\n=== 测试工具库集成 ===")
    
    try:
        from core.toolscore.unified_tool_library import UnifiedToolLibrary
        from core.toolscore.interfaces import (
            FunctionToolSpec, ToolType, ToolkitCategory, ToolCapability
        )
        
        async with UnifiedToolLibrary() as tool_library:
            
            # 注册演示工具
            demo_spec = FunctionToolSpec(
                tool_id="test_demo_tool",
                name="测试演示工具",
                description="用于集成测试的演示工具",
                tool_type=ToolType.FUNCTION,
                toolkit_category=ToolkitCategory.GENERAL,
                capabilities=[
                    ToolCapability(
                        name="greet",
                        description="问候功能",
                        parameters={
                            "name": {"type": "string", "required": False}
                        },
                        examples=[{"name": "World"}]
                    )
                ],
                module_path="tools.examples.demo_function_tool",
                class_name="DemoFunctionTool"
            )
            
            # 注册工具
            result = await tool_library.register_function_tool(demo_spec)
            print(f"✅ 工具注册结果: {result}")
            
            # 发现工具包
            toolkits = await tool_library.discover_toolkits()
            print(f"✅ 发现工具包数量: {len(toolkits)}")
            
            # 发现具体工具
            tools = []
            if toolkits:
                for toolkit in toolkits:
                    toolkit_tools = await tool_library.discover_tools_by_toolkit(toolkit.toolkit_name)
                    tools.extend(toolkit_tools)
            
            print(f"✅ 发现工具数量: {len(tools)}")
            
            # 执行工具
            if tools:
                tool_id = tools[0].tool_id
                result = await tool_library.execute_tool(
                    tool_id, 
                    "greet", 
                    {"name": "集成测试"}
                )
                print(f"✅ 工具执行结果: {result}")
                
                return result.success if hasattr(result, 'success') else result.get('success', False)
            
            return True
            
    except Exception as e:
        print(f"❌ 工具库集成测试失败: {e}")
        return False


async def main():
    """主测试函数"""
    print("=" * 60)
    print("示例工具完整性测试")
    print("=" * 60)
    
    test_results = []
    
    # 1. 测试演示Function Tool
    result1 = await test_demo_function_tool()
    test_results.append(("演示Function Tool", result1))
    
    # 2. 测试简易MCP服务器
    result2 = await test_simple_mcp_server()
    test_results.append(("简易MCP服务器", result2))
    
    # 3. 测试工具库集成
    result3 = await test_tool_library_integration()
    test_results.append(("工具库集成", result3))
    
    # 输出测试总结
    print("\n" + "=" * 60)
    print("测试结果总结")
    print("=" * 60)
    
    total_tests = len(test_results)
    passed_tests = sum(1 for _, passed in test_results if passed)
    
    for test_name, passed in test_results:
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"{test_name:30} {status}")
    
    print(f"\n总计: {passed_tests}/{total_tests} 通过")
    
    if passed_tests == total_tests:
        print("🎉 所有测试通过！示例工具实现完整。")
        return 0
    else:
        print("⚠️  部分测试失败，需要检查实现。")
        return 1


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n测试被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n测试执行异常: {e}")
        sys.exit(1) 