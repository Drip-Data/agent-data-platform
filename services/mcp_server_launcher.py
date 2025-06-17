import logging
import os
import threading
import subprocess
from typing import Dict, Optional, List, Any # 导入Any
import time
import json
import socket # 导入socket模块
from core.config_manager import ConfigManager # 导入ConfigManager

logger = logging.getLogger(__name__)

# 全局变量
mcp_servers: List[str] = []
mcp_processes: Dict[str, subprocess.Popen] = {}
server_statuses: Dict[str, Dict[str, Any]] = {}
_config_manager: Optional[ConfigManager] = None # 新增一个私有变量来存储ConfigManager实例

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

def initialize(config_manager: ConfigManager):
    """初始化MCP服务器启动器"""
    global mcp_servers, _config_manager
    
    _config_manager = config_manager # 存储ConfigManager实例
    
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
        # 确保包含python_executor_server和browser_navigator_server
        if "python_executor_server" not in mcp_servers:
            mcp_servers.append("python_executor_server")
        if "browser_navigator_server" not in mcp_servers:
            mcp_servers.append("browser_navigator_server")
        # 添加 search_tool_server
        if "search_tool_server" not in mcp_servers:
            mcp_servers.append("search_tool_server")

    except Exception as e:
        logger.warning(f"从ConfigManager加载MCP服务器列表失败: {e}，使用默认列表")
        mcp_servers = [
            'python_executor_server',
            'browser_navigator_server',
            'search_tool_server' # 添加 search_tool_server 到默认列表
        ]
    
    logger.info(f"MCP服务器启动器初始化完成，配置了 {len(mcp_servers)} 个服务器: {mcp_servers}")

def start():
    """启动所有MCP服务器"""
    global mcp_processes, server_statuses
    
    if not mcp_servers:
        logger.warning("没有配置MCP服务器，跳过启动")
        return
    
    logger.info("正在启动MCP服务器...")
    
    # 清空现有进程字典
    mcp_processes = {}
    server_statuses = {}
    
    # 遍历所有服务器并启动
    for server_name in mcp_servers:
        _start_server(server_name) # _start_server现在可以访问_config_manager
    
    logger.info(f"已启动 {len(mcp_processes)} 个MCP服务器")

def _start_server(server_name: str):
    """启动单个MCP服务器"""
    global mcp_processes, server_statuses
    
    if _config_manager is None:
        logger.error("ConfigManager未初始化，无法启动MCP服务器")
        server_statuses[server_name] = {'status': 'error', 'message': 'ConfigManager not initialized'}
        return

    logger.info(f"正在启动MCP服务器: {server_name}")
    
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
                for key, value in ports_config['mcp_servers'].items():
                    # 移除 '_server' 后缀进行匹配
                    normalized_server_name = server_name.replace('_server', '')
                    if normalized_server_name == key:
                        if isinstance(value, dict):
                            server_config = value
                            break
            
            cmd = ['python', '-m', module_str]
            
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
        
        # 等待服务器启动
        time.sleep(2)
        
        # 检查进程是否仍在运行
        if process.poll() is not None:
            # 进程已结束
            stdout, stderr = process.communicate()
            logger.error(f"MCP服务器启动失败: {server_name}\n输出: {stdout}\n错误: {stderr}")
            server_statuses[server_name] = {
                'status': 'error',
                'message': 'Failed to start',
                'exit_code': process.returncode
            }
        else:
            # 进程正在运行
            server_statuses[server_name] = {'status': 'running', 'pid': process.pid}
    
    except Exception as e:
        logger.error(f"启动MCP服务器时出错: {server_name} - {str(e)}")
        server_statuses[server_name] = {'status': 'error', 'message': str(e)}

def _monitor_server(server_name, process):
    """监控MCP服务器进程"""
    global server_statuses
    
    # 读取输出
    for line in process.stdout:
        logger.debug(f"[{server_name}] {line.strip()}")
    
    # 进程结束
    exit_code = process.wait()
    
    if exit_code != 0:
        logger.warning(f"MCP服务器异常退出: {server_name} (退出码: {exit_code})")
        stderr = process.stderr.read()
        logger.error(f"[{server_name}] 错误输出: {stderr}")
        
        server_statuses[server_name] = {
            'status': 'crashed',
            'exit_code': exit_code,
            'error': stderr[:500] if stderr else None
        }
    else:
        logger.info(f"MCP服务器正常退出: {server_name}")
        server_statuses[server_name] = {'status': 'stopped', 'exit_code': 0}

def stop():
    """停止所有MCP服务器"""
    global mcp_processes, server_statuses
    
    logger.info("正在停止MCP服务器...")
    
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

def get_server_status(server_name):
    """获取指定MCP服务器的状态"""
    return server_statuses.get(server_name, {'status': 'unknown'})

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
    _start_server(server_name)
    
    return True
