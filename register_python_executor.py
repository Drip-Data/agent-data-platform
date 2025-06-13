#!/usr/bin/env python3
"""
注册 Python 执行器 MCP 服务器
"""

import asyncio
import aiohttp
import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def register_python_executor():
    """注册 Python 执行器 MCP 服务器"""
    
    # Python 执行器服务器规范
    server_spec = {
        "tool_id": "python_executor_server",
        "name": "Python 执行器",
        "description": "执行 Python 代码、数据分析和可视化",
        "endpoint": "ws://localhost:8083/mcp",  # 使用不同的端口
        "capabilities": [
            {
                "name": "python_execute",
                "description": "执行Python代码",
                "parameters": {
                    "code": {
                        "type": "string",
                        "description": "要执行的Python代码",
                        "required": True
                    },
                    "timeout": {
                        "type": "integer", 
                        "description": "执行超时时间（秒），默认30秒",
                        "required": False
                    }
                },
                "examples": [
                    {"code": "print('Hello, World!')"},
                    {"code": "import math\nresult = math.sqrt(16)\nprint(f'平方根: {result}')"}
                ]
            },
            {
                "name": "python_analyze",
                "description": "使用pandas分析数据",
                "parameters": {
                    "data": {
                        "type": "any",
                        "description": "要分析的数据",
                        "required": True
                    },
                    "operation": {
                        "type": "string",
                        "description": "分析操作类型",
                        "required": False
                    }
                },
                "examples": [
                    {"data": [1, 2, 3, 4, 5], "operation": "describe"}
                ]
            },
            {
                "name": "python_visualize", 
                "description": "创建数据可视化图表",
                "parameters": {
                    "data": {
                        "type": "any",
                        "description": "要可视化的数据",
                        "required": True
                    },
                    "plot_type": {
                        "type": "string",
                        "description": "图表类型",
                        "required": False
                    }
                },
                "examples": [
                    {"data": [1, 2, 3, 4, 5], "plot_type": "line"}
                ]
            },
            {
                "name": "python_install_package",
                "description": "安装Python包",
                "parameters": {
                    "package_name": {
                        "type": "string",
                        "description": "要安装的包名",
                        "required": True
                    }
                },
                "examples": [
                    {"package_name": "requests"}
                ]
            }
        ],
        "tags": ["python", "code", "execution", "data-analysis", "visualization"],
        "server_config": {},
        "connection_params": {"timeout": 30},
        "enabled": True
    }
    
    # 注册请求数据
    registration_data = {
        "server_spec": server_spec
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            # 发送注册请求到监控 API
            async with session.post(
                'http://localhost:8082/admin/mcp/register',
                json=registration_data,
                headers={'Content-Type': 'application/json'}
            ) as response:
                
                if response.status == 200:
                    result = await response.json()
                    if result.get('success'):
                        logger.info("✅ Python 执行器 MCP 服务器注册成功!")
                        logger.info(f"服务器 ID: {result.get('tool_id', 'unknown')}")
                        return True
                    else:
                        logger.error(f"❌ 注册失败: {result.get('message', 'Unknown error')}")
                        return False
                else:
                    error_text = await response.text()
                    logger.error(f"❌ HTTP 错误 {response.status}: {error_text}")
                    return False
                    
    except Exception as e:
        logger.error(f"❌ 注册时发生错误: {e}")
        return False

async def check_registration():
    """检查注册状态"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get('http://localhost:8082/tools') as response:
                if response.status == 200:
                    result = await response.json()
                    tools = result.get('tools', [])
                    
                    python_tools = [tool for tool in tools if 'python' in tool.get('name', '').lower()]
                    
                    if python_tools:
                        logger.info("✅ 找到已注册的 Python 工具:")
                        for tool in python_tools:
                            logger.info(f"  - {tool.get('name')}: {tool.get('description')}")
                    else:
                        logger.info("ℹ️  未找到已注册的 Python 工具")
                    
                    return tools
                else:
                    logger.error(f"❌ 无法获取工具列表: HTTP {response.status}")
                    return []
    except Exception as e:
        logger.error(f"❌ 检查注册状态时发生错误: {e}")
        return []

async def main():
    """主函数"""
    logger.info("开始重新注册 Python 执行器 MCP 服务器...")
    
    # 首先检查当前注册状态
    logger.info("检查当前工具注册状态...")
    await check_registration()
    
    # 注册 Python 执行器
    success = await register_python_executor()
    
    if success:
        logger.info("等待一下，然后检查注册结果...")
        await asyncio.sleep(2)
        await check_registration()
    else:
        logger.error("注册失败")

if __name__ == "__main__":
    asyncio.run(main()) 