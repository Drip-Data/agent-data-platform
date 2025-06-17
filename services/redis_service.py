import logging
import os
from typing import Optional
from core.redis_manager import RedisManager # 导入RedisManager

logger = logging.getLogger(__name__)

# 全局Redis连接
_redis_manager: Optional[RedisManager] = None

def initialize(redis_manager: RedisManager):
    """初始化Redis客户端连接"""
    global _redis_manager
    
    _redis_manager = redis_manager
    
    logger.info("Redis服务初始化完成，使用注入的RedisManager实例")

def start():
    """Redis客户端不需要特别的启动过程"""
    if _redis_manager is None:
        raise RuntimeError("Redis客户端未初始化，请先调用initialize()")
    logger.info("Redis客户端已就绪")

def stop():
    """关闭Redis连接"""
    global _redis_manager
    if _redis_manager:
        logger.info("正在关闭Redis连接")
        # RedisManager可能不需要显式关闭连接，因为它管理连接池
        # 如果RedisManager有close方法，可以在这里调用
        # _redis_manager.close()
        _redis_manager = None

def health_check():
    """检查Redis连接状态"""
    if _redis_manager is None:
        return {'status': 'error', 'message': 'Redis client not initialized'}
    
    try:
        # 使用RedisManager的get_client()方法获取实际的客户端，然后调用ping
        client = _redis_manager.get_client()
        import asyncio
        if asyncio.run(client.ping()): # ping是异步方法，需要await
            return {'status': 'healthy'}
        else:
            return {'status': 'error', 'message': 'Redis ping failed'}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}

def get_client():
    """获取Redis客户端实例"""
    if _redis_manager is None:
        raise RuntimeError("Redis客户端未初始化，请先调用initialize()")
    return _redis_manager.get_client() # 返回RedisManager内部的redis客户端

# 队列操作辅助函数
def enqueue(queue_name, data):
    """向指定队列添加数据"""
    if _redis_manager is None:
        raise RuntimeError("Redis客户端未初始化")
    client = _redis_manager.get_client()
    import asyncio
    return asyncio.run(client.lpush(queue_name, data)) # lpush是异步方法，需要await

def dequeue(queue_name, timeout=0):
    """从指定队列获取数据，可设置超时时间"""
    if _redis_manager is None:
        raise RuntimeError("Redis客户端未初始化")
    client = _redis_manager.get_client()
    import asyncio
    if timeout > 0:
        return asyncio.run(client.brpop(queue_name, timeout=timeout)) # brpop是异步方法，需要await
    else:
        return asyncio.run(client.rpop(queue_name)) # rpop是异步方法，需要await
