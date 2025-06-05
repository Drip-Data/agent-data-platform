import logging
import asyncio
from typing import Dict, Any, List
from uuid import uuid4
from fastapi import FastAPI, Request, HTTPException
from core.toolscore.interfaces import ToolCapability, ToolType, ExecutionResult
from core.toolscore.mcp_server import MCPServer
from core.toolscore.mcp_client import MCPToolClient
from runtimes.reasoning.tools.python_executor_tool import PythonExecutorTool

logger = logging.getLogger(__name__)

class PythonExecutorMCPServer:
    """
    Python 执行器 MCP Server，提供 Python 代码执行、数据分析、可视化和包安装能力。
    """
    
    def __init__(self, toolscore_url: str): # 移除 app 参数
        self.python_tool = PythonExecutorTool()
        self.toolscore_client = MCPToolClient(toolscore_url)
        self.server_name = "python_executor_server"
        self.server_url = "http://localhost:8081" # 假设此服务运行在8081端口
        self.server_id = str(uuid4()) # 为 MCP Server 生成一个唯一的 ID
        self.mcp_server_instance = None # 用于存储 MCPServer 实例
        
    async def _execute_tool(self, action: str, params: Dict[str, Any]) -> ExecutionResult:
        """
        内部工具执行逻辑，根据 action 调用相应的 PythonExecutorTool 方法。
        """
        try:
            result = {}
            if action == "python_execute":
                code = params.get("code", "")
                timeout = params.get("timeout", 30)
                result = await self.python_tool.execute_code(code, timeout)
                
            elif action == "python_analyze":
                data = params.get("data")
                operation = params.get("operation", "describe")
                result = await self.python_tool.analyze_data(data, operation)
                
            elif action == "python_visualize":
                data = params.get("data")
                plot_type = params.get("plot_type", "line")
                title = params.get("title", "Data Visualization")
                save_path = params.get("save_path")
                result = await self.python_tool.create_visualization(data, plot_type, title, save_path)
                
            elif action == "python_install_package":
                package_name = params.get("package_name", "")
                result = await self.python_tool.install_package(package_name)
                
            else:
                return ExecutionResult(
                    success=False,
                    error_message=f"Unsupported action: {action}",
                    error_type="UnsupportedAction"
                )
            
            return ExecutionResult(
                success=result.get("success", False),
                data=result.get("output", ""),
                error_message=result.get("error", ""),
                error_type=result.get("error_type", "")
            )
                
        except Exception as e:
            logger.error(f"Python tool execution failed for {action}: {e}")
            return ExecutionResult(
                success=False,
                error_message=str(e),
                error_type="PythonToolError"
            )

    async def wait_for_server_instance(self):
        """等待 MCPServer 实例被初始化"""
        while self.mcp_server_instance is None:
            await asyncio.sleep(0.1) # 短暂等待
        logger.info("MCPServer instance is ready.")

    def get_capabilities(self) -> List[ToolCapability]:
        """
        获取 Python 工具的所有能力，用于注册到 toolscore。
        """
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
                    {"code": "import math\nresult = math.sqrt(16)\nprint(f'平方根结果: {result}')"},
                    {"code": "data = [1, 2, 3, 4, 5]\nprint(f'平均值: {sum(data) / len(data)}')", "timeout": 10}
                ]
            ),
            ToolCapability(
                name="python_analyze",
                description="使用pandas分析数据",
                parameters={
                    "data": {
                        "type": "any",
                        "description": "要分析的数据（列表、字典或其他格式）",
                        "required": True
                    },
                    "operation": {
                        "type": "string",
                        "description": "分析操作类型：describe(描述统计), info(数据信息), head(前几行), tail(后几行)",
                        "required": False
                    }
                },
                examples=[
                    {"data": [1, 2, 3, 4, 5], "operation": "describe"},
                    {"data": {"name": ["Alice", "Bob"], "age": [25, 30]}, "operation": "info"},
                    {"data": [[1, 2], [3, 4], [5, 6]], "operation": "head"}
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
                        "description": "图表类型：line(折线图), bar(柱状图), scatter(散点图), pie(饼图), hist(直方图)",
                        "required": False
                    },
                    "title": {
                        "type": "string",
                        "description": "图表标题",
                        "required": False
                    },
                    "save_path": {
                        "type": "string",
                        "description": "图片保存路径",
                        "required": False
                    }
                },
                examples=[
                    {"data": [1, 2, 3, 4, 5], "plot_type": "line", "title": "趋势图"},
                    {"data": {"A": 10, "B": 20, "C": 15}, "plot_type": "bar"},
                    {"data": [[1, 2], [2, 3], [3, 5]], "plot_type": "scatter", "save_path": "/app/output/chart.png"}
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
                    {"package_name": "requests"},
                    {"package_name": "beautifulsoup4"},
                    {"package_name": "scikit-learn"}
                ]
            )
        ]

    async def run(self):
        """
        启动 MCP Server 并注册到 toolscore。
        """
        logging.basicConfig(level=logging.INFO)
        logger.info(f"Starting {self.server_name} MCP Server...")
        
        # 创建并启动 MCP Server
        mcp_server = MCPServer(
            server_name=self.server_name,
            server_id=self.server_id,
            description=f"MCP Server for {self.server_name}",
            capabilities=self.get_capabilities(),
            tool_type=ToolType.MCP_SERVER,
            endpoint=self.server_url,
            toolscore_endpoint=self.toolscore_client.toolscore_endpoint
        )
        
        # 注册工具动作处理函数
        mcp_server.register_tool_action_handler(self._execute_tool)
        
        # 启动 MCP Server
        await mcp_server.start()
        self.mcp_server_instance = mcp_server # 存储 MCPServer 实例
        # 注意：这里不能直接设置 app.state，因为 app 实例不在类范围内。
        # 必须在 startup_event 中设置。

# 全局 FastAPI 应用实例
app = FastAPI()

# 在应用启动时初始化并运行 MCP Server
@app.on_event("startup")
async def startup_event():
    toolscore_url = "ws://toolscore:8080/websocket" # 假设 toolscore 运行在 8080 端口
    global python_executor_mcp_server
    python_executor_mcp_server = PythonExecutorMCPServer(toolscore_url)
    app.state.python_executor_mcp_server = python_executor_mcp_server
    asyncio.create_task(python_executor_mcp_server.run())
    # 等待 MCPServer 实例初始化完成
    await python_executor_mcp_server.wait_for_server_instance()

# 健康检查端点
@app.get("/health")
async def health_check():
    return {"status": "healthy"}

# MCP Server 的 WebSocket 端点
@app.websocket("/mcp")
async def websocket_endpoint(websocket: websockets.WebSocket):
    if hasattr(app.state, 'python_executor_mcp_server') and \
       app.state.python_executor_mcp_server.mcp_server_instance:
        await app.state.python_executor_mcp_server.mcp_server_instance.websocket_handler(websocket, "/mcp")
    else:
        raise HTTPException(status_code=503, detail="Python Executor MCP Server not initialized.")