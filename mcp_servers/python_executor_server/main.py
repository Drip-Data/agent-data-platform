#!/usr/bin/env python3
"""
Python Executor MCP Server
独立的Python代码执行服务，通过MCP协议与toolscore通信
"""

import asyncio
import logging
import os
from typing import Dict, Any, List
from uuid import uuid4

from core.toolscore.interfaces import ToolCapability, ToolType, ExecutionResult
from core.toolscore.mcp_server import MCPServer
from runtimes.reasoning.tools.python_executor_tool import PythonExecutorTool

logger = logging.getLogger(__name__)

class PythonExecutorMCPServer:
    """Python执行器MCP服务器"""
    
    def __init__(self):
        self.python_tool = PythonExecutorTool()
        self.server_name = "python_executor_server"
        self.server_id = "python-executor-mcp-server"
        self.endpoint = "ws://0.0.0.0:8083/mcp"
        self.toolscore_endpoint = os.getenv('TOOLSCORE_ENDPOINT', 'ws://localhost:8081/websocket')
        
    def get_capabilities(self) -> List[ToolCapability]:
        """获取Python工具的所有能力"""
        return [
            ToolCapability(
                name="python_execute",
                description="执行Python代码",
                parameters={
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
                examples=[
                    {"code": "print('Hello, World!')"},
                    {"code": "import math\nresult = math.sqrt(16)\nprint(f'平方根: {result}')"},
                    {"code": "data = [1, 2, 3, 4, 5]\nprint(f'平均值: {sum(data) / len(data)}')", "timeout": 10}
                ]
            ),
            ToolCapability(
                name="python_analyze",
                description="使用pandas分析数据",
                parameters={
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
                examples=[
                    {"data": [1, 2, 3, 4, 5], "operation": "describe"}
                ]
            ),
            ToolCapability(
                name="python_visualize", 
                description="创建数据可视化图表",
                parameters={
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
                examples=[
                    {"data": [1, 2, 3, 4, 5], "plot_type": "line"}
                ]
            ),
            ToolCapability(
                name="python_install_package",
                description="安装Python包",
                parameters={
                    "package_name": {
                        "type": "string",
                        "description": "要安装的包名",
                        "required": True
                    }
                },
                examples=[
                    {"package_name": "requests"}
                ]
            )
        ]
    
    async def handle_tool_action(self, action: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """处理工具动作执行"""
        try:
            logger.info(f"Executing Python tool action: {action} with params: {parameters}")

            result = {}
            if action == "python_execute":
                code = parameters.get("code", "")
                timeout = parameters.get("timeout", 30)
                result = await self.python_tool.execute_code(code, timeout)
                
            elif action == "python_analyze":
                data = parameters.get("data")
                operation = parameters.get("operation", "describe")
                result = await self.python_tool.analyze_data(data, operation)
                
            elif action == "python_visualize":
                data = parameters.get("data")
                plot_type = parameters.get("plot_type", "line")
                title = parameters.get("title", "Data Visualization")
                save_path = parameters.get("save_path")
                result = await self.python_tool.create_visualization(data, plot_type, title, save_path)
                
            elif action == "python_install_package":
                package_name = parameters.get("package_name", "")
                result = await self.python_tool.install_package(package_name)
                
            else:
                return {
                    "success": False,
                    "data": None,
                    "error_message": f"Unsupported action: {action}",
                    "error_type": "UnsupportedAction"
                }

            # 统一构建响应格式，确保符合ExecutionResult的结构
            response_data = None
            if result.get("success"):
                if action == "python_execute":
                    response_data = {
                        "stdout": result.get("stdout", ""),
                        "stderr": result.get("stderr", ""),
                        "return_code": result.get("return_code", 0)
                    }
                else:
                    # 对于其他成功的操作，将原始结果放入'result'字段
                    response_data = {"result": result.get("result", result.get("output"))}

            return {
                "success": result.get("success", False),
                "data": response_data,
                "error_message": result.get("error", ""),
                "error_type": result.get("error_type", "")
            }
                
        except Exception as e:
            logger.error(f"Python tool execution failed for {action}: {e}", exc_info=True)
            return {
                "success": False,
                "data": None,
                "error_message": str(e),
                "error_type": "PythonToolError"
            }

    async def run(self):
        """启动MCP服务器"""
        logger.info(f"Starting {self.server_name}...")
        
        # 创建MCP服务器
        mcp_server = MCPServer(
            server_name=self.server_name,
            server_id=self.server_id,
            description="Python代码执行和数据分析工具服务器",
            capabilities=self.get_capabilities(),
            tool_type=ToolType.MCP_SERVER,
            endpoint=self.endpoint,
            toolscore_endpoint=self.toolscore_endpoint
        )
        
        # 注册工具动作处理器
        mcp_server.register_tool_action_handler(self.handle_tool_action)
        
        # 启动服务器
        await mcp_server.start()

async def main():
    """主函数"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    server = PythonExecutorMCPServer()
    await server.run()

if __name__ == "__main__":
    asyncio.run(main())