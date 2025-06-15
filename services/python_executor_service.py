import asyncio
import logging
from mcp_servers.python_executor_server.main import PythonExecutorMCPServer
from core.toolscore.managers.core_manager import CoreManager # 用于类型提示
from config import settings
from utils.port_manager import PortManager

logger = logging.getLogger(__name__)

async def start_python_executor_server(core_manager: CoreManager = None) -> PythonExecutorMCPServer:
    """
    启动 Python Executor MCP Server。
    如果提供了 core_manager，则将 Python Executor 实例传递给监控 API。
    返回 PythonExecutorMCPServer 实例。
    """
    logger.info("🚀 正在启动 Python Executor MCP Server...")
    # PythonExecutorMCPServer 需要端口参数，这里自动分配一个可用端口
    port_manager = PortManager()
    port = port_manager.find_available_port(start_port=settings.MCP_SERVER_PORT_RANGE_START,
                                            end_port=settings.MCP_SERVER_PORT_RANGE_END)
    if port is None:
        raise RuntimeError("无法找到可用端口启动 Python Executor MCP Server")

    python_executor_server = PythonExecutorMCPServer(port=port)
    # 修改为不尝试注册到ToolScore，因为ToolScore Service会手动注册
    python_executor_server.toolscore_endpoint = None 
    
    asyncio.create_task(python_executor_server.run())
    logger.info(f"✅ Python Executor MCP Server 已启动在端口 {port} (已手动注册)")

    # 🔧 修复：将Python Executor实例传递给监控API，实现直接调用
    # 注意：这里假设 core_manager 已经启动并且 monitoring_api 已经初始化
    if core_manager and hasattr(core_manager, 'monitoring_api') and core_manager.monitoring_api:
        core_manager.monitoring_api.python_executor_server = python_executor_server
        logger.info("✅ Python Executor实例已传递给监控API")
    else:
        logger.warning("⚠️  无法将 Python Executor 实例传递给监控API，core_manager 或 monitoring_api 未就绪。")

    return python_executor_server

async def stop_python_executor_server(python_executor_server: PythonExecutorMCPServer):
    """
    停止 Python Executor MCP Server。
    """
    # PythonExecutorMCPServer 没有明确的 stop 方法，但其 run() 是一个无限循环
    # 实际停止可能需要更复杂的信号处理或外部控制
    # 这里暂时不实现复杂的停止逻辑，因为其作为子任务运行
    logger.info("Python Executor MCP Server 停止逻辑（如果需要）")