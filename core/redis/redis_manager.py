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
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class RedisManager:
    """Redis管理器，支持自动启动和fallback到内存模式"""
    
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis_url = redis_url
        self.redis_process: Optional[subprocess.Popen] = None
        self.redis_available = False
        self.fallback_mode = False
        
        # 内存存储 - 作为Redis的fallback
        self.memory_storage: Dict[str, Any] = {}
        self.memory_queues: Dict[str, asyncio.Queue] = {}
        self.memory_pubsub: Dict[str, list] = {}
        
        # 数据持久化路径
        self.data_dir = Path(__file__).parent.parent / "data"
        self.data_dir.mkdir(exist_ok=True)
        self.backup_file = self.data_dir / "redis_backup.json"
    
    async def ensure_redis_available(self) -> bool:
        """确保Redis可用，优先使用现有Redis，否则尝试启动或fallback"""
        
        # 1. 检查Redis是否已经运行
        if await self._check_redis_connection():
            logger.info("发现运行中的Redis服务")
            self.redis_available = True
            return True
        
        # 2. 尝试启动Redis
        if await self._try_start_redis():
            logger.info("成功启动Redis服务")
            self.redis_available = True
            return True
        
        # 3. Fallback到内存模式
        logger.warning("Redis不可用，启用内存存储模式")
        self.fallback_mode = True
        await self._load_backup_data()
        return True
    
    async def _check_redis_connection(self) -> bool:
        """检查Redis连接"""
        try:
            import redis.asyncio as redis
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
