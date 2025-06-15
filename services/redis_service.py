import logging
import os
import redis
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# 全局Redis连接
redis_client = None

def initialize(config: Optional[Dict] = None):
    """初始化Redis客户端连接"""
    global redis_client
    
    if config is None:
        config = {}
    
    redis_host = config.get('REDIS_HOST', os.getenv('REDIS_HOST', 'localhost'))
    redis_port = int(config.get('REDIS_PORT', os.getenv('REDIS_PORT', 6379)))
    redis_db = int(config.get('REDIS_DB', os.getenv('REDIS_DB', 0)))
    redis_password = config.get('REDIS_PASSWORD', os.getenv('REDIS_PASSWORD', None))
    
    logger.info(f"正在连接Redis: {redis_host}:{redis_port}/{redis_db}")
    
    connection_params = {
        'host': redis_host,
        'port': redis_port,
        'db': redis_db,
        'decode_responses': True  # 自动解码为Python字符串
    }
    
    if redis_password:
        connection_params['password'] = redis_password
    
    redis_client = redis.Redis(**connection_params)
    
    # 测试连接
    try:
        redis_client.ping()
        logger.info("Redis连接成功")
    except redis.ConnectionError as e:
        logger.error(f"Redis连接失败: {e}")
        raise

def start():
    """Redis客户端不需要特别的启动过程"""
    if redis_client is None:
        raise RuntimeError("Redis客户端未初始化，请先调用initialize()")
    logger.info("Redis客户端已就绪")

def stop():
    """关闭Redis连接"""
    global redis_client
    if redis_client:
        logger.info("正在关闭Redis连接")
        redis_client.close()
        redis_client = None

def health_check():
    """检查Redis连接状态"""
    if redis_client is None:
        return {'status': 'error', 'message': 'Redis client not initialized'}
    
    try:
        if redis_client.ping():
            return {'status': 'healthy'}
        else:
            return {'status': 'error', 'message': 'Redis ping failed'}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}

def get_client():
    """获取Redis客户端实例"""
    if redis_client is None:
        raise RuntimeError("Redis客户端未初始化，请先调用initialize()")
    return redis_client

# 队列操作辅助函数
def enqueue(queue_name, data):
    """向指定队列添加数据"""
    if redis_client is None:
        raise RuntimeError("Redis客户端未初始化")
    return redis_client.lpush(queue_name, data)

def dequeue(queue_name, timeout=0):
    """从指定队列获取数据，可设置超时时间"""
    if redis_client is None:
        raise RuntimeError("Redis客户端未初始化")
    if timeout > 0:
        return redis_client.brpop(queue_name, timeout=timeout)
    else:
        return redis_client.rpop(queue_name)
