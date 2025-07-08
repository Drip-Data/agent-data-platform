import asyncio
import logging
import os
import threading
import subprocess
from typing import Dict, Optional, List, Any # 导入Any
import time
import json
import socket # 导入socket模块
from core.config_manager import ConfigManager
from core.toolscore.service_container import MCPServiceContainer
from core.toolscore.mcp_auto_registration import get_auto_registrar

logger = logging.getLogger(__name__)

# 全局变量
mcp_servers: List[str] = []
mcp_processes: Dict[str, subprocess.Popen] = {}
server_statuses: Dict[str, Dict[str, Any]] = {}
_config_manager: Optional[ConfigManager] = None
_service_container: Optional['MCPServiceContainer'] = None
_is_shutting_down = False
_restart_timers: Dict[str, threading.Timer] = {}

def find_available_port(start_port: int, end_port: int) -> Optional[int]:
    """
    在指定范围内查找一个可用的端口。
    """
    for port in range(start_port, end_port + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("0.0.0.0", port))
                return port
            except OSError:
                continue
    return None

def initialize(config_manager: ConfigManager, service_manager: 'ServiceManager', service_container: 'MCPServiceContainer' = None):
    """初始化MCP服务器启动器"""
    global mcp_servers, _config_manager, _service_container, _service_manager
    
    _config_manager = config_manager
    _service_container = service_container
    _service_manager = service_manager
    
    logger.info("正在初始化MCP服务器启动器...")
    
    # 从ConfigManager加载运行时配置，获取MCP服务器列表
    try:
        routing_config = _config_manager.load_routing_config()
        # 假设运行时配置中包含mcp_servers的列表
        # 这里需要根据实际的routing_config结构来获取mcp_servers
        # 暂时先使用一个默认的逻辑，后续根据实际配置调整
        mcp_servers = [
            runtime_name for runtime_name, runtime_config in routing_config.runtimes.items()
            if "mcp_server" in runtime_config.capabilities # 假设通过capabilities判断是否是mcp_server
        ]
        # 确保包含必要的MCP服务器
        if "microsandbox_server" not in mcp_servers:
            mcp_servers.append("microsandbox_server")  # 添加MicroSandbox MCP Server
        # browser_navigator_server已替换为browser_use_server
        if "browser_navigator_server" in mcp_servers:
            mcp_servers.remove("browser_navigator_server")
        # 添加 search_tool_server
        if "search_tool_server" not in mcp_servers:
            mcp_servers.append("search_tool_server")
        # 添加 browser_use_server
        if "browser_use_server" not in mcp_servers:
            mcp_servers.append("browser_use_server")
        # 添加 deepsearch_server
        if "deepsearch_server" not in mcp_servers:
            mcp_servers.append("deepsearch_server")
        # 移除已弃用的 python_executor_server
        if "python_executor_server" in mcp_servers:
            mcp_servers.remove("python_executor_server")

    except Exception as e:
        logger.warning(f"从ConfigManager加载MCP服务器列表失败: {e}，使用默认列表")
        mcp_servers = [
            'microsandbox_server',  # MicroSandbox MCP服务器
            'search_tool_server', # 搜索工具服务器
            'browser_use_server',  # Browser-Use AI浏览器自动化服务器 (替换browser_navigator_server)
            'deepsearch_server'  # 专业级深度搜索服务器
        ]
    
    logger.info(f"MCP服务器启动器初始化完成，配置了 {len(mcp_servers)} 个服务器: {mcp_servers}")

async def start():
    """启动所有MCP服务器"""
    global mcp_processes, server_statuses
    
    if not mcp_servers:
        logger.warning("没有配置MCP服务器，跳过启动")
        return
    
    logger.info("正在启动MCP服务器...")
    
    # 清空现有进程字典
    mcp_processes = {}
    server_statuses = {}
    
    # 🚀 并行启动所有服务器以提高启动速度
    logger.info(f"正在并行启动 {len(mcp_servers)} 个MCP服务器...")
    
    startup_tasks = []
    for server_name in mcp_servers:
        task = asyncio.create_task(_start_server(server_name))
        startup_tasks.append(task)
    
    # 等待所有服务器启动完成，设置合理的超时时间
    try:
        await asyncio.wait_for(
            asyncio.gather(*startup_tasks, return_exceptions=True),
            timeout=120  # 2分钟启动超时
        )
    except asyncio.TimeoutError:
        logger.warning("⚠️ MCP服务器启动超时，部分服务器可能未完全启动")
    
    # 统计启动成功的服务器
    successful_servers = [name for name, status in server_statuses.items() 
                         if status.get('status') == 'running']
    
    logger.info(f"✅ 成功启动 {len(successful_servers)}/{len(mcp_servers)} 个MCP服务器: {successful_servers}")


async def _start_server(server_name: str):
    """启动单个MCP服务器"""
    global mcp_processes, server_statuses
    
    if _config_manager is None:
        logger.error("ConfigManager未初始化，无法启动MCP服务器")
        server_statuses[server_name] = {'status': 'error', 'message': 'ConfigManager not initialized'}
        return

    logger.info(f"正在启动MCP服务器: {server_name}")
    
    # 检查是否是外部服务器
    ports_config = _config_manager.get_ports_config()
    server_config = None
    if 'mcp_servers' in ports_config:
        for key, value in ports_config['mcp_servers'].items():
            if key == server_name and isinstance(value, dict):
                server_config = value
                break
    
    # 如果是外部服务器，验证连接而不启动进程
    if server_config and server_config.get('type') == 'external':
        await _verify_external_server(server_name, server_config)
        return
    
    # 构建服务器目录路径
    # 假设mcp_servers都在项目根目录下的mcp_servers目录中
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    server_dir_absolute = os.path.join(project_root, 'mcp_servers', server_name)

    # 调试日志，输出CWD、路径信息
    logger.debug(f"[MCP启动器] 当前工作目录: {os.getcwd()}")
    logger.debug(f"[MCP启动器] server_name: {server_name}")
    logger.debug(f"[MCP启动器] server_dir (绝对用于操作): {server_dir_absolute}")

    # More detailed checks for the absolute path
    path_exists = os.path.exists(server_dir_absolute)
    logger.debug(f"[MCP启动器] os.path.exists({server_dir_absolute}) = {path_exists}")

    if path_exists:
        is_directory = os.path.isdir(server_dir_absolute)
        logger.debug(f"[MCP启动器] os.path.isdir({server_dir_absolute}) = {is_directory}")
        try:
            contents = os.listdir(server_dir_absolute)
            logger.debug(f"[MCP启动器] os.listdir({server_dir_absolute}) contents: {contents[:5]}") # Log first 5 items
        except Exception as e_listdir:
            logger.error(f"[MCP启动器] os.listdir({server_dir_absolute}) FAILED: {e_listdir}")
            is_directory = False # If listdir fails, treat as not a usable directory
    else:
        is_directory = False # If path doesn't exist, it's not a directory

    # 检查目录是否存在 (using the results of detailed checks)
    if not is_directory: # Check our derived is_directory flag
        logger.error(f"MCP服务器目录不存在或不是目录 (基于详细检查的绝对路径): {server_dir_absolute}. Exists: {path_exists}, IsDir: {os.path.isdir(server_dir_absolute) if path_exists else 'N/A'}")
        server_statuses[server_name] = {'status': 'error', 'message': 'Directory not found, not a directory, or not accessible'}
        return
    
    # 检查启动脚本 (using the absolute path)
    # Order of preference: start.sh, then main.py, then app.py
    script_to_try = ['start.sh', 'main.py', 'app.py']
    start_script = None

    for script_name in script_to_try:
        potential_script = os.path.join(server_dir_absolute, script_name)
        if os.path.exists(potential_script):
            start_script = potential_script
            logger.info(f"[MCP启动器] 找到启动脚本: {start_script}")
            break
    
    if start_script is None:
        logger.error(f"MCP服务器启动脚本 (start.sh, main.py, or app.py) 不存在于: {server_dir_absolute}")
        server_statuses[server_name] = {'status': 'error', 'message': 'Start script (start.sh, main.py, or app.py) not found'}
        return
    
    try:
        env = os.environ.copy() # 将env初始化移到try块的开头

        # microsandbox_server无需特殊环境变量配置

        # Determine the project root to add to PYTHONPATH
        project_root_for_pythonpath = os.path.abspath(os.path.join(server_dir_absolute, '..', '..'))
        logger.debug(f"[MCP启动器] Setting PYTHONPATH for subprocess to: {project_root_for_pythonpath}")
        
        # 构建启动命令
        if start_script.endswith('.sh'):
            cmd = ['sh', start_script] # start_script is now absolute
        else:
            # 对于Python脚本，使用模块格式运行
            relative_script_path = os.path.relpath(start_script, project_root_for_pythonpath)
            module_path_parts = list(os.path.splitext(relative_script_path)[0].split(os.sep))
            module_str = ".".join(module_path_parts)
            
            ports_config = _config_manager.get_ports_config()
            server_config = None
            # 尝试从ports_config中找到对应服务器的配置
            if 'mcp_servers' in ports_config:
                server_config = ports_config['mcp_servers'].get(server_name)

            port = None
            if server_config and 'port' in server_config:
                port = server_config['port']
                logger.info(f"[MCP启动器] 为 {server_name} 使用配置文件指定端口: {port}")
                # 检查端口是否可用
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    if s.connect_ex(('localhost', port)) == 0:
                        logger.warning(f"[MCP启动器] 端口 {port} 已被占用，尝试查找可用端口...")
                        port = find_available_port(port + 1, port + 100)
                        if not port:
                            logger.error(f"[MCP启动器] 无法为 {server_name} 找到可用端口")
                            server_statuses[server_name] = {'status': 'error', 'message': 'No available ports'}
                            return
                        logger.info(f"[MCP启动器] 为 {server_name} 分配了新端口: {port}")

            if port:
                env[f"{server_name.upper()}_PORT"] = str(port)

            cmd = ['python3', '-m', module_str]
            env['PYTHONPATH'] = project_root_for_pythonpath + os.pathsep + env.get('PYTHONPATH', '')
            
            # 处理端口分配逻辑
            if server_config and server_config.get('auto_start', True): # 默认auto_start为True
                port_management_config = ports_config.get('port_management', {})
                auto_detect = port_management_config.get('auto_detect', False)
                
                target_port = server_config.get('port')
                
                # 无论auto_detect是否为True，都优先使用配置文件中指定的端口
                if target_port:
                    logger.info(f"[MCP启动器] 为 {server_name} 使用配置文件指定端口: {target_port}")
                elif auto_detect:
                    # 如果配置文件中没有指定端口，并且启用了自动检测，则查找可用端口
                    start_range = port_management_config.get('port_range_start', 8088)
                    end_range = port_management_config.get('port_range_end', 8200)
                    
                    available_port = find_available_port(start_range, end_range)
                    if available_port:
                        target_port = available_port
                        logger.info(f"[MCP启动器] 为 {server_name} 动态分配端口: {target_port}")
                    else:
                        logger.warning(f"[MCP启动器] 未能为 {server_name} 找到可用端口，将不设置端口环境变量。")
                
                if target_port:
                    # 将端口作为环境变量传递给子进程
                    # 不同的MCP服务器可能通过不同的环境变量名获取端口
                    # 这里根据server_name动态设置环境变量名
                    env_var_name = f"{server_name.upper()}_PORT"
                    env[env_var_name] = str(target_port)
                    logger.debug(f"[MCP启动器] 设置环境变量 {env_var_name}={target_port} 给 {server_name}")
                else:
                    logger.warning(f"[MCP启动器] {server_name} 没有配置端口，也未能动态分配。")
            else:
                logger.info(f"[MCP启动器] {server_name} 未配置 auto_start 或 auto_start 为 false，跳过端口分配。")
            
            logger.debug(f"[MCP启动器] 使用模块格式启动: python -m {module_str}")
 
        current_pythonpath = env.get('PYTHONPATH')
        if current_pythonpath:
            env['PYTHONPATH'] = f"{project_root_for_pythonpath}{os.pathsep}{current_pythonpath}"
        else:
            env['PYTHONPATH'] = project_root_for_pythonpath
        
        # 启动进程
        # 对于模块格式，使用项目根目录作为工作目录；对于脚本文件，使用服务器目录
        if start_script.endswith('.sh'):
            cwd = server_dir_absolute
        else:
            cwd = project_root_for_pythonpath
        
        logger.debug(f"[MCP启动器] 使用工作目录: {cwd}")
        
        process = subprocess.Popen(
            cmd,
            cwd=cwd,
            env=env, # Pass the modified environment with PYTHONPATH
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # 记录进程
        mcp_processes[server_name] = process
        server_statuses[server_name] = {'status': 'starting'}
        
        # 启动监控线程
        monitor_thread = threading.Thread(
            target=_monitor_server,
            args=(server_name, process),
            daemon=True
        )
        monitor_thread.start()
        
        logger.info(f"MCP服务器已启动: {server_name} (PID: {process.pid})")
        
        # 🚀 智能就绪检测 - 替换简单的sleep
        ready = await _wait_for_server_ready(server_name, process, timeout=30)
        
        if not ready:
            logger.warning(f"⚠️ {server_name} 启动超时，但进程仍在运行，可能需要更多时间")
            # 即使超时，如果进程还在运行，也标记为running状态
            if process.poll() is None:
                server_statuses[server_name] = {'status': 'running', 'pid': process.pid, 'ready': False}
            else:
                stdout, stderr = process.communicate()
                logger.error(f"MCP服务器启动失败: {server_name}\n输出: {stdout}\n错误: {stderr}")
                server_statuses[server_name] = {
                    'status': 'error',
                    'message': 'Failed to start during readiness check',
                    'exit_code': process.returncode
                }
        else:
            logger.info(f"✅ {server_name} 已就绪")
            server_statuses[server_name] = {'status': 'running', 'pid': process.pid, 'ready': True}
            
            # 通知服务容器更新内置服务状态
            await _notify_service_container(server_name, process.pid)
    
    except Exception as e:
        logger.error(f"启动MCP服务器时出错: {server_name} - {str(e)}")
        server_statuses[server_name] = {'status': 'error', 'message': str(e)}

async def _check_registration_readiness(server_name: str) -> bool:
    """检查服务器是否已在ToolScore中注册"""
    global _service_manager
    if not _service_manager:
        logger.debug(f"Service manager not available, cannot check registration status for {server_name}")
        return False

    try:
        toolscore_service = _service_manager.get_service('toolscore')
        if not toolscore_service:
            logger.debug(f"ToolScore service not available, cannot check registration status for {server_name}")
            return False

        tool_library = toolscore_service.get_tool_library()
        if not tool_library:
            logger.debug(f"Unable to get tool library from ToolScore service, skipping registration check for {server_name}")
            return False

        auto_registrar = get_auto_registrar()
        service_id = auto_registrar.builtin_servers.get(server_name, {}).get('service_id')

        if not service_id:
            logger.warning(f"Could not determine service_id for {server_name}, skipping registration check")
            return False

        tool_spec = await tool_library.get_tool_by_id(service_id)
        
        if tool_spec:
            logger.info(f"✅ {server_name} (ID: {service_id}) is registered in ToolScore")
            return True
        else:
            logger.debug(f"⏳ {server_name} (ID: {service_id}) is not yet registered in ToolScore")
            return False
            
    except Exception as e:
        logger.warning(f"Error checking registration status for {server_name}: {e}")
        return False

async def _wait_for_server_ready(server_name: str, process: subprocess.Popen, timeout: int = 30) -> bool:
    """智能等待MCP服务器就绪"""
    start_time = time.time()
    check_interval = 0.5  # 开始时快速检查
    max_interval = 3.0
    current_interval = check_interval
    
    logger.debug(f"🔍 开始检测 {server_name} 就绪状态...")
    
    while time.time() - start_time < timeout:
        # 首先检查进程是否还在运行
        if process.poll() is not None:
            logger.error(f"❌ {server_name} 进程意外退出 (退出码: {process.returncode})")
            return False
        
        try:
            # 🔍 最终检查：确认在ToolScore中注册
            if await _check_registration_readiness(server_name):
                logger.info(f"✅ {server_name} 已在ToolScore中注册，确认就绪")
                return True

            # 🔍 基于服务器类型的特定就绪检查
            if await _check_server_specific_readiness(server_name):
                logger.debug(f"✅ {server_name} 特定就绪检查通过")
                # return True # 特定检查通过后，仍需等待注册

            # 🔍 通用端口就绪检查
            if await _check_port_readiness(server_name):
                logger.debug(f"✅ {server_name} 端口就绪检查通过")
                # 端口就绪后额外等待一点时间确保服务完全初始化
                # await asyncio.sleep(1)
                # return True # 端口就绪不代表完全就绪
            
            # 📋 日志输出分析（检查成功启动的标志）
            if _check_startup_logs(server_name, process):
                logger.debug(f"✅ {server_name} 启动日志检查通过")
                # return True # 日志显示启动不代表完全就绪
            
        except Exception as e:
            logger.debug(f"⚠️ {server_name} 就绪检查异常: {e}")
        
        # 渐进式增加检查间隔
        current_interval = min(current_interval * 1.2, max_interval)
        await asyncio.sleep(current_interval)
    
    logger.debug(f"⏱️ {server_name} 就绪检测超时 ({timeout}秒)")
    return False

async def _check_server_specific_readiness(server_name: str) -> bool:
    """基于服务器类型的特定就绪检查"""
    global _config_manager
    if not _config_manager:
        return False

    try:
        mcp_servers_config = _config_manager.get_mcp_servers_config()
        server_config = mcp_servers_config.get(server_name)

        if not server_config or 'port' not in server_config:
            logger.debug(f"`{server_name}` a un `port` manquant dans la configuration, sautant la vérification de préparation spécifique.")
            return False

        port = server_config['port']
        
        if server_name == 'deepsearch_server':
            return await _check_http_endpoint_health(f"http://localhost:{port}/health")
        elif server_name == 'microsandbox_server':
            return await _check_http_endpoint_health(f"http://localhost:{port}/health")
        elif server_name == 'browser_use_server':
            # Browser Use特定的就绪检查
            return await _check_websocket_health(f"ws://localhost:{port}")
        elif server_name == 'search_tool_server':
            # Search Tool特定的就绪检查
            return await _check_websocket_health(f"ws://localhost:{port}")

    except Exception as e:
        logger.debug(f"⚠️ {server_name} 特定就绪检查失败: {e}")
    
    return False

async def _check_http_endpoint_health(url: str) -> bool:
    """检查HTTP端点健康状态"""
    try:
        import aiohttp
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=3)) as session:
            async with session.get(url) as response:
                return response.status in [200, 404]  # 404也算存活，说明服务在运行
    except Exception:
        return False

async def _check_websocket_health(url: str) -> bool:
    """检查WebSocket端点健康状态"""
    try:
        import websockets
        # 修复: 使用更严格的超时设置和错误处理
        async with websockets.connect(
            url, 
            ping_timeout=3, 
            close_timeout=3,
            open_timeout=5
        ) as websocket:
            # 简单的ping检查
            await websocket.send('{"type": "ping"}')
            # 等待响应以确保连接正常工作
            response = await asyncio.wait_for(websocket.recv(), timeout=2)
            return True
    except asyncio.TimeoutError:
        logger.debug(f"WebSocket健康检查超时: {url}")
        return False
    except Exception as e:
        logger.debug(f"WebSocket健康检查失败: {url}, 错误: {e}")
        return False

async def _check_port_readiness(server_name: str) -> bool:
    """检查服务器端口是否就绪"""
    # 从配置中获取端口
    if _config_manager is None:
        return False
        
    try:
        ports_config = _config_manager.get_ports_config()
        
        # 🔧 修复：添加服务器名称映射
        server_config_key = server_name
        if server_name == 'microsandbox_server':
            server_config_key = 'microsandbox'
        
        server_config = ports_config.get('mcp_servers', {}).get(server_config_key, {})
        port = server_config.get('port')
        
        if not port:
            logger.debug(f"📋 {server_name} 没有配置端口，跳过端口检查")
            return False
        
        # 尝试连接端口
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection('localhost', port),
                timeout=3.0
            )
            writer.close()
            await writer.wait_closed()
            logger.debug(f"✅ {server_name} 端口 {port} 可连接")
            return True
        except Exception:
            logger.debug(f"📋 {server_name} 端口 {port} 尚未就绪")
            return False
            
    except Exception as e:
        logger.debug(f"⚠️ {server_name} 端口检查异常: {e}")
        return False

def _check_startup_logs(server_name: str, process: subprocess.Popen) -> bool:
    """检查启动日志中的成功标志"""
    try:
        # 非阻塞地读取stdout和stderr
        import select
        if process.stdout and process.stdout.readable():
            ready, _, _ = select.select([process.stdout], [], [], 0)
            if ready:
                output = process.stdout.read(1024)  # 读取最近的输出
                if output:
                    output_str = output.decode('utf-8', errors='ignore')
                    # 检查成功启动的标志
                    success_indicators = [
                        'Server started',
                        'server started',
                        'listening on',
                        'Started successfully',
                        'Ready to accept connections',
                        'Server is running',
                        'MCP Server started successfully'
                    ]
                    
                    for indicator in success_indicators:
                        if indicator.lower() in output_str.lower():
                            logger.debug(f"📋 {server_name} 发现启动成功标志: '{indicator}'")
                            return True
    except Exception as e:
        logger.debug(f"⚠️ {server_name} 日志检查异常: {e}")
    
    return False

async def _verify_external_server(server_name: str, server_config: Dict[str, Any]):
    """验证外部MCP服务器连接"""
    global server_statuses
    
    host = server_config.get('host', 'localhost')
    port = server_config.get('port')
    endpoint = server_config.get('endpoint', '')
    protocol = server_config.get('protocol', 'http')
    
    if not port:
        logger.error(f"外部服务器 {server_name} 缺少端口配置")
        server_statuses[server_name] = {'status': 'error', 'message': 'Missing port configuration'}
        return
    
    # 构建URL
    if protocol == 'http':
        url = f"http://{host}:{port}{endpoint}"
    else:
        url = f"ws://{host}:{port}{endpoint}"
    
    logger.info(f"验证外部MCP服务器连接: {server_name} at {url}")
    
    try:
        # 对于HTTP协议，进行简单的连接测试
        if protocol == 'http':
            # 使用同步方式进行简单的连接测试
            import requests
            try:
                # 设置较短的超时时间
                requests.get(f"http://{host}:{port}", timeout=5)
                logger.info(f"外部MCP服务器连接成功: {server_name}")
                server_statuses[server_name] = {'status': 'external_running', 'url': url}
            except requests.exceptions.RequestException:
                # 即使HTTP GET失败，也可能是MCP服务器正常运行（因为它可能不响应普通GET请求）
                # 尝试检查端口是否开放
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(5)
                result = sock.connect_ex((host, port))
                sock.close()
                
                if result == 0:
                    logger.info(f"外部MCP服务器端口开放: {server_name}")
                    server_statuses[server_name] = {'status': 'external_running', 'url': url}
                    # 注册到ToolScore
                    await _register_external_server_to_toolscore(server_name, server_config, url)
                else:
                    logger.error(f"外部MCP服务器连接失败: {server_name}")
                    server_statuses[server_name] = {'status': 'external_error', 'message': 'Connection failed'}
        else:
            # 对于WebSocket协议，检查端口是否开放
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            result = sock.connect_ex((host, port))
            sock.close()
            
            if result == 0:
                logger.info(f"外部MCP服务器连接成功: {server_name}")
                server_statuses[server_name] = {'status': 'external_running', 'url': url}
                # 注册到ToolScore
                await _register_external_server_to_toolscore(server_name, server_config, url)
            else:
                logger.error(f"外部MCP服务器连接失败: {server_name}")
                server_statuses[server_name] = {'status': 'external_error', 'message': 'Connection failed'}
                
    except Exception as e:
        logger.error(f"验证外部MCP服务器时出错: {server_name} - {str(e)}")
        server_statuses[server_name] = {'status': 'external_error', 'message': str(e)}

async def _register_external_server_to_toolscore(server_name: str, server_config: Dict[str, Any], url: str):
    """将外部MCP服务器注册到ToolScore"""
    try:
        # 导入必要的类
        from core.toolscore.interfaces import MCPServerSpec, ToolType
        
        # 创建MCP服务器规范
        server_spec = MCPServerSpec(
            tool_id=f"{server_name}-mcp-server",
            name=server_name,
            description=server_config.get('description', f'{server_name} MCP Server'),
            tool_type=ToolType.MCP_SERVER,
            capabilities=[],  # 能力列表，将从MCP服务器动态获取
            tags=['python', 'sandbox', 'execution'] if server_name == 'microsandbox' else ['external'],
            version=server_config.get('version', '1.0.0'),
            endpoint=url,
            server_config=server_config,
            connection_params={}
        )
        
        # 获取ToolScore服务的UnifiedToolLibrary实例
        from services.toolscore_service import get_tool_library
        tool_library = get_tool_library()
        
        if tool_library:
            # 注册外部MCP服务器
            result = await tool_library.register_external_mcp_server(server_spec)
            
            if result.success:
                logger.info(f"✅ 外部MCP服务器已成功注册到ToolScore: {server_name}")
                server_statuses[server_name]['toolscore_registered'] = True
            else:
                logger.error(f"❌ 外部MCP服务器注册到ToolScore失败: {server_name} - {result.error}")
                server_statuses[server_name]['toolscore_registered'] = False
        else:
            logger.warning(f"⚠️ ToolScore工具库未可用，无法注册: {server_name}")
            server_statuses[server_name]['toolscore_registered'] = False
            
    except Exception as e:
        logger.error(f"注册外部MCP服务器到ToolScore时出错: {server_name} - {str(e)}")
        server_statuses[server_name]['toolscore_registered'] = False

def _monitor_server(server_name, process):
    """监控MCP服务器进程 - 增强版本，支持健康检查和自动重启"""
    global server_statuses
    
    import time
    import threading
    
    # 启动健康检查线程
    health_check_thread = threading.Thread(
        target=_health_check_server, 
        args=(server_name, process), 
        daemon=True
    )
    health_check_thread.start()
    
    # 读取输出
    try:
        for line in process.stdout:
            line_content = line.strip()
            logger.debug(f"[{server_name}] {line_content}")
            
            # 检查特定的错误模式（改进版：排除成功消息）
            line_lower = line_content.lower()
            
            # 先检查是否是成功消息
            success_patterns = ['successfully', 'success', 'started successfully', 'completed', 'ready']
            is_success_message = any(success_pattern in line_lower for success_pattern in success_patterns)
            
            # 只有在非成功消息的情况下才检查错误模式
            error_patterns = ['error', 'exception', 'failed', 'connection refused', 'timeout', 'crashed', 'abort']
            has_error_pattern = any(error_pattern in line_lower for error_pattern in error_patterns)
            
            if has_error_pattern and not is_success_message:
                logger.warning(f"⚠️ [{server_name}] 检测到错误日志: {line_content}")
                
                # 更新状态，包含错误信息
                if server_name in server_statuses:
                    server_statuses[server_name]['last_error'] = line_content
                    server_statuses[server_name]['last_error_time'] = time.time()
    except Exception as e:
        logger.error(f"❌ 读取 {server_name} 输出时出错: {e}")
    
    # 进程结束
    exit_code = process.wait()

    # 如果正在关闭系统，则不执行重启逻辑
    if _is_shutting_down:
        logger.info(f"MCP服务器在系统关闭期间退出: {server_name} (退出码: {exit_code})")
        server_statuses[server_name] = {'status': 'stopped_on_shutdown', 'exit_code': exit_code}
        return
    
    if exit_code != 0:
        logger.warning(f"❌ MCP服务器异常退出: {server_name} (退出码: {exit_code})")
        stderr = process.stderr.read() if process.stderr else ""
        logger.error(f"[{server_name}] 错误输出: {stderr}")
        
        server_statuses[server_name] = {
            'status': 'crashed',
            'exit_code': exit_code,
            'error': stderr[:500] if stderr else None,
            'crash_time': time.time(),
            'restart_attempts': server_statuses.get(server_name, {}).get('restart_attempts', 0)
        }
        
        # 🔄 自动重启逻辑
        restart_attempts = server_statuses[server_name]['restart_attempts']
        max_restart_attempts = 3
        restart_delay = min(60, 10 * (restart_attempts + 1))  # 10s, 20s, 30s, 最大60s
        
        if restart_attempts < max_restart_attempts:
            logger.info(f"🔄 计划在 {restart_delay}s 后自动重启 {server_name} (第 {restart_attempts + 1} 次)")
            server_statuses[server_name]['restart_attempts'] = restart_attempts + 1
            server_statuses[server_name]['next_restart_time'] = time.time() + restart_delay
            
            # 使用定时器实现延迟重启
            restart_timer = threading.Timer(restart_delay, _auto_restart_server, args=(server_name,))
            restart_timer.daemon = True
            restart_timer.start()
            _restart_timers[server_name] = restart_timer
        else:
            logger.error(f"❌ {server_name} 已达最大重启次数 ({max_restart_attempts})，停止自动重启")
            server_statuses[server_name]['status'] = 'failed'
    else:
        logger.info(f"✅ MCP服务器正常退出: {server_name}")
        server_statuses[server_name] = {'status': 'stopped', 'exit_code': 0}

def _health_check_server(server_name: str, process: subprocess.Popen):
    """定期健康检查MCP服务器"""
    global server_statuses
    
    import time
    check_interval = 30  # 30秒检查一次
    consecutive_failures = 0
    max_failures = 3
    
    while process.poll() is None:  # 进程还在运行
        try:
            time.sleep(check_interval)
            
            # 检查进程是否还活着
            if process.poll() is not None:
                break
            
            # 🔍 端口连通性检查
            ports_config = _config_manager.get_ports_config() if _config_manager else {}
            server_config = ports_config.get('mcp_servers', {}).get(server_name, {})
            port = server_config.get('port')
            
            if port:
                health_ok = _check_port_health(port)
                
                if health_ok:
                    consecutive_failures = 0
                    if server_name in server_statuses:
                        server_statuses[server_name]['last_health_check'] = time.time()
                        server_statuses[server_name]['health_status'] = 'healthy'
                    logger.debug(f"💚 {server_name} 健康检查通过 (端口 {port})")
                else:
                    consecutive_failures += 1
                    logger.warning(f"🔴 {server_name} 健康检查失败 (端口 {port})，连续失败 {consecutive_failures} 次")
                    
                    if server_name in server_statuses:
                        server_statuses[server_name]['health_status'] = 'unhealthy'
                        server_statuses[server_name]['consecutive_health_failures'] = consecutive_failures
                    
                    # 如果连续失败过多，标记为需要重启
                    if consecutive_failures >= max_failures:
                        logger.error(f"❌ {server_name} 连续健康检查失败 {consecutive_failures} 次，标记为不健康")
                        
                        # 尝试终止进程以触发自动重启
                        try:
                            process.terminate()
                            logger.info(f"🔄 已发送终止信号给不健康的进程: {server_name}")
                        except Exception as e:
                            logger.error(f"❌ 无法终止不健康的进程 {server_name}: {e}")
                        
                        break
                        
        except Exception as e:
            logger.error(f"❌ 健康检查 {server_name} 时出错: {e}")
            consecutive_failures += 1

def _check_port_health(port: int) -> bool:
    """检查端口健康状态"""
    try:
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(5)
            result = sock.connect_ex(('localhost', port))
            return result == 0
    except Exception:
        return False

def _auto_restart_server(server_name: str):
    """自动重启服务器"""
    if _is_shutting_down:
        logger.info(f"自动重启 {server_name} 已取消，因为系统正在关闭。")
        return

    # 从定时器字典中移除
    if server_name in _restart_timers:
        del _restart_timers[server_name]
        
    try:
        logger.info(f"🔄 开始自动重启 MCP 服务器: {server_name}")
        
        # 更新状态
        if server_name in server_statuses:
            server_statuses[server_name]['status'] = 'restarting'
            server_statuses[server_name]['restart_time'] = time.time()
        
        # 异步调用重启
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(_start_server(server_name))
            logger.info(f"✅ 自动重启成功: {server_name}")
        except Exception as e:
            logger.error(f"❌ 自动重启失败: {server_name} - {e}")
            if server_name in server_statuses:
                server_statuses[server_name]['status'] = 'restart_failed'
                server_statuses[server_name]['restart_error'] = str(e)
        finally:
            loop.close()
            
    except Exception as e:
        logger.error(f"❌ 自动重启过程异常: {server_name} - {e}")
        if server_name in server_statuses:
            server_statuses[server_name]['status'] = 'restart_failed'
            server_statuses[server_name]['restart_error'] = str(e)

def stop():
    """停止所有MCP服务器"""
    global mcp_processes, server_statuses, _is_shutting_down, _restart_timers
    
    _is_shutting_down = True
    logger.info("正在停止MCP服务器...")

    # 取消所有计划中的重启任务
    for server, timer in list(_restart_timers.items()):
        timer.cancel()
        logger.info(f"已取消计划中的重启任务: {server}")
    _restart_timers.clear()
    
    for server_name, process in list(mcp_processes.items()):
        logger.info(f"停止MCP服务器: {server_name}")
        
        try:
            # 检查进程是否还活着
            if process.poll() is None:
                # 进程还在运行，尝试正常终止
                process.terminate()
                
                # 等待进程结束
                try:
                    process.wait(timeout=3)  # 减少超时时间
                    logger.info(f"MCP服务器已正常停止: {server_name}")
                except subprocess.TimeoutExpired:
                    # 如果进程没有及时结束，强制杀死
                    logger.warning(f"MCP服务器未响应终止信号，强制杀死: {server_name}")
                    process.kill()
                    try:
                        process.wait(timeout=2)
                        logger.info(f"MCP服务器已强制停止: {server_name}")
                    except subprocess.TimeoutExpired:
                        logger.error(f"无法停止MCP服务器: {server_name}")
            else:
                logger.info(f"MCP服务器已经停止: {server_name}")
            
            server_statuses[server_name] = {'status': 'stopped'}
            
        except Exception as e:
            logger.error(f"停止MCP服务器时出错: {server_name} - {str(e)}")
            server_statuses[server_name] = {'status': 'error', 'message': f"Stop error: {str(e)}"}
    
    # 强制清理可能遗留的进程
    _force_cleanup_mcp_processes()
    
    # 清空进程字典
    mcp_processes = {}
    
    logger.info("所有MCP服务器已停止")

def _force_cleanup_mcp_processes():
    """强制清理可能遗留的MCP服务器进程"""
    mcp_server_ports = [8081, 8082, 8080]  # MCP服务器使用的端口
    
    for port in mcp_server_ports:
        try:
            # 查找占用端口的进程
            result = subprocess.run(
                ['lsof', '-ti', f':{port}'], 
                capture_output=True, text=True, timeout=3
            )
            
            if result.returncode == 0 and result.stdout.strip():
                pids = result.stdout.strip().split('\n')
                for pid in pids:
                    try:
                        # 检查这是否是我们的MCP服务器进程
                        # 通过检查命令行参数来确认
                        cmd_result = subprocess.run(
                            ['ps', '-p', pid, '-o', 'args='], 
                            capture_output=True, text=True, timeout=2
                        )
                        
                        if (cmd_result.returncode == 0 and 
                            'mcp_servers' in cmd_result.stdout):
                            # 这是我们的MCP服务器进程，强制终止
                            subprocess.run(['kill', '-KILL', pid], timeout=2, check=False)
                            logger.info(f"强制清理MCP服务器进程 {pid} (端口 {port})")
                        
                    except Exception as e:
                        logger.debug(f"清理端口 {port} 进程 {pid} 时出错: {e}")
        except Exception as e:
            logger.debug(f"检查端口 {port} 占用情况失败: {e}")
    
    logger.info("所有MCP服务器已停止")

def health_check():
    """检查所有MCP服务器的健康状态"""
    result = {
        'status': 'healthy',
        'servers': {}
    }
    
    any_running = False
    all_crashed = True
    
    for server_name in mcp_servers:
        status = server_statuses.get(server_name, {'status': 'unknown'})
        result['servers'][server_name] = status
        
        if status.get('status') == 'running':
            any_running = True
            all_crashed = False
        elif status.get('status') not in ['crashed', 'error']:
            all_crashed = False
    
    if not any_running:
        result['status'] = 'warning'
        result['message'] = 'No MCP servers running'
    
    if all_crashed and mcp_servers:
        result['status'] = 'error'
        result['message'] = 'All MCP servers crashed'
    
    return result

def get_server_status(server_name: str) -> Optional[Dict[str, Any]]:
    """获取单个MCP服务器的状态"""
    return server_statuses.get(server_name)

def get_all_server_status() -> Dict[str, Dict[str, Any]]:
    """获取所有MCP服务器的状态"""
    return server_statuses

def restart_server(server_name):
    """重启指定的MCP服务器"""
    if server_name not in mcp_servers:
        logger.error(f"未知的MCP服务器: {server_name}")
        return False
    
    logger.info(f"重启MCP服务器: {server_name}")
    
    # 如果服务器进程存在，先停止它
    if server_name in mcp_processes:
        process = mcp_processes[server_name]
        try:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
        except Exception as e:
            logger.error(f"停止MCP服务器时出错: {server_name} - {str(e)}")
    
    # 启动服务器
    asyncio.create_task(_start_server(server_name))
    
    return True

async def _notify_service_container(server_name: str, status: str, url: Optional[str] = None):
    """通知服务容器有关服务器状态的更新"""
    if _service_container and hasattr(_service_container, 'update_builtin_service_status'):
        try:
            await _service_container.update_builtin_service_status(server_name, status, url)
            logger.debug(f"已通知服务容器: {server_name} 状态为 {status}")
        except Exception as e:
            logger.error(f"通知服务容器时出错: {e}")
