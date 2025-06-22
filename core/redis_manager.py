#!/usr/bin/env python3
"""
Redis管理器 - 处理Redis自动启动和fallback机制
"""

import asyncio
import logging
import os
import subprocess
import sys
import time
import json
from pathlib import Path
from typing import Optional, Dict, Any, List
import redis.asyncio as redis # 导入redis.asyncio
from redis.asyncio.client import Redis # 导入Redis类型提示

logger = logging.getLogger(__name__)

class MockRedisClient:
    """模拟Redis客户端，用于内存fallback模式 - 增强版本"""
    def __init__(self, manager: 'RedisManager'):
        self.manager = manager
        # 连接健康状态
        self._is_connected = True
        self._last_operation_time = time.time()

    async def xlen(self, name: str) -> int:
        """模拟Xlen"""
        return len(self.manager.memory_storage.get(name, []))

    async def xpending_range(self, name: str, consumer_group: str, min_id: str = '-', max_id: str = '+', count: int = 10) -> List[Dict[str, Any]]:
        """模拟XpendingRange，简化实现"""
        # 内存模式下不模拟复杂的XPENDING，直接返回空列表
        return []

    async def xadd(self, name: str, fields: Dict[str, Any], id: str = '*') -> str:
        """模拟XADD，简化为lpush"""
        message = json.dumps(fields)
        await self.manager.memory_lpush(name, message)
        return f"{int(time.time() * 1000)}-0" # 模拟一个ID

    async def lpush(self, key: str, *values: str) -> int:
        """模拟LPUSH"""
        count = 0
        for value in values:
            count = await self.manager.memory_lpush(key, value)
        return count

    async def rpop(self, key: str) -> Optional[str]:
        """模拟RPOP"""
        return await self.manager.memory_rpop(key)

    async def set(self, key: str, value: str) -> bool:
        """模拟SET"""
        return await self.manager.memory_set(key, value)

    async def get(self, key: str) -> Optional[str]:
        """模拟GET"""
        return await self.manager.memory_get(key)

    async def delete(self, *keys: str) -> int:
        """模拟DELETE"""
        count = 0
        for key in keys:
            count += await self.manager.memory_delete(key)
        return count

    async def publish(self, channel: str, message: str) -> int:
        """模拟PUBLISH"""
        return await self.manager.memory_publish(channel, message)

    async def ping(self) -> bool:
        """模拟PING"""
        return True

    async def close(self):
        """模拟CLOSE"""
        pass

class RedisManager:
    """Redis管理器，支持自动启动和fallback到内存模式 - 增强版本"""
    
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis_url = redis_url
        self.redis_process: Optional[subprocess.Popen] = None
        self.redis_available = False
        self.fallback_mode = False
        self._redis_client: Optional[Redis] = None # 存储真实的Redis客户端
        self._mock_client: Optional[MockRedisClient] = None # 存储模拟客户端
        
        # 连接优化配置
        self.connection_timeout = 5.0
        self.max_retries = 3
        self.retry_delay = 1.0
        self.health_check_interval = 30.0
        
        # 连接状态监控
        self._last_health_check = 0
        self._connection_failures = 0
        self._is_monitoring = False
        
        # 内存存储 - 作为Redis的fallback
        self.memory_storage: Dict[str, Any] = {}
        self.memory_queues: Dict[str, asyncio.Queue] = {} # 实际未使用，因为lpush/rpop直接操作memory_storage
        self.memory_pubsub: Dict[str, list] = {}
        
        # 数据持久化路径
        from core.utils.path_utils import get_output_dir
        self.data_dir = get_output_dir("cache")
        self.data_dir.mkdir(exist_ok=True)
        self.backup_file = self.data_dir / "redis_backup.json"
    
    async def ensure_redis_available(self) -> bool:
        """确保Redis可用，增强版本：智能重试和连接监控"""
        
        # 1. 检查Redis是否已经运行（支持重试）
        for attempt in range(self.max_retries):
            if await self._check_redis_connection():
                logger.info(f"✅ 发现运行中的Redis服务 (尝试 {attempt + 1})")
                self.redis_available = True
                self.fallback_mode = False
                self._connection_failures = 0
                
                # 创建Redis客户端with连接池优化
                self._redis_client = redis.from_url(
                    self.redis_url,
                    socket_timeout=self.connection_timeout,
                    socket_connect_timeout=self.connection_timeout,
                    health_check_interval=self.health_check_interval
                )
            return True
        
        # 2. 尝试启动Redis
        if await self._try_start_redis():
            logger.info("成功启动Redis服务")
            self.redis_available = True
            self._redis_client = redis.from_url(self.redis_url)
            return True
        
        # 3. Fallback到内存模式
        logger.warning("Redis不可用，启用内存存储模式")
        self.fallback_mode = True
        self._mock_client = MockRedisClient(self)
        await self._load_backup_data()
        return True
    
    async def _check_redis_connection(self) -> bool:
        """检查Redis连接"""
        try:
            # 不在这里实例化客户端，只检查连接
            client = redis.from_url(self.redis_url)
            await client.ping()
            await client.close()
            return True
        except Exception:
            return False
    
    async def _try_start_redis(self) -> bool:
        """尝试启动Redis服务"""
        try:
            # Windows: 尝试查找Redis安装
            if os.name == 'nt':
                redis_paths = [
                    r"C:\Program Files\Redis\redis-server.exe",
                    r"C:\Program Files (x86)\Redis\redis-server.exe",
                    r"C:\Redis\redis-server.exe",
                    "redis-server.exe"  # PATH中
                ]
                
                for redis_path in redis_paths:
                    if await self._start_redis_process(redis_path):
                        return True
            
            # Unix系统
            else:
                unix_commands = ["redis-server", "/usr/local/bin/redis-server", "/opt/homebrew/bin/redis-server"]
                for cmd in unix_commands:
                    if await self._start_redis_process(cmd):
                        return True
            
            return False
            
        except Exception as e:
            logger.debug(f"启动Redis失败: {e}")
            return False
    
    async def _start_redis_process(self, redis_cmd: str) -> bool:
        """启动Redis进程"""
        try:
            # 检查命令是否存在
            if not self._command_exists(redis_cmd):
                return False
            
            # 启动Redis
            self.redis_process = subprocess.Popen(
                [redis_cmd, "--port", "6379", "--daemonize", "no"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            
            # 等待Redis启动
            for _ in range(10):  # 最多等待5秒
                await asyncio.sleep(0.5)
                if await self._check_redis_connection():
                    logger.info(f"Redis服务已启动 (PID: {self.redis_process.pid})")
                    return True
            
            # 启动失败，终止进程
            self.redis_process.terminate()
            self.redis_process = None
            return False
            
        except Exception as e:
            logger.debug(f"启动Redis进程失败: {e}")
            return False
    
    def _command_exists(self, command: str) -> bool:
        """检查命令是否存在"""
        try:
            if os.name == 'nt':
                # Windows: 检查文件是否存在或在PATH中
                if os.path.isfile(command):
                    return True
                subprocess.run(["where", command], capture_output=True, check=True)
            else:
                # Unix: 使用which命令
                subprocess.run(["which", command], capture_output=True, check=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False
    
    async def _load_backup_data(self):
        """加载备份数据到内存存储"""
        try:
            if self.backup_file.exists():
                with open(self.backup_file, 'r', encoding='utf-8') as f:
                    backup_data = json.load(f)
                    self.memory_storage.update(backup_data.get('storage', {}))
                logger.info("已加载Redis备份数据到内存")
        except Exception as e:
            logger.warning(f"加载备份数据失败: {e}")
    
    async def _save_backup_data(self):
        """保存内存数据到备份文件"""
        try:
            backup_data = {
                'storage': self.memory_storage,
                'timestamp': time.time()
            }
            with open(self.backup_file, 'w', encoding='utf-8') as f:
                json.dump(backup_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"保存备份数据失败: {e}")
    
    async def stop(self):
        """停止Redis管理器"""
        if self.fallback_mode:
            await self._save_backup_data()
        
        if self.redis_process:
            try:
                self.redis_process.terminate()
                self.redis_process.wait(timeout=5)
                logger.info("Redis进程已停止")
            except Exception as e:
                logger.warning(f"停止Redis进程失败: {e}")
                try:
                    self.redis_process.kill()
                except:
                    pass
    
    # ============ 内存存储API (Redis fallback) ============
    # 这些方法现在由MockRedisClient调用
    
    async def memory_set(self, key: str, value: str) -> bool:
        """内存模式: 设置键值"""
        self.memory_storage[key] = value
        return True
    
    async def memory_get(self, key: str) -> Optional[str]:
        """内存模式: 获取键值"""
        return self.memory_storage.get(key)
    
    async def memory_delete(self, key: str) -> int:
        """内存模式: 删除键"""
        if key in self.memory_storage:
            del self.memory_storage[key]
            return 1
        return 0
    
    async def memory_lpush(self, key: str, value: str) -> int:
        """内存模式: 列表左推"""
        if key not in self.memory_storage:
            self.memory_storage[key] = []
        self.memory_storage[key].insert(0, value)
        return len(self.memory_storage[key])
    
    async def memory_rpop(self, key: str) -> Optional[str]:
        """内存模式: 列表右弹"""
        if key in self.memory_storage and self.memory_storage[key]:
            return self.memory_storage[key].pop()
        return None
    
    async def memory_publish(self, channel: str, message: str) -> int:
        """内存模式: 发布消息"""
        if channel not in self.memory_pubsub:
            self.memory_pubsub[channel] = []
        
        # 简单的内存pub/sub，只保留最近100条消息
        self.memory_pubsub[channel].append(message)
        if len(self.memory_pubsub[channel]) > 100:
            self.memory_pubsub[channel].pop(0)
        
        return len(self.memory_pubsub[channel])
    
    def get_redis_url(self) -> str:
        """获取Redis URL，如果是fallback模式返回memory://"""
        if self.fallback_mode:
            return "memory://localhost"
        return self.redis_url
    
    def is_fallback_mode(self) -> bool:
        """是否处于fallback模式"""
        return self.fallback_mode

    def get_client(self) -> Any: # 返回类型可以是Redis或MockRedisClient
        """获取Redis客户端实例，如果fallback模式则返回模拟客户端"""
        if self.fallback_mode:
            if not self._mock_client:
                self._mock_client = MockRedisClient(self)
            return self._mock_client
        else:
            if not self._redis_client:
                self._redis_client = redis.from_url(self.redis_url)
            return self._redis_client
