import logging
import os
from typing import Dict, Optional
import threading
import asyncio

from core.toolscore.core_manager import CoreManager
from core.toolscore.unified_tool_library import UnifiedToolLibrary
from core.config_manager import ConfigManager
from core.toolscore.mcp_server import ToolScoreMCPServer
from core.toolscore.interfaces import ToolCapability, ToolType
from services.mcp_server_launcher import find_available_port # 导入 find_available_port

logger = logging.getLogger(__name__)

# 全局变量
core_manager: Optional[CoreManager] = None
tool_library: Optional[UnifiedToolLibrary] = None
toolscore_server: Optional[ToolScoreMCPServer] = None
toolscore_thread: Optional[threading.Thread] = None
_config_manager: Optional[ConfigManager] = None
_http_api_thread: Optional[threading.Thread] = None

def initialize(config_manager: ConfigManager):
    """初始化ToolScore服务"""
    global core_manager, tool_library, _config_manager
    
    _config_manager = config_manager
    
    logger.info("正在初始化ToolScore服务...")
    
    tool_library = UnifiedToolLibrary(config_manager=_config_manager)
    core_manager = tool_library.core_manager
    
    logger.info("ToolScore服务初始化完成（异步初始化将在start()中进行）")

def get_tool_library() -> Optional[UnifiedToolLibrary]:
    """获取ToolScore工具库实例"""
    return tool_library

def start():
    """启动ToolScore服务"""
    global toolscore_server, toolscore_thread, _http_api_thread
    
    if core_manager is None or _config_manager is None or tool_library is None:
        raise RuntimeError("ToolScore未初始化，请先调用initialize()并传入ConfigManager实例")
    
    logger.info("正在启动ToolScore服务...")
    
    # 同步初始化工具库，确保在服务启动前完成
    logger.info("正在初始化工具库...")
    assert tool_library is not None, "Tool library should be initialized before async init"
    # 由于start()是同步函数，这里需要一个同步的方式来运行异步的tool_library.initialize()
    # 在生产环境中，这通常意味着整个启动流程是异步的。
    # 在测试环境中，我们可以利用pytest-asyncio的事件循环。
    # 但为了保持start()的同步性，我们可以在一个临时的事件循环中运行它，或者依赖外部调用者来await。
    # 考虑到toolscore_thread会创建自己的事件循环，我们可以在那里进行初始化。
    # 暂时移除这里的直接初始化，让toolscore_server在自己的线程中初始化其tool_library。
    # 确保toolscore_server的__init__或start方法中会调用tool_library.initialize()
    # 实际上，core/toolscore/mcp_server.py的MCPServer.start()已经包含了tool_library.initialize()
    # 所以这里的初始化是多余的，并且可能导致问题。
    logger.info("工具库初始化将在ToolScore MCP服务器线程中进行。")

    # HTTP API启动已禁用 - 使用配置回退工具推荐
    # 启用HTTP监控API
    logger.info("正在启动ToolScore HTTP API...")
    from core.toolscore.monitoring_api import ToolScoreMonitoringAPI
    # 从配置中获取ToolScore HTTP API的端口
    ports_config = _config_manager.get_ports_config()
    toolscore_http_port = ports_config['mcp_servers']['toolscore_http']['port']
    
    toolscore_api = ToolScoreMonitoringAPI(tool_library, toolscore_http_port)
    _http_api_thread = threading.Thread(target=asyncio.run, args=(toolscore_api.start(),), daemon=True)
    _http_api_thread.start()
    logger.info(f"ToolScore HTTP API已启动于端口: {toolscore_http_port}")

    # 创建并启动ToolScore MCP服务器 (这部分保持不变，因为它已经在单独的线程中)
    try:
        if _config_manager is None:
            raise RuntimeError("ConfigManager not initialized")
        ports_config = _config_manager.get_ports_config()
        toolscore_mcp_config = ports_config.get('mcp_servers', {}).get('toolscore_mcp', {})
        host = os.getenv('TOOLSCORE_HOST', toolscore_mcp_config.get('host', '0.0.0.0'))
        
        # 获取端口管理配置
        port_management_config = ports_config.get('port_management', {})
        auto_detect = port_management_config.get('auto_detect', False)
        
        # 优先从ports_config.yaml获取端口，如果未配置则使用默认值8090
        configured_port = int(os.getenv('TOOLSCORE_PORT', toolscore_mcp_config.get('port', 8090)))
        
        bind_port = configured_port # 默认使用配置的端口

        # 只有当全局 auto_detect 为 True 且 toolscore_mcp 明确允许 auto_detect_port 时，才进行动态分配
        if auto_detect and toolscore_mcp_config.get('auto_detect_port', False): # 默认不允许自动检测
            start_range = port_management_config.get('port_range_start', 8100)
            end_range = port_management_config.get('port_range_end', 8200)
            available_port = find_available_port(start_range, end_range)
            if available_port:
                bind_port = available_port
                logger.info(f"为 ToolScore MCP 服务器动态分配端口: {bind_port} (范围: {start_range}-{end_range})")
            else:
                logger.warning(f"未能为 ToolScore MCP 服务器找到可用端口，将使用配置的默认端口 {configured_port}")
                # 如果找不到可用端口，仍然使用配置的端口，但会记录警告
                bind_port = configured_port
        else:
            logger.info(f"ToolScore MCP 服务器不进行端口自动检测，使用配置端口: {configured_port}")
            # 如果不自动检测，bind_port 已经设置为 configured_port

        websocket_path = toolscore_mcp_config.get('endpoint', '/websocket').lstrip('/')
        logger.info(f"ToolScore MCP server configured to use host: {host}, port: {bind_port}, path: /{websocket_path}")
    except Exception as e:
        logger.warning(f"Failed to load port config for ToolScore MCP, using defaults. Error: {e}")
        host = os.getenv('TOOLSCORE_HOST', '0.0.0.0')
        bind_port = int(os.getenv('TOOLSCORE_PORT', 8090)) # 使用ports_config.yaml中的默认端口8090
        websocket_path = "websocket"
        
    endpoint = f"ws://{host}:{bind_port}/{websocket_path}" # 使用 bind_port 构建 endpoint

    capabilities = [
        ToolCapability(name="register_tool", description="注册新工具到工具库", parameters={}, examples=[]),
        ToolCapability(name="list_tools", description="列出所有可用工具", parameters={}, examples=[]),
        ToolCapability(name="execute_tool", description="执行指定工具", parameters={}, examples=[])
    ]

    # 创建一个Event来通知主线程服务器已启动
    server_started_event = asyncio.Event()

    # 创建一个Event来通知主线程服务器已启动
    server_started_event = asyncio.Event()

    # 在启动线程之前，先创建并赋值toolscore_server实例给全局变量
    # 这样测试fixture就可以立即访问到它
    global toolscore_server # 明确声明使用全局变量
    toolscore_server = ToolScoreMCPServer(
        server_name="toolscore",
        server_id="toolscore-main-server",
        description="统一工具注册与调用中心",
        capabilities=capabilities,
        tool_type=ToolType.MCP_SERVER,
        endpoint=endpoint,
        toolscore_endpoint=None,
        bind_port=bind_port, # 传递动态分配的端口
        server_started_event=server_started_event # 传递Event
    )
    toolscore_server.unified_tool_library = tool_library

    def run_server(server_instance: ToolScoreMCPServer, event: asyncio.Event):
        import asyncio
        # 在这里创建一个新的事件循环，并在其中运行服务器
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(server_instance.start())
        except Exception as e:
            logger.error(f"Error in ToolScore MCP server thread: {e}", exc_info=True)
            server_instance._is_healthy = False # 标记服务不健康
            server_instance._startup_error_message = str(e) # 存储错误信息
            # 即使失败也设置事件，让等待的代码知道启动尝试已完成
            if event:
                event.set()
        finally:
            loop.close()

    global toolscore_thread # 明确声明使用全局变量
    toolscore_thread = threading.Thread(
        target=run_server,
        args=(toolscore_server, server_started_event),
        daemon=True
    )
    logger.info("Starting ToolScore MCP server thread...")
    toolscore_thread.start()
    logger.info(f"ToolScore MCP server thread started, is_alive: {toolscore_thread.is_alive()}")

    # 在主线程中等待服务器启动事件
    # 注意：这里不能直接await server_started_event.wait()，因为start()是同步函数
    # 而是需要一个机制让主线程等待。在测试中，fixture会处理等待。
    # 对于生产环境，如果需要等待，start()函数本身需要是异步的，或者使用其他同步机制。
    # 暂时不在这里阻塞主线程，依赖测试fixture的等待。
    logger.info(f"ToolScore MCP服务器启动线程已启动，等待就绪信号...")
    # 移除此处的logger.info，因为它可能在服务器实际启动前打印
    # logger.info(f"ToolScore MCP服务器已启动于 {endpoint}")
    
    # 注意：HTTP API的启动现在在_async_init_and_start_http任务中处理

def stop():
    """停止ToolScore服务"""
    global toolscore_server, toolscore_thread, core_manager, tool_library, _http_api_thread
    
    logger.info("正在停止ToolScore服务...")
    
    # 1. 首先尝试优雅关闭WebSocket服务器
    if toolscore_server:
        try:
            if hasattr(toolscore_server, 'websocket_server') and toolscore_server.websocket_server:
                toolscore_server.websocket_server.close()
                logger.info("WebSocket服务器已关闭")
        except Exception as e:
            logger.warning(f"关闭WebSocket服务器时出错: {e}")
        
        # 尝试停止server的内部循环
        try:
            if hasattr(toolscore_server, '_is_running'):
                toolscore_server._is_running = False
        except Exception as e:
            logger.warning(f"停止server内部循环时出错: {e}")
            
        logger.info("ToolScore MCP服务器已停止")
    
    # 2. 强制停止线程
    threads_to_stop = [
        (toolscore_thread, "ToolScore MCP"),
        (_http_api_thread, "ToolScore HTTP API")
    ]
    
    for thread, name in threads_to_stop:
        if thread and thread.is_alive():
            logger.info(f"等待 {name} 线程停止...")
            thread.join(timeout=3)  # 减少超时时间
            
            if thread.is_alive():
                logger.warning(f"{name} 线程未能正常结束，尝试强制停止...")
                
                # 尝试强制停止线程（Python没有直接的线程终止方法）
                try:
                    import threading
                    import ctypes
                    
                    # 获取线程ID
                    thread_id = thread.ident
                    if thread_id:
                        # 尝试发送异常到线程（这是不安全的，但在关闭时可以使用）
                        res = ctypes.pythonapi.PyThreadState_SetAsyncExc(
                            ctypes.c_long(thread_id), 
                            ctypes.py_object(SystemExit)
                        )
                        if res > 1:
                            ctypes.pythonapi.PyThreadState_SetAsyncExc(
                                ctypes.c_long(thread_id), 
                                None
                            )
                        logger.info(f"强制终止 {name} 线程")
                except Exception as e:
                    logger.warning(f"强制停止 {name} 线程失败: {e}")

    # 3. 强制释放相关端口
    _force_release_toolscore_ports()

    # 4. 清理资源
    core_manager = None
    tool_library = None
    toolscore_server = None
    toolscore_thread = None
    _http_api_thread = None
    
    logger.info("ToolScore服务已停止")

def _force_release_toolscore_ports():
    """强制释放ToolScore相关端口"""
    toolscore_ports = [8088, 8089, 8081, 8082, 8080]  # ToolScore HTTP, MCP, 以及MCP服务器端口
    
    for port in toolscore_ports:
        try:
            import subprocess
            
            # 查找占用端口的进程
            result = subprocess.run(
                ['lsof', '-ti', f':{port}'], 
                capture_output=True, text=True, timeout=3
            )
            
            if result.returncode == 0 and result.stdout.strip():
                pids = result.stdout.strip().split('\n')
                for pid in pids:
                    try:
                        # 首先尝试TERM信号
                        subprocess.run(['kill', '-TERM', pid], timeout=2, check=False)
                        
                        # 等待一秒后检查进程是否还存在
                        import time
                        time.sleep(1)
                        
                        # 检查进程是否仍然存在
                        check_result = subprocess.run(
                            ['kill', '-0', pid], 
                            capture_output=True, timeout=1
                        )
                        
                        if check_result.returncode == 0:
                            # 进程仍然存在，使用KILL信号
                            subprocess.run(['kill', '-KILL', pid], timeout=2, check=False)
                            logger.info(f"强制释放端口 {port}，杀死进程 {pid}")
                        else:
                            logger.info(f"端口 {port} 进程 {pid} 已正常退出")
                            
                    except subprocess.TimeoutExpired:
                        logger.warning(f"释放端口 {port} 进程 {pid} 超时")
                    except Exception as e:
                        logger.warning(f"释放端口 {port} 进程 {pid} 失败: {e}")
        except Exception as e:
            logger.debug(f"检查端口 {port} 占用情况失败: {e}")  # 降级为debug，因为这不是关键错误

async def health_check(): # 将 health_check 定义为异步函数
    """检查ToolScore服务健康状态"""
    # 优先检查 ToolScore MCP 服务器的启动状态和错误信息
    if toolscore_server is None or not toolscore_thread or not toolscore_thread.is_alive():
        return {'status': 'error', 'message': 'ToolScore MCP server thread not running or server instance is None.'}

    if not toolscore_server._is_healthy:
        # 如果服务器报告不健康，直接返回其错误信息
        return {'status': 'error', 'message': f"ToolScore MCP server reported unhealthy: {toolscore_server._startup_error_message or 'No specific error message provided.'}"}

    # 其次检查 tool_library 是否初始化
    if tool_library is None or not tool_library.is_initialized:
        return {'status': 'error', 'message': 'ToolScore not initialized (tool_library is None or not fully initialized).'}
    
    # 确保 toolscore_server.unified_tool_library 存在且已初始化
    if toolscore_server.unified_tool_library is None or not toolscore_server.unified_tool_library.is_initialized:
        return {'status': 'error', 'message': 'ToolScore MCP server unified_tool_library is not initialized or not fully initialized.'}

    # 获取加载的工具数量，使用toolscore_server内部的unified_tool_library
    try:
        all_tools = await toolscore_server.unified_tool_library.get_all_tools() # 直接 await
        tool_count = len(all_tools)
    except Exception as e:
        return {'status': 'error', 'message': f"Failed to get tools from ToolScore server's library: {e}"}
    
    return {
        'status': 'healthy',
        'tool_count': tool_count,
        'dynamic_tools': 0,  # 暂时设为0，等确认实际方法后再修正
        'tool_recommendation': 'config_based'
    }
