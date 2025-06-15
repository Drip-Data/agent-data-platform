import asyncio
import logging
import aiohttp
from core.toolscore.managers.core_manager import CoreManager
from core.toolscore.managers.unified_tool_library import UnifiedToolLibrary
from core.toolscore.mcp.mcp_server import MCPServer
from core.toolscore.interfaces.toolscore_interfaces import ToolCapability, ToolType, MCPServerSpec
from core.redis.redis_manager import RedisManager # 导入 RedisManager 类型提示
from config import settings
from config.settings import TOOLSCORE_MCP_PORT, TOOLSCORE_MONITORING_PORT, TOOLSCORE_MCP_WS_URL, TOOLSCORE_HTTP_URL

logger = logging.getLogger(__name__)

async def start_toolscore_services(redis_manager: RedisManager) -> tuple[CoreManager, MCPServer, UnifiedToolLibrary]:
    """
    初始化并启动 ToolScore 相关的核心服务：
    CoreManager, UnifiedToolLibrary, ToolScore MCP Server。
    返回这些服务的实例。
    """
    logger.info("🚀 正在初始化 ToolScore 核心服务...")

    # 初始化核心管理器
    core_manager = CoreManager(redis_manager=redis_manager)
    await core_manager.initialize()
    logger.info("✅ CoreManager 已初始化")

    # 创建并初始化工具库
    redis_url = redis_manager.get_redis_url()
    tool_library = UnifiedToolLibrary(redis_url=redis_url, redis_manager=redis_manager)
    await tool_library.initialize()
    logger.info("✅ UnifiedToolLibrary 已初始化")

    # 注入工具库到监控API
    await core_manager.set_tool_library_for_monitoring(tool_library)
    logger.info("✅ UnifiedToolLibrary 已注入到 Monitoring API")

    # 启动 ToolScore MCP 服务器 (8081端口)
    toolscore_capabilities = [
        ToolCapability(
            name="register_tool",
            description="注册新工具到工具库",
            parameters={
                "tool_spec": {
                    "type": "object",
                    "description": "工具规范",
                    "required": True
                }
            },
            examples=[{"tool_spec": {"tool_id": "example_tool", "name": "示例工具"}}]
        ),
        ToolCapability(
            name="list_tools",
            description="列出所有可用工具",
            parameters={},
            examples=[{}]
        ),
        ToolCapability(
            name="execute_tool",
            description="执行指定工具",
            parameters={
                "tool_id": {
                    "type": "string",
                    "description": "工具ID",
                    "required": True
                },
                "action": {
                    "type": "string", 
                    "description": "工具动作",
                    "required": True
                },
                "parameters": {
                    "type": "object",
                    "description": "动作参数",
                    "required": False
                }
            },
            examples=[{"tool_id": "python_executor_server", "action": "python_execute", "parameters": {"code": "print('hello')"}}]
        )
    ]
    
    toolscore_server = MCPServer(
        server_name="toolscore",
        server_id="toolscore-main-server", 
        description="统一工具注册与调用中心",
        capabilities=toolscore_capabilities,
        tool_type=ToolType.MCP_SERVER,
        endpoint=TOOLSCORE_MCP_WS_URL,
        toolscore_endpoint=None  # 自己就是toolscore
    )
    
    # 设置工具库
    toolscore_server.unified_tool_library = tool_library
    
    # 启动 ToolScore MCP 服务器
    asyncio.create_task(toolscore_server.start())
    logger.info(f"✅ ToolScore MCP Server 已启动在端口 {TOOLSCORE_MCP_PORT}")

    # 直接注册Python Executor到工具库，避免WebSocket连接问题
    python_executor_spec = MCPServerSpec(
        tool_id="python-executor-mcp-server",
        name="python_executor_server",
        description="Python代码执行和数据分析工具服务器",
        tool_type=ToolType.MCP_SERVER,
        capabilities=[
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
                    {"code": "import math\nresult = math.sqrt(16)\nprint(f'平方根: {result}')"}
                ]
            )
        ],
        endpoint=f"ws://localhost:{settings.MCP_SERVER_PORT_RANGE_START}/mcp"
    )
    
    registration_result = await tool_library.register_mcp_server(python_executor_spec)
    if registration_result.success:
        logger.info("✅ Python Executor 已直接注册到工具库")
        # 同步在MCP连接注册表中登记，确保execute_tool时可用
        tool_library.mcp_server_registry.register_server(python_executor_spec.tool_id, python_executor_spec.endpoint)
    else:
        logger.error(f"❌ Python Executor 注册失败: {registration_result.error}")


    return core_manager, toolscore_server, tool_library

async def stop_toolscore_services(core_manager: CoreManager, toolscore_server: MCPServer):
    """
    停止 ToolScore 相关的核心服务。
    """
    if core_manager:
        await core_manager.stop()
        logger.info("CoreManager 已停止。")
    if toolscore_server:
        await toolscore_server.stop()
        logger.info("ToolScore MCP Server 已停止。")