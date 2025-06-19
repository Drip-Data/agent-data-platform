#!/usr/bin/env python3
import asyncio
import sys
import os

# 添加项目根目录到Python路径
sys.path.append('/Users/zhaoxiang/Documents/Datapresso/agent-data-platform')

from mcp_servers.microsandbox_server.main import MicroSandboxMCPServer
from core.config_manager import ConfigManager

async def test_microsandbox():
    """直接测试MicroSandbox服务器的执行功能"""
    config_manager = ConfigManager()
    server = MicroSandboxMCPServer(config_manager)
    
    # 测试代码执行
    test_params = {
        "code": "print(9*9)"
    }
    
    print("Testing MicroSandbox execution...")
    result = await server.handle_tool_action("microsandbox_execute", test_params)
    print(f"Result: {result}")
    
    # 清理
    await server.cleanup()

if __name__ == "__main__":
    asyncio.run(test_microsandbox())