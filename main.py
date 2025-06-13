import asyncio
import logging
import os
import sys

# Adjust system path to include the project's root directory for module resolution
# This assumes 'main.py' is in 'new_version/agent-data-platform/'
# and 'core', 'tools' are subdirectories of 'new_version/agent-data-platform/'
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT) # Add project root
# If core and tools are directly under PROJECT_ROOT, this is enough.
# If they are under a src-like dir, adjust sys.path.append(os.path.join(PROJECT_ROOT, "src"))


from core.config_service import ConfigService
from core.logging_service import setup_logging, LoggingService # Use LoggingService for get_logger
from core.persistence_service import PersistenceService
from core.toolscore.tool_registry import ToolRegistry
from core.toolscore.local_tool_server import LocalToolServerManager
from core.toolscore.local_tool_executor import LocalToolExecutor

# Example tools - ensure these paths are correct relative to PROJECT_ROOT
# e.g., if tools directory is directly under PROJECT_ROOT
try:
    from tools.python_executor_tool import PythonExecutorTool
    from tools.browser_navigator_tool import BrowserNavigatorTool, PLAYWRIGHT_AVAILABLE # Import PLAYWRIGHT_AVAILABLE
except ImportError as e:
    print(f"Error importing tools: {e}. Check PYTHONPATH and file locations.", file=sys.stderr)
    # Decide if this is a fatal error or if the application can run without some tools
    # For now, let it proceed and log, but in production, this might be fatal.
    PythonExecutorTool = None # type: ignore
    BrowserNavigatorTool = None # type: ignore
    PLAYWRIGHT_AVAILABLE = False # Assume not available if import fails


async def main_async():
    # Setup logging first
    # Use the LoggingService class to get a logger instance after setup
    log_service = setup_logging(log_level="INFO", app_name="agent-data-platform", use_json_format=False)
    logger = log_service.get_logger("main") # Get a logger instance from the service
    logger.info("正在启动Agent Data Platform (Async)...")

    persistence_service = None
    tool_registry_instance = None
    server_manager_instance = None
    tool_executor_instance = None

    try:
        # Initialize services
        config_service_instance = ConfigService()
        config = config_service_instance.get_config()
        logger.info(f"配置已加载: {config.app_name}, 日志级别: {config.log_level}")
        # Re-configure logging if config has a different level
        if config.log_level.upper() != logger.level: # type: ignore
             log_service.configure(log_level=config.log_level.upper(), app_name=config.app_name)
             logger.info(f"日志级别已根据配置更新为: {config.log_level.upper()}")


        persistence_service = PersistenceService()
        await asyncio.sleep(0.01) # Allow any async init in PersistenceService if present

        tool_registry_instance = ToolRegistry()
        # Explicitly load tools if your ToolRegistry requires it (e.g., if _load_tools was deferred)
        if hasattr(tool_registry_instance, 'load_tools_async'):
            await tool_registry_instance.load_tools_async()


        server_manager_instance = LocalToolServerManager()
        tool_executor_instance = LocalToolExecutor()

        # Create and register tools
        if PythonExecutorTool:
            python_tool = PythonExecutorTool()
            tool_registry_instance.register_tool_instance(python_tool) 
                                                                    
        if BrowserNavigatorTool:
            browser_tool = BrowserNavigatorTool() 
            tool_registry_instance.register_tool_instance(browser_tool)


        # Setup and start HTTP server for tools (example)
        # Ensure tool_server_port is correctly read from config
        http_server_port = config.tools.tool_server_port if config.tools else 8080
        http_server = server_manager_instance.create_http_server(name="AgentTools", port=http_server_port)

        # Register tools to the HTTP server
        if PythonExecutorTool and 'python_executor' in tool_registry_instance.tool_instances:
             http_server.register_tool(tool_registry_instance.tool_instances['python_executor'])
        if BrowserNavigatorTool and 'browser_navigator' in tool_registry_instance.tool_instances:
             http_server.register_tool(tool_registry_instance.tool_instances['browser_navigator'])


        await server_manager_instance.start_all_servers()

        logger.info("系统初始化完成。按 Ctrl+C 退出。")

        while True:
            await asyncio.sleep(3600) 

    except KeyboardInterrupt:
        logger.info("收到退出信号 (KeyboardInterrupt)，正在关闭...")
    except Exception as e:
        logger.error(f"应用启动或运行时发生严重错误: {e}", exc_info=True)
    finally:
        logger.info("开始执行关闭程序...")
        if server_manager_instance:
            logger.info("正在停止所有工具服务器...")
            await server_manager_instance.stop_all_servers()
        if tool_executor_instance:
            logger.info("正在关闭工具执行器...")
            await tool_executor_instance.close()
        if hasattr(tool_registry_instance, 'close') and tool_registry_instance: 
            logger.info("正在关闭工具注册表...")
            await tool_registry_instance.close() # type: ignore
        if persistence_service:
            logger.info("正在关闭持久化服务...")
            await persistence_service.close()

        if BrowserNavigatorTool and PLAYWRIGHT_AVAILABLE: # Check PLAYWRIGHT_AVAILABLE
            try:
                from tools.browser_navigator_tool import BrowserManager 
                if BrowserManager._instance: 
                    logger.info("正在关闭浏览器管理器 (main)...")
                    await BrowserManager._instance.stop() 
            except Exception as e_bm_stop:
                logger.error(f"关闭浏览器管理器时出错 (main): {e_bm_stop}")


        logger.info("系统已关闭。")
        await asyncio.sleep(0.5)


if __name__ == "__main__":
    asyncio.run(main_async())
