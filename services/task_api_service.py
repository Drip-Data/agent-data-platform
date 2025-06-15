import logging
import os
import threading
from typing import Dict, Optional

# 导入task_api相关模块
from core.task_api import app as fastapi_app

logger = logging.getLogger(__name__)

# 全局变量
api_app = None
api_server = None
api_thread = None

def initialize(config: Optional[Dict] = None):
    """初始化任务API服务"""
    global api_app
    
    if config is None:
        config = {}
    
    logger.info("正在初始化任务API服务...")
    
    # 使用已定义的FastAPI应用
    api_app = fastapi_app
    
    logger.info("任务API服务初始化完成")

def start():
    """启动任务API服务"""
    global api_server, api_thread
    
    if api_app is None:
        raise RuntimeError("任务API未初始化，请先调用initialize()")
    
    logger.info("正在启动任务API服务...")
    
    # 导入uvicorn，用于运行FastAPI应用
    import uvicorn
    
    # 配置参数
    host = os.getenv('API_HOST', '0.0.0.0')
    port = int(os.getenv('API_PORT', 8000))
    
    # 创建服务器配置
    config = uvicorn.Config(
        app=api_app,
        host=host,
        port=port,
        log_level="info"
    )
    
    # 创建服务器
    api_server = uvicorn.Server(config)
    
    # 在单独的线程中启动服务器
    api_thread = threading.Thread(
        target=api_server.run,
        daemon=True
    )
    api_thread.start()
    
    logger.info(f"任务API服务已启动于 {host}:{port}")

def stop():
    """停止任务API服务"""
    global api_server, api_thread, api_app
    
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
    
    logger.info("任务API服务已停止")

def health_check():
    """检查任务API服务健康状态"""
    if api_app is None:
        return {'status': 'error', 'message': 'Task API not initialized'}
    
    if api_server is None or not api_thread or not api_thread.is_alive():
        return {'status': 'error', 'message': 'Task API server not running'}
    
    return {
        'status': 'healthy',
        'endpoint': f"http://{os.getenv('API_HOST', '0.0.0.0')}:{os.getenv('API_PORT', 8000)}"
    }

def get_app():
    """获取FastAPI应用实例"""
    if api_app is None:
        raise RuntimeError("任务API未初始化，请先调用initialize()")
    return api_app
