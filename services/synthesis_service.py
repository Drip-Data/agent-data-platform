import logging
import os
import threading
import time
import asyncio
from typing import Dict, Optional
from pathlib import Path

# 导入synthesis相关模块
from core.synthesiscore.synthesis import SynthesisService
from core.synthesiscore.trajectory_monitor import TrajectoryMonitor
from core.llm_client import LLMClient
from core.toolscore.mcp_client import MCPToolClient

logger = logging.getLogger(__name__)

# 全局变量
synthesis_instance = None
trajectory_monitor = None
synthesis_thread = None
monitor_task = None
running = False

from core.unified_tool_manager import UnifiedToolManager

def initialize(config: Optional[Dict] = None, tool_manager: Optional[UnifiedToolManager] = None):
    """初始化合成服务"""
    global synthesis_instance, trajectory_monitor
    
    if config is None:
        config = {}
    
    logger.info("正在初始化合成服务...")
    
    # 如果没有传入依赖，这是一个致命错误
    if not tool_manager:
        raise ValueError("SynthesisService初始化失败：必须提供UnifiedToolManager实例。")

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
    
    # 创建SynthesisService实例，并传入tool_manager
    synthesis_instance = SynthesisService(config=config, tool_manager=tool_manager)
    
    # 初始化完整的TrajectoryMonitor v2.0
    try:
        # 创建LLM和MCP客户端
        llm_client = LLMClient(config, tool_manager=tool_manager)
        mcp_client = MCPToolClient("ws://localhost:8089/websocket")
        
        # 创建完整的TrajectoryMonitor v2.0
        trajectory_monitor = TrajectoryMonitor(
            llm_client=llm_client,
            mcp_client=mcp_client,
            trajectories_dir=trajectories_dir,
            seed_tasks_file=os.path.join(trajectories_dir, "..", "seed_tasks.jsonl")
        )
        
        logger.info("✅ TrajectoryMonitor v2.0 初始化完成")
        
    except Exception as e:
        logger.error(f"❌ TrajectoryMonitor v2.0 初始化失败: {e}")
        # 如果v2.0失败，继续使用v1.0
        trajectory_monitor = None
    
    logger.info(f"合成服务初始化完成，轨迹目录: {trajectories_dir}")

def start():
    """启动合成服务"""
    global synthesis_thread, monitor_task, running
    
    if synthesis_instance is None:
        raise RuntimeError("合成服务未初始化，请先调用initialize()")
    
    logger.info("正在启动合成服务...")
    
    # 设置运行标志
    running = True
    
    # 启动v1.0服务（保持向后兼容）
    synthesis_thread = threading.Thread(
        target=_synthesis_worker,
        daemon=True
    )
    synthesis_thread.start()
    
    # 启动v2.0监控器（在单独线程中运行）
    if trajectory_monitor:
        monitor_thread = threading.Thread(
            target=_v2_monitor_worker,
            daemon=True
        )
        monitor_thread.start()
        logger.info("🚀 启动SynthesisCore v2.0监控器")
    
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

def _v2_monitor_worker():
    """v2.0监控器工作线程"""
    global running
    
    logger.info("SynthesisCore v2.0监控器工作线程已启动")
    
    try:
        # 创建新的事件循环
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # 运行监控器
        loop.run_until_complete(_start_v2_monitor())
        
    except Exception as e:
        logger.error(f"❌ SynthesisCore v2.0监控器工作线程异常: {e}")
    finally:
        logger.info("SynthesisCore v2.0监控器工作线程已停止")

async def _start_v2_monitor():
    """启动简化监控器"""
    try:
        await trajectory_monitor.initialize()
        await trajectory_monitor.start_monitoring()
        logger.info("✅ SynthesisCore v2.0监控器已启动")
        
        # 保持监控运行
        while running:
            await asyncio.sleep(1)
            
        # 停止监控
        await trajectory_monitor.stop_monitoring()
        
    except Exception as e:
        logger.error(f"❌ SynthesisCore v2.0监控器启动失败: {e}")

def stop():
    """停止合成服务"""
    global synthesis_thread, monitor_task, running, synthesis_instance, trajectory_monitor
    
    logger.info("正在停止合成服务...")
    
    # 设置停止标志
    running = False
    
    # 停止v2.0监控器
    if trajectory_monitor:
        try:
            asyncio.create_task(trajectory_monitor.stop_monitoring())
            logger.info("🛑 SynthesisCore v2.0监控器已停止")
        except Exception as e:
            logger.error(f"❌ 停止v2.0监控器失败: {e}")
    
    # 等待v1.0线程结束
    if synthesis_thread and synthesis_thread.is_alive():
        logger.info("等待合成服务线程结束...")
        synthesis_thread.join(timeout=10)
        if synthesis_thread.is_alive():
            logger.warning("合成服务线程未能正常结束")
    
    # 清理资源
    synthesis_instance = None
    trajectory_monitor = None
    synthesis_thread = None
    monitor_task = None
    
    logger.info("合成服务已停止")

def health_check():
    """检查合成服务健康状态"""
    if synthesis_instance is None:
        return {'status': 'error', 'message': 'Synthesis service not initialized'}
    
    # v1.0状态检查
    v1_status = {
        'thread_alive': synthesis_thread.is_alive() if synthesis_thread else False,
        'running_flag': running
    }
    
    # v2.0状态检查
    v2_status = {
        'monitor_initialized': trajectory_monitor is not None,
        'monitor_active': False
    }
    
    if trajectory_monitor:
        try:
            v2_status['monitor_active'] = trajectory_monitor.observer.is_alive() if hasattr(trajectory_monitor, 'observer') else False
        except:
            pass
    
    # 获取处理统计信息
    stats = synthesis_instance.get_stats() if hasattr(synthesis_instance, 'get_stats') else {}
    
    # 整体状态
    overall_healthy = (v1_status['thread_alive'] or v2_status['monitor_initialized'])
    
    return {
        'status': 'healthy' if overall_healthy else 'error',
        'v1_synthesis': v1_status,
        'v2_monitor': v2_status,
        'stats': stats
    }

def force_process():
    """强制立即处理轨迹"""
    if synthesis_instance is None:
        raise RuntimeError("合成服务未初始化，请先调用initialize()")
    
    logger.info("强制立即处理轨迹...")
    
    result = {'v1_synthesis': None, 'v2_monitor': None, 'success': False}
    
    try:
        # v1.0处理
        v1_result = asyncio.run(synthesis_instance._process_unprocessed_trajectories())
        result['v1_synthesis'] = v1_result
        
        # v2.0处理（如果可用）
        if trajectory_monitor:
            v2_result = asyncio.run(trajectory_monitor.process_existing_trajectories())
            result['v2_monitor'] = v2_result
        
        result['success'] = True
        logger.info("✅ 强制处理完成")
        
    except Exception as e:
        logger.error(f"❌ 强制处理失败: {e}")
        result['error'] = str(e)
    
    return result

def get_v2_statistics():
    """获取v2.0监控器统计信息"""
    if trajectory_monitor is None:
        return {'error': 'TrajectoryMonitor v2.0 not initialized'}
    
    try:
        return asyncio.run(trajectory_monitor.get_statistics())
    except Exception as e:
        logger.error(f"❌ 获取v2.0统计信息失败: {e}")
        return {'error': str(e)}
