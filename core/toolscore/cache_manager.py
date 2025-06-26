"""
缓存管理器 - 简化版本
"""

import asyncio
import logging
import time
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class CacheManager:
    """缓存管理器"""
    
    def __init__(self):
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._cache_lock = asyncio.Lock()
        self.is_running = False
        
    async def start(self):
        """启动缓存管理器"""
        self.is_running = True
        logger.info("缓存管理器启动完成")
        
    async def stop(self):
        """停止缓存管理器"""
        self.is_running = False
        async with self._cache_lock:
            self._cache.clear()
        logger.info("缓存管理器已停止")
        
    async def set(self, key: str, value: Any, ttl: int = 3600):
        """设置缓存"""
        async with self._cache_lock:
            self._cache[key] = {
                "value": value,
                "expires_at": time.time() + ttl
            }
            
    async def get(self, key: str) -> Optional[Any]:
        """获取缓存"""
        async with self._cache_lock:
            if key not in self._cache:
                return None
                
            cache_item = self._cache[key]
            if time.time() > cache_item["expires_at"]:
                del self._cache[key]
                return None
                
            return cache_item["value"]
            
    async def delete(self, key: str):
        """删除缓存"""
        async with self._cache_lock:
            self._cache.pop(key, None)
            
    async def clear(self):
        """清空缓存"""
        async with self._cache_lock:
            self._cache.clear()
            
    async def cleanup_expired(self):
        """清理过期缓存"""
        current_time = time.time()
        async with self._cache_lock:
            expired_keys = [
                key for key, item in self._cache.items()
                if current_time > item["expires_at"]
            ]
            for key in expired_keys:
                del self._cache[key]
        
        if expired_keys:
            logger.info(f"清理了 {len(expired_keys)} 个过期缓存项")
            
    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        return {
            "total_items": len(self._cache),
            "is_running": self.is_running
        } 