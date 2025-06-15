import logging
import os
import threading
import subprocess
from typing import Dict, Optional, List
import time
import json

logger = logging.getLogger(__name__)

# 全局变量
mcp_servers = []
mcp_processes = {}
server_statuses = {}

def initialize(config: Optional[Dict] = None):
    """初始化MCP服务器启动器"""
    global mcp_servers
    
    if config is None:
        config = {}
    
    logger.info("正在初始化MCP服务器启动器...")
    
    # 从环境变量或配置中获取MCP服务器列表
    mcp_servers_env = os.getenv('MCP_SERVERS', '')
    mcp_servers_config = config.get('MCP_SERVERS', [])
    
    if mcp_servers_env:
        # 从环境变量解析服务器列表
        mcp_servers = mcp_servers_env.split(',')
    elif mcp_servers_config:
        # 从配置中获取服务器列表
        mcp_servers = mcp_servers_config
    else:
        # 默认服务器列表
        mcp_servers = [
            'python_executor_server',  # Changed hyphen to underscore
            'browser_navigator_server' # Changed hyphen to underscore
        ]
    
    logger.info(f"MCP服务器启动器初始化完成，配置了 {len(mcp_servers)} 个服务器")

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
        _start_server(server_name)
    
    logger.info(f"已启动 {len(mcp_processes)} 个MCP服务器")

def _start_server(server_name):
    """启动单个MCP服务器"""
    global mcp_processes, server_statuses
    
    logger.info(f"正在启动MCP服务器: {server_name}")
    
    # 构建服务器目录路径
    mcp_servers_dir_env = os.getenv('MCP_SERVERS_DIR', './mcp_servers')
    # server_dir_relative is the path as constructed, potentially relative
    server_dir_relative = os.path.join(mcp_servers_dir_env, server_name)
    # server_dir_absolute is the canonical absolute path we'll use for checks and operations
    server_dir_absolute = os.path.abspath(server_dir_relative)

    # 调试日志，输出环境变量、CWD、路径信息
    logger.debug(f"[MCP启动器] 当前工作目录: {os.getcwd()}")
    logger.debug(f"[MCP启动器] MCP_SERVERS_DIR 环境变量: {mcp_servers_dir_env}")
    logger.debug(f"[MCP启动器] server_name: {server_name}")
    logger.debug(f"[MCP启动器] server_dir (相对构造): {server_dir_relative}")
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
        # Determine the project root to add to PYTHONPATH
        # server_dir_absolute is like D:\Code\Agent_mcp_dev\agent-data-platform\mcp_servers\python_executor_server
        # Project root is two levels up from server_dir_absolute
        project_root_for_pythonpath = os.path.abspath(os.path.join(server_dir_absolute, '..', '..'))
        logger.debug(f"[MCP启动器] Setting PYTHONPATH for subprocess to: {project_root_for_pythonpath}")
        
        # 构建启动命令
        if start_script.endswith('.sh'):
            cmd = ['sh', start_script] # start_script is now absolute
        else:
            # 对于Python脚本，使用模块格式运行
            # 将绝对路径转换为相对于项目根目录的模块路径
            relative_script_path = os.path.relpath(start_script, project_root_for_pythonpath)
            module_path_parts = list(os.path.splitext(relative_script_path)[0].split(os.sep))
            module_str = ".".join(module_path_parts)
            cmd = ['python', '-m', module_str]
            logger.debug(f"[MCP启动器] 使用模块格式启动: python -m {module_str}")

        env = os.environ.copy()
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
            # 尝试正常终止进程
            process.terminate()
            
            # 等待进程结束
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                # 如果进程没有及时结束，强制杀死
                logger.warning(f"MCP服务器未响应终止信号，强制杀死: {server_name}")
                process.kill()
            
            logger.info(f"MCP服务器已停止: {server_name}")
            server_statuses[server_name] = {'status': 'stopped'}
            
        except Exception as e:
            logger.error(f"停止MCP服务器时出错: {server_name} - {str(e)}")
            server_statuses[server_name] = {'status': 'error', 'message': f"Stop error: {str(e)}"}
    
    # 清空进程字典
    mcp_processes = {}
    
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
