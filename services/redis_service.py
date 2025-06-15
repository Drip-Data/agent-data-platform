import logging
from core.redis.redis_manager import RedisManager
from config import get_available_api_keys_info

logger = logging.getLogger(__name__)

async def start_redis_manager() -> RedisManager:
    """
    初始化并启动 RedisManager。
    返回 RedisManager 实例。
    """
    logger.info("🚀 正在初始化 Redis Manager...")
    redis_manager = RedisManager()
    await redis_manager.ensure_redis_available()
    
    if redis_manager.is_fallback_mode():
        logger.warning("⚠️  使用内存存储模式 - 数据将在重启后丢失")
    else:
        logger.info("✅ Redis 服务已就绪")
    
        
    return redis_manager

async def stop_redis_manager(redis_manager: RedisManager):
    """
    停止 RedisManager。
    """
    if redis_manager:
        await redis_manager.stop()
        logger.info("Redis Manager 已停止。")