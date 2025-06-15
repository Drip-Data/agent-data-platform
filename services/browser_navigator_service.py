import asyncio
import logging
from mcp_servers.browser_navigator_server.main import BrowserNavigatorMCPServer
from core.toolscore.managers.core_manager import CoreManager # 用于类型提示
from config import settings

logger = logging.getLogger(__name__)

async def start_browser_navigator_server(core_manager: CoreManager = None) -> BrowserNavigatorMCPServer:
    """
    启动 Browser Navigator MCP Server。
    如果提供了 core_manager，则将 Browser Navigator 实例传递给监控 API。
    返回 BrowserNavigatorMCPServer 实例。
    """
    logger.info("🚀 正在启动 Browser Navigator MCP Server...")
    browser_navigator_server = BrowserNavigatorMCPServer()
    # 修改为不尝试注册到ToolScore，因为ToolScore Service会手动注册
    browser_navigator_server.toolscore_endpoint = None 
    
    asyncio.create_task(browser_navigator_server.run())
    logger.info(f"✅ Browser Navigator MCP Server 已启动在端口 {settings.MCP_SERVER_PORT_RANGE_START + 1} (已手动注册)")

    # 🔧 修复：将Browser Navigator实例传递给监控API，实现直接调用
    # 注意：这里假设 core_manager 已经启动并且 monitoring_api 已经初始化
    if core_manager and hasattr(core_manager, 'monitoring_api') and core_manager.monitoring_api:
        core_manager.monitoring_api.browser_navigator_server = browser_navigator_server
        logger.info("✅ Browser Navigator实例已传递给监控API")
    else:
        logger.warning("⚠️  无法将 Browser Navigator 实例传递给监控API，core_manager 或 monitoring_api 未就绪。")

    return browser_navigator_server

async def stop_browser_navigator_server(browser_navigator_server: BrowserNavigatorMCPServer):
    """
    停止 Browser Navigator MCP Server。
    """
    # BrowserNavigatorMCPServer 可能没有明确的 stop 方法，但其 run() 是一个无限循环
    # 实际停止可能需要更复杂的信号处理或外部控制
    # 这里暂时不实现复杂的停止逻辑，因为其作为子任务运行
    logger.info("Browser Navigator MCP Server 停止逻辑（如果需要）")