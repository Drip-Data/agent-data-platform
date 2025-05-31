import hashlib
import json
import logging
from typing import Optional, Dict, Any
import redis.asyncio as redis

logger = logging.getLogger(__name__)

class TemplateCache:
    """代码/动作模板缓存系统"""
    
    def __init__(self, redis_client: redis.Redis, ttl: int = 3600):
        self.redis = redis_client
        self.ttl = ttl
        self._hit_count = 0
        self._miss_count = 0
    
    def _make_key(self, task_type: str, description: str) -> str:
        """生成缓存键"""
        content = f"{task_type}:{description.lower().strip()}"
        hash_key = hashlib.md5(content.encode()).hexdigest()
        return f"template_cache:{hash_key}"
    
    async def get(self, task_type: str, description: str) -> Optional[Dict[str, Any]]:
        """获取缓存的模板"""
        key = self._make_key(task_type, description)
        
        try:
            cached = await self.redis.get(key)
            if cached:
                self._hit_count += 1
                result = json.loads(cached.decode())
                logger.info(f"Cache hit for {task_type}: {description[:50]}...")
                return result
            else:
                self._miss_count += 1
                return None
        except Exception as e:
            logger.error(f"Cache get error: {e}")
            return None
    
    async def set(self, task_type: str, description: str, template: Dict[str, Any]):
        """设置缓存模板"""
        key = self._make_key(task_type, description)
        
        try:
            await self.redis.setex(
                key, 
                self.ttl, 
                json.dumps(template, ensure_ascii=False)
            )
            logger.info(f"Cache set for {task_type}: {description[:50]}...")
        except Exception as e:
            logger.error(f"Cache set error: {e}")
    
    async def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        total = self._hit_count + self._miss_count
        hit_rate = self._hit_count / total if total > 0 else 0
        
        return {
            "hit_count": self._hit_count,
            "miss_count": self._miss_count,
            "hit_rate": hit_rate,
            "total_requests": total
        }