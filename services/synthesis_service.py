import logging
import os
import threading
import time
from typing import Dict, Optional
from pathlib import Path

# 导入synthesis相关模块
from core.synthesiscore.synthesis import SynthesisService

logger = logging.getLogger(__name__)

# 全局变量
synthesis_instance = None
synthesis_thread = None
running = False

def initialize(config: Optional[Dict] = None):
    """初始化合成服务"""
    global synthesis_instance
    
    if config is None:
        config = {}
    
    logger.info("正在初始化合成服务...")
      # 从环境变量或配置中获取轨迹目录
    trajectories_dir = os.getenv('TRAJECTORIES_DIR', 
                               config.get('TRAJECTORIES_DIR', 'output/trajectories'))
    
    # 确保目录存在
    Path(trajectories_dir).mkdir(parents=True, exist_ok=True)
    
    # 将轨迹目录设置到配置中
    config['TRAJECTORIES_DIR'] = trajectories_dir

    # 添加redis_url配置，确保SynthesisService初始化时有redis_url
    redis_url = config.get('redis_url', os.getenv('REDIS_URL', 'redis://localhost:6379/0'))
    config['redis_url'] = redis_url
    
    # 创建SynthesisService实例（只传递config参数）
    synthesis_instance = SynthesisService(config=config)
    
    logger.info(f"合成服务初始化完成，轨迹目录: {trajectories_dir}")

def start():
    """启动合成服务"""
    global synthesis_thread, running
    
    if synthesis_instance is None:
        raise RuntimeError("合成服务未初始化，请先调用initialize()")
    
    logger.info("正在启动合成服务...")
    
    # 设置运行标志
    running = True
    
    # 创建并启动线程
    synthesis_thread = threading.Thread(
        target=_synthesis_worker,
        daemon=True
    )
    synthesis_thread.start()
    
    logger.info("合成服务已启动")

def _synthesis_worker():
    """合成服务工作线程"""
    global running
    
    logger.info("合成服务工作线程已启动")
    
    # 轮询间隔（秒）
    poll_interval = int(os.getenv('SYNTHESIS_POLL_INTERVAL', 300))  # 默认5分钟
    
    while running:
        try:
            # 执行合成处理
            logger.info("开始处理轨迹数据...")
            import asyncio
            asyncio.run(synthesis_instance._process_unprocessed_trajectories())
        except Exception as e:
            logger.error(f"合成处理过程中出错: {e}", exc_info=True)
        
        # 等待下一次处理
        logger.debug(f"等待 {poll_interval} 秒后再次处理...")
        
        # 使用小间隔检查running标志，以便能够及时响应停止请求
        for _ in range(poll_interval):
            if not running:
                break
            time.sleep(1)
    
    logger.info("合成服务工作线程已停止")

def stop():
    """停止合成服务"""
    global synthesis_thread, running, synthesis_instance
    
    logger.info("正在停止合成服务...")
    
    # 设置停止标志
    running = False
    
    # 等待线程结束
    if synthesis_thread and synthesis_thread.is_alive():
        logger.info("等待合成服务线程结束...")
        synthesis_thread.join(timeout=10)
        if synthesis_thread.is_alive():
            logger.warning("合成服务线程未能正常结束")
    
    # 清理资源
    synthesis_instance = None
    synthesis_thread = None
    
    logger.info("合成服务已停止")

def health_check():
    """检查合成服务健康状态"""
    if synthesis_instance is None:
        return {'status': 'error', 'message': 'Synthesis service not initialized'}
    
    if not synthesis_thread or not synthesis_thread.is_alive():
        return {'status': 'error', 'message': 'Synthesis thread not running'}
    
    # 获取处理统计信息
    stats = synthesis_instance.get_stats() if hasattr(synthesis_instance, 'get_stats') else {}
    
    return {
        'status': 'healthy',
        'thread_alive': synthesis_thread.is_alive(),
        'running_flag': running,
        'stats': stats
    }

def force_process():
    """强制立即处理轨迹"""
    if synthesis_instance is None:
        raise RuntimeError("合成服务未初始化，请先调用initialize()")
    
    logger.info("强制立即处理轨迹...")
    import asyncio
    result = asyncio.run(synthesis_instance._process_unprocessed_trajectories())
    
    return {
        'success': True,
        'processed': result
    }
