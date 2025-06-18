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
from .python_executor_tool import PythonExecutorTool
from .enhanced_sandbox_executor import enhanced_executor
from core.config_manager import ConfigManager # 导入ConfigManager

logger = logging.getLogger(__name__)

class PythonExecutorMCPServer:
    """Python执行器MCP服务器"""
    
    def __init__(self, config_manager: ConfigManager):
        self.python_tool = PythonExecutorTool()
        self.server_name = "python_executor_server"
        self.server_id = "python-executor-mcp-server"
        self.config_manager = config_manager
        
        # 从配置中获取端口，优先使用动态分配的端口
        ports_config = self.config_manager.get_ports_config()
        
        # 检查是否有动态分配的端口（由MCP启动器设置）
        dynamic_port = os.getenv('PYTHON_EXECUTOR_SERVER_PORT')
        if dynamic_port:
            python_executor_port = int(dynamic_port)
            logger.info(f"使用动态分配端口: {python_executor_port}")
        else:
            python_executor_port = ports_config['mcp_servers']['python_executor']['port']
            logger.info(f"使用配置文件端口: {python_executor_port}")
        
        toolscore_mcp_port = ports_config['mcp_servers']['toolscore_mcp']['port']

        # 监听地址使用 0.0.0.0 以接受所有网卡，但 **注册给 ToolScore 的地址** 必须是客户端可访问的
        listen_host = os.getenv("PYTHON_EXECUTOR_LISTEN_HOST", "0.0.0.0")
        public_host = os.getenv("PYTHON_EXECUTOR_HOST", "localhost")
        
        self.endpoint = f"ws://{public_host}:{python_executor_port}"        # 保存监听信息供 MCPServer 使用
        self._listen_host = listen_host
        self._listen_port = python_executor_port
        
        self.toolscore_endpoint = os.getenv('TOOLSCORE_ENDPOINT', f'ws://localhost:{toolscore_mcp_port}/websocket')
        
        # 添加日志以确认端口和端点信息
        logger.info(f"PythonExecutorMCPServer initialized:")
        logger.info(f"  Server Name: {self.server_name}")
        logger.info(f"  Server ID: {self.server_id}")
        logger.info(f"  Listen Host: {self._listen_host}")
        logger.info(f"  Listen Port: {self._listen_port}")
        logger.info(f"  Public Endpoint: {self.endpoint}")
        logger.info(f"  ToolScore Endpoint: {self.toolscore_endpoint}")
        
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
            ),
            # 新增增强沙箱功能
            ToolCapability(
                name="python_execute_enhanced",
                description="在增强沙箱中执行Python代码，支持会话、调试和语法检查",
                parameters={
                    "code": {
                        "type": "string",
                        "description": "要执行的Python代码",
                        "required": True
                    },
                    "session_id": {
                        "type": "string",
                        "description": "会话ID，用于多轮执行和调试",
                        "required": False
                    },
                    "timeout": {
                        "type": "integer", 
                        "description": "执行超时时间（秒），默认30秒",
                        "required": False
                    },
                    "enable_debug": {
                        "type": "boolean",
                        "description": "是否启用调试模式（获取变量状态）",
                        "required": False
                    }
                },
                examples=[
                    {"code": "x = 42; print(f'x = {x}')", "session_id": "debug-session-1", "enable_debug": True},
                    {"code": "print('Hello Enhanced Sandbox!')", "timeout": 10}
                ]
            ),
            ToolCapability(
                name="python_check_syntax",
                description="检查Python代码语法",
                parameters={
                    "code": {
                        "type": "string",
                        "description": "要检查的Python代码",
                        "required": True
                    }
                },
                examples=[
                    {"code": "print('Hello, World!')"},
                    {"code": "print('missing quote)"}
                ]
            ),
            ToolCapability(
                name="python_session_info",
                description="获取调试会话信息",
                parameters={
                    "session_id": {
                        "type": "string",
                        "description": "会话ID",
                        "required": True
                    }
                },
                examples=[
                    {"session_id": "debug-session-1"}
                ]
            ),
            ToolCapability(
                name="python_close_session",
                description="关闭调试会话",
                parameters={
                    "session_id": {
                        "type": "string",
                        "description": "会话ID",
                        "required": True
                    }
                },
                examples=[
                    {"session_id": "debug-session-1"}
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
            
            # 新增增强沙箱功能处理
            elif action == "python_execute_enhanced":
                code = parameters.get("code", "")
                session_id = parameters.get("session_id")
                timeout = parameters.get("timeout", 30)
                enable_debug = parameters.get("enable_debug", False)
                
                enhanced_result = await enhanced_executor.execute_code(
                    code=code,
                    session_id=session_id,
                    timeout=timeout,
                    enable_debug=enable_debug
                )
                
                # 转换增强结果格式
                result = {
                    "success": enhanced_result.success,
                    "stdout": enhanced_result.stdout,
                    "stderr": enhanced_result.stderr,
                    "return_code": enhanced_result.return_code,
                    "execution_time": enhanced_result.execution_time,
                    "session_id": enhanced_result.session_id,
                    "variables": enhanced_result.variables,
                    "suggestions": enhanced_result.suggestions,
                    "syntax_check": {
                        "is_valid": enhanced_result.syntax_check.is_valid if enhanced_result.syntax_check else True,
                        "errors": [{"line": err.line, "column": err.column, "message": err.message, "type": err.error_type} 
                                 for err in enhanced_result.syntax_check.errors] if enhanced_result.syntax_check else [],
                        "warnings": enhanced_result.syntax_check.warnings if enhanced_result.syntax_check else [],
                        "suggestions": enhanced_result.syntax_check.suggestions if enhanced_result.syntax_check else []
                    }
                }
            
            elif action == "python_check_syntax":
                code = parameters.get("code", "")
                syntax_result = enhanced_executor.syntax_analyzer.analyze_syntax(code)
                
                result = {
                    "success": True,
                    "is_valid": syntax_result.is_valid,
                    "errors": [{"line": err.line, "column": err.column, "message": err.message, "type": err.error_type} 
                             for err in syntax_result.errors],
                    "warnings": syntax_result.warnings,
                    "suggestions": syntax_result.suggestions
                }
            
            elif action == "python_session_info":
                session_id = parameters.get("session_id", "")
                session_info = await enhanced_executor.get_session_info(session_id)
                
                if session_info:
                    result = {
                        "success": True,
                        "session_info": session_info
                    }
                else:
                    result = {
                        "success": False,
                        "error": f"Session not found: {session_id}"
                    }
            
            elif action == "python_close_session":
                session_id = parameters.get("session_id", "")
                closed = await enhanced_executor.close_session(session_id)
                
                result = {
                    "success": closed,
                    "message": f"Session {session_id} {'closed' if closed else 'not found'}"
                }
                
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
        
        # 在启动之前，覆盖其监听地址，防止绑定到不可用端口
        # MCPServer.start() 会解析 endpoint 字符串，只关心端口；因此额外在环境变量中覆盖端口足够。
        os.environ["PYTHON_EXECUTOR_BIND_HOST"] = self._listen_host
        
        logger.info(f"Attempting to start MCPServer for {self.server_name} at {self.endpoint}...")
        try:
            await mcp_server.start()
            logger.info(f"MCPServer for {self.server_name} started successfully.")
        except Exception as e:
            logger.error(f"Failed to start MCPServer for {self.server_name}: {e}", exc_info=True)
            raise # Re-raise the exception to propagate the failure

async def main():
    """主函数"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # 初始化ConfigManager
    from core.config_manager import ConfigManager
    config_manager = ConfigManager()
    
    server = PythonExecutorMCPServer(config_manager)
    await server.run()

if __name__ == "__main__":
    asyncio.run(main())