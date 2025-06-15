import asyncio
import logging
import os
from pathlib import Path

from runtimes.reasoning.enhanced_runtime import EnhancedReasoningRuntime
from core.task_management.task_manager import start_runtime_service
from core.redis.redis_manager import RedisManager
from config import TOOLSCORE_HTTP_URL, TOOLSCORE_MCP_WS_URL

logger = logging.getLogger(__name__)

_enhanced_runtime_instance: EnhancedReasoningRuntime = None

async def start_enhanced_reasoning_runtime(redis_manager: RedisManager):
    """启动Enhanced Reasoning Runtime任务消费者"""
    global _enhanced_runtime_instance
    try:
        logger.info("🚀 启动Enhanced Reasoning Runtime消费者...")
        
        # 配置环境变量，使增强运行时能够正确连接当前实例的 ToolScore
        os.environ.setdefault('TOOLSCORE_HTTP_URL', TOOLSCORE_HTTP_URL)  # Monitoring / HTTP API
        os.environ.setdefault('TOOLSCORE_WS_URL', TOOLSCORE_HTTP_URL)     # WebSocket for real-time updates (这里应该用HTTP URL，因为是监控API的WS)
        os.environ.setdefault('TOOLSCORE_URL', TOOLSCORE_MCP_WS_URL)  # MCP WebSocket

        _enhanced_runtime_instance = EnhancedReasoningRuntime()
        
        # 延迟启动Enhanced Runtime，确保所有服务都已就绪
        await asyncio.sleep(8)  # 等待核心服务完全启动
        
        logger.info("⏳ 初始化Enhanced Reasoning Runtime...")
        
        # 设置更合理的初始化超时时间
        await asyncio.wait_for(_enhanced_runtime_instance.initialize(), timeout=60.0)
        
        logger.info("✅ Enhanced Reasoning Runtime初始化完成")
        logger.info(f"Runtime ID: {_enhanced_runtime_instance.runtime_id}")
        
        logger.info("🔄 启动任务队列消费服务...")
        
        # 修复：使用稳定的启动方式，传递redis_manager参数
        await start_runtime_service(_enhanced_runtime_instance, redis_manager=redis_manager)
        
    except asyncio.TimeoutError:
        logger.error("Enhanced Reasoning Runtime 初始化超时，将跳过启动，但其他服务正常运行")
    except Exception as e:
        logger.error(f"启动 Enhanced Reasoning Runtime 失败: {e}")
        logger.warning("Enhanced Reasoning Runtime 启动失败，但核心服务（ToolScore、Task API）仍可正常使用")
        import traceback
        traceback.print_exc()

async def stop_enhanced_reasoning_runtime():
    """停止Enhanced Reasoning Runtime并清理资源"""
    global _enhanced_runtime_instance
    if _enhanced_runtime_instance:
        try:
            logger.info("⏳ 正在清理 Enhanced Reasoning Runtime...")
            await _enhanced_runtime_instance.cleanup()
            logger.info("✅ Enhanced Reasoning Runtime 已清理")
        except Exception as e:
            logger.error(f"清理 Enhanced Reasoning Runtime 出错: {e}")
        _enhanced_runtime_instance = None