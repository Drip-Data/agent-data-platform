import logging
import os
import threading
from typing import Dict, Optional

# 导入task_api相关模块
from core.task_api import app as fastapi_app
from core.config_manager import ConfigManager # 导入ConfigManager
from services.mcp_server_launcher import find_available_port # 导入 find_available_port

logger = logging.getLogger(__name__)

# 全局变量
api_app = None
api_server = None
api_thread = None
_config_manager: Optional[ConfigManager] = None # 新增ConfigManager实例

def initialize(config_manager: ConfigManager): # 修改initialize函数签名
    """初始化任务API服务"""
    global api_app, _config_manager
    
    _config_manager = config_manager # 存储ConfigManager实例
    
    logger.info("正在初始化任务API服务...")
    
    # 使用已定义的FastAPI应用
    api_app = fastapi_app
    
    logger.info("任务API服务初始化完成")

def start():
    """启动任务API服务"""
    global api_server, api_thread
    
    if api_app is None or _config_manager is None: # 添加_config_manager检查
        raise RuntimeError("任务API未初始化，请先调用initialize()并传入ConfigManager实例")
    
    logger.info("正在启动任务API服务...")
    
    # 导入uvicorn，用于运行FastAPI应用
    import uvicorn
    
    # 配置参数
    host = os.getenv('API_HOST', '0.0.0.0')
    
    # 从ConfigManager获取端口配置
    ports_config = _config_manager.get_ports_config()
    task_api_config = ports_config.get('core_services', {}).get('task_api', {})
    
    configured_port = int(os.getenv('API_PORT', task_api_config.get('port', 8000)))
    
    # 端口自动检测逻辑
    port_management_config = ports_config.get('port_management', {})
    auto_detect = port_management_config.get('auto_detect', False)
    
    bind_port = None
    if auto_detect:
        start_range = port_management_config.get('port_range_start', 8088)
        end_range = port_management_config.get('port_range_end', 8200)
        available_port = find_available_port(start_range, end_range)
        if available_port:
            bind_port = available_port
            logger.info(f"为 Task API 服务动态分配端口: {bind_port}")
        else:
            logger.warning(f"未能为 Task API 服务找到可用端口，将使用配置的默认端口 {configured_port}")
            bind_port = configured_port # 回退到配置的端口
    else:
        bind_port = configured_port # 不自动检测，直接使用配置的端口
    
    # 创建服务器配置
    config = uvicorn.Config(
        app=api_app,
        host=host,
        port=bind_port, # 使用动态分配或配置的端口
        log_level="debug"
    )
    
    # 创建服务器
    api_server = uvicorn.Server(config)
    
    # 在单独的线程中启动服务器
    api_thread = threading.Thread(
        target=api_server.run,
        daemon=True
    )
    api_thread.start()
    
    logger.info(f"任务API服务已启动于 {host}:{bind_port}") # 更新日志信息

def stop():
    """停止任务API服务"""
    global api_server, api_thread, api_app, _config_manager # 添加_config_manager到global
    
    logger.info("正在停止任务API服务...")
    
    if api_server:
        api_server.should_exit = True
        logger.info("已发送停止信号给任务API服务器")
    
    if api_thread and api_thread.is_alive():
        # 等待线程结束
        api_thread.join(timeout=5)
        if api_thread.is_alive():
            logger.warning("任务API线程未能正常结束")
    
    # 清理资源
    api_app = None
    api_server = None
    api_thread = None
    _config_manager = None # 清理_config_manager
    
    logger.info("任务API服务已停止")

def health_check():
    """检查任务API服务健康状态"""
    if api_app is None:
        return {'status': 'error', 'message': 'Task API not initialized'}
    
    # 动态获取当前绑定的端口
    current_port = None
    if api_server and api_server.config and api_server.config.port:
        current_port = api_server.config.port
    elif _config_manager:
        ports_config = _config_manager.get_ports_config()
        task_api_config = ports_config.get('core_services', {}).get('task_api', {})
        current_port = task_api_config.get('port', 8000) # 回退到配置的默认端口

    if api_server is None or not api_thread or not api_thread.is_alive():
        return {'status': 'error', 'message': 'Task API server not running'}
    
    return {
        'status': 'healthy',
        'endpoint': f"http://{os.getenv('API_HOST', '0.0.0.0')}:{current_port}" # 使用current_port
    }

def get_app():
    """获取FastAPI应用实例"""
    if api_app is None:
        raise RuntimeError("任务API未初始化，请先调用initialize()")
    return api_app
