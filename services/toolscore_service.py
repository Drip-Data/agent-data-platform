import logging
import os
from typing import Dict, Optional
import threading

# 导入ToolScore相关模块
from core.toolscore.core_manager import CoreManager
from core.toolscore.unified_tool_library import UnifiedToolLibrary

logger = logging.getLogger(__name__)

# 全局变量
core_manager = None
tool_library = None
toolscore_server = None
toolscore_thread = None

def initialize(config: Optional[Dict] = None):
    """初始化ToolScore服务"""
    global core_manager, tool_library
    
    if config is None:
        config = {}
    
    logger.info("正在初始化ToolScore服务...")
    
    # 创建UnifiedToolLibrary实例（它会自动创建CoreManager）
    tool_library = UnifiedToolLibrary()
    
    # 获取内部的CoreManager实例
    core_manager = tool_library.core_manager
    
    logger.info("正在初始化工具库...")
    # 注意：这里不能直接await，需要在start()中进行异步初始化
    # await tool_library.initialize()
    
    # 获取工具数量 - 暂时返回0，实际初始化在start()中进行
    # all_tools = tool_library.get_all_tools()
    # tool_count = len(all_tools)
    
    logger.info(f"ToolScore服务初始化完成，实际初始化将在start()中进行")

def start():
    """启动ToolScore服务"""
    global toolscore_server, toolscore_thread
    
    if core_manager is None:
        raise RuntimeError("ToolScore未初始化，请先调用initialize()")
    
    logger.info("正在启动ToolScore服务...")
    
    # 首先异步初始化工具库
    import asyncio
    
    async def async_initialize():
        try:
            logger.info("正在异步初始化工具库...")
            await tool_library.initialize()
            logger.info("工具库初始化完成")
        except Exception as e:
            logger.error(f"工具库初始化失败: {e}")
            raise
    
    # 在当前线程中运行异步初始化
    try:
        asyncio.run(async_initialize())
    except Exception as e:
        logger.error(f"异步初始化失败: {e}")
        raise RuntimeError(f"ToolScore工具库初始化失败: {e}")
    
    # 创建并启动ToolScore MCP服务器
    from core.toolscore.mcp_server import ToolScoreMCPServer
    from core.toolscore.interfaces import ToolCapability, ToolType
    from core.config_manager import get_ports_config # 导入配置管理器

    # 从配置加载端口
    try:
        ports_config = get_ports_config()
        toolscore_mcp_config = ports_config.get('mcp_servers', {}).get('toolscore_mcp', {})
        host = os.getenv('TOOLSCORE_HOST', toolscore_mcp_config.get('host', '0.0.0.0'))
        port = int(os.getenv('TOOLSCORE_PORT', toolscore_mcp_config.get('port', 8081))) # 默认使用配置文件的8081
        websocket_path = toolscore_mcp_config.get('endpoint', '/websocket').lstrip('/')
        logger.info(f"ToolScore MCP server configured to use host: {host}, port: {port}, path: /{websocket_path}")
    except Exception as e:
        logger.warning(f"Failed to load port config for ToolScore MCP, using defaults. Error: {e}")
        host = os.getenv('TOOLSCORE_HOST', '0.0.0.0')
        port = int(os.getenv('TOOLSCORE_PORT', 8080)) # 回退到原始默认值8080以防万一
        websocket_path = "websocket"
        
    endpoint = f"ws://{host}:{port}/{websocket_path}"

    # 构造能力列表（最小能力集）
    capabilities = [
        ToolCapability(
            name="register_tool",
            description="注册新工具到工具库",
            parameters={},
            examples=[]
        ),
        ToolCapability(
            name="list_tools",
            description="列出所有可用工具",
            parameters={},
            examples=[]
        ),
        ToolCapability(
            name="execute_tool",
            description="执行指定工具",
            parameters={},
            examples=[]
        )
    ]

    toolscore_server = ToolScoreMCPServer(
        server_name="toolscore",
        server_id="toolscore-main-server",
        description="统一工具注册与调用中心",
        capabilities=capabilities,
        tool_type=ToolType.MCP_SERVER,
        endpoint=endpoint,
        toolscore_endpoint=None
    )
    # 注入unified_tool_library
    toolscore_server.unified_tool_library = tool_library

    # 在单独的线程中启动服务器
    def run_server():
        import asyncio
        asyncio.run(toolscore_server.start())

    toolscore_thread = threading.Thread(
        target=run_server,
        daemon=True
    )
    toolscore_thread.start()

    logger.info(f"ToolScore MCP服务器已启动于 {endpoint}")

def stop():
    """停止ToolScore服务"""
    global toolscore_server, toolscore_thread, core_manager, tool_library
    
    logger.info("正在停止ToolScore服务...")
    
    if toolscore_server:
        import asyncio
        asyncio.run(toolscore_server.stop())
        logger.info("ToolScore MCP服务器已停止")
    
    if toolscore_thread and toolscore_thread.is_alive():
        # 等待线程结束
        toolscore_thread.join(timeout=5)
        if toolscore_thread.is_alive():
            logger.warning("ToolScore线程未能正常结束")
    
    # 清理资源
    core_manager = None
    tool_library = None
    toolscore_server = None
    toolscore_thread = None
    
    logger.info("ToolScore服务已停止")

def health_check():
    """检查ToolScore服务健康状态"""
    if core_manager is None or tool_library is None:
        return {'status': 'error', 'message': 'ToolScore not initialized'}
    
    if toolscore_server is None or not toolscore_thread or not toolscore_thread.is_alive():
        return {'status': 'error', 'message': 'ToolScore MCP server not running'}
    
    # 获取加载的工具数量
    all_tools = tool_library.get_all_tools()
    tool_count = len(all_tools)
    
    return {
        'status': 'healthy',
        'tool_count': tool_count,
        'dynamic_tools': 0  # 暂时设为0，等确认实际方法后再修正
    }

def get_core_manager():
    """获取CoreManager实例"""
    if core_manager is None:
        raise RuntimeError("ToolScore未初始化，请先调用initialize()")
    return core_manager

def get_tool_library():
    """获取工具库实例"""
    if tool_library is None:
        raise RuntimeError("ToolScore未初始化，请先调用initialize()")
    return tool_library
