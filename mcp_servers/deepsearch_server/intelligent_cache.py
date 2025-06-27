#!/usr/bin/env python3
"""
智能缓存系统 - DeepSearch性能优化
支持查询结果缓存、语义相似性匹配和缓存策略管理
"""

import asyncio
import hashlib
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, asdict
import pickle
import os
from pathlib import Path

logger = logging.getLogger(__name__)

@dataclass
class CacheEntry:
    """缓存条目数据结构"""
    question: str
    result: Dict[str, Any]
    timestamp: datetime
    hit_count: int = 0
    research_depth: str = "standard"
    question_hash: str = ""
    semantic_embedding: Optional[List[float]] = None
    
    def __post_init__(self):
        if not self.question_hash:
            self.question_hash = self._generate_hash(self.question)
    
    @staticmethod
    def _generate_hash(text: str) -> str:
        """生成文本哈希"""
        return hashlib.md5(text.encode('utf-8')).hexdigest()
    
    def is_expired(self, ttl_hours: int = 24) -> bool:
        """检查缓存是否过期"""
        expiry_time = self.timestamp + timedelta(hours=ttl_hours)
        return datetime.now() > expiry_time
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式（用于序列化）"""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CacheEntry':
        """从字典创建实例"""
        data['timestamp'] = datetime.fromisoformat(data['timestamp'])
        return cls(**data)

class IntelligentCache:
    """智能缓存管理器"""
    
    def __init__(self, cache_dir: str = None, max_entries: int = 1000, ttl_hours: int = 24):
        self.cache_dir = Path(cache_dir) if cache_dir else Path.home() / ".deepsearch_cache"
        self.cache_dir.mkdir(exist_ok=True)
        
        self.max_entries = max_entries
        self.ttl_hours = ttl_hours
        
        # 内存缓存
        self._memory_cache: Dict[str, CacheEntry] = {}
        self._access_times: Dict[str, datetime] = {}
        
        # 缓存统计
        self.stats = {
            "total_requests": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "semantic_matches": 0,
            "cache_saves": 0
        }
        
        # 初始化时加载持久化缓存
        try:
            asyncio.create_task(self._load_persistent_cache())
        except RuntimeError:
            # 在同步环境中跳过异步初始化
            pass
    
    async def _load_persistent_cache(self):
        """异步加载持久化缓存"""
        try:
            cache_file = self.cache_dir / "cache_entries.json"
            if cache_file.exists():
                with open(cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                loaded_count = 0
                for entry_data in data.get('entries', []):
                    try:
                        entry = CacheEntry.from_dict(entry_data)
                        if not entry.is_expired(self.ttl_hours):
                            self._memory_cache[entry.question_hash] = entry
                            loaded_count += 1
                    except Exception as e:
                        logger.warning(f"Failed to load cache entry: {e}")
                
                logger.info(f"Loaded {loaded_count} cache entries from persistent storage")
                
                # 加载统计信息
                if 'stats' in data:
                    self.stats.update(data['stats'])
                    
        except Exception as e:
            logger.error(f"Failed to load persistent cache: {e}")
    
    async def _save_persistent_cache(self):
        """异步保存缓存到持久化存储"""
        try:
            cache_file = self.cache_dir / "cache_entries.json"
            
            # 准备序列化数据
            entries_data = []
            for entry in self._memory_cache.values():
                if not entry.is_expired(self.ttl_hours):
                    entries_data.append(entry.to_dict())
            
            data = {
                'entries': entries_data,
                'stats': self.stats,
                'last_saved': datetime.now().isoformat()
            }
            
            # 原子写入
            temp_file = cache_file.with_suffix('.tmp')
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            temp_file.replace(cache_file)
            logger.debug(f"Saved {len(entries_data)} cache entries to persistent storage")
            
        except Exception as e:
            logger.error(f"Failed to save persistent cache: {e}")
    
    def _generate_cache_key(self, question: str, research_depth: str = "standard") -> str:
        """生成缓存键"""
        # 标准化问题文本
        normalized_question = question.strip().lower()
        key_text = f"{normalized_question}|{research_depth}"
        return hashlib.md5(key_text.encode('utf-8')).hexdigest()
    
    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """计算文本相似度（简单基于词汇重叠）"""
        # TODO: 未来可以集成embedding模型进行语义相似度计算
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        return len(intersection) / len(union) if union else 0.0
    
    async def get_cached_result(self, question: str, research_depth: str = "standard", 
                               similarity_threshold: float = 0.7) -> Optional[Dict[str, Any]]:
        """获取缓存结果"""
        self.stats["total_requests"] += 1
        
        cache_key = self._generate_cache_key(question, research_depth)
        
        # 1. 精确匹配
        if cache_key in self._memory_cache:
            entry = self._memory_cache[cache_key]
            if not entry.is_expired(self.ttl_hours):
                entry.hit_count += 1
                self._access_times[cache_key] = datetime.now()
                self.stats["cache_hits"] += 1
                
                logger.info(f"Cache HIT (exact): {question[:50]}...")
                return {
                    **entry.result,
                    "_cache_info": {
                        "hit_type": "exact",
                        "hit_count": entry.hit_count,
                        "cached_at": entry.timestamp.isoformat()
                    }
                }
        
        # 2. 语义相似性匹配
        best_match = None
        best_similarity = 0.0
        
        for entry in self._memory_cache.values():
            if entry.research_depth == research_depth and not entry.is_expired(self.ttl_hours):
                similarity = self._calculate_similarity(question, entry.question)
                if similarity > best_similarity and similarity >= similarity_threshold:
                    best_similarity = similarity
                    best_match = entry
        
        if best_match:
            best_match.hit_count += 1
            self.stats["semantic_matches"] += 1
            
            logger.info(f"Cache HIT (semantic {best_similarity:.2f}): {question[:50]}... -> {best_match.question[:50]}...")
            
            # 为语义匹配添加适配信息
            adapted_result = best_match.result.copy()
            adapted_result["_cache_info"] = {
                "hit_type": "semantic",
                "similarity": best_similarity,
                "original_question": best_match.question,
                "hit_count": best_match.hit_count,
                "cached_at": best_match.timestamp.isoformat()
            }
            
            return adapted_result
        
        # 3. 缓存未命中
        self.stats["cache_misses"] += 1
        logger.debug(f"Cache MISS: {question[:50]}...")
        return None
    
    async def cache_result(self, question: str, result: Dict[str, Any], 
                          research_depth: str = "standard"):
        """缓存研究结果"""
        try:
            cache_key = self._generate_cache_key(question, research_depth)
            
            # 创建缓存条目
            entry = CacheEntry(
                question=question,
                result=result,
                timestamp=datetime.now(),
                research_depth=research_depth,
                question_hash=cache_key
            )
            
            # 添加到内存缓存
            self._memory_cache[cache_key] = entry
            self._access_times[cache_key] = datetime.now()
            self.stats["cache_saves"] += 1
            
            logger.info(f"Cached result for: {question[:50]}...")
            
            # 清理过期缓存
            await self._cleanup_expired_entries()
            
            # 如果缓存过大，清理最久未使用的条目
            if len(self._memory_cache) > self.max_entries:
                await self._cleanup_lru_entries()
            
            # 异步保存到持久化存储
            asyncio.create_task(self._save_persistent_cache())
            
        except Exception as e:
            logger.error(f"Failed to cache result: {e}")
    
    async def _cleanup_expired_entries(self):
        """清理过期缓存条目"""
        expired_keys = []
        for key, entry in self._memory_cache.items():
            if entry.is_expired(self.ttl_hours):
                expired_keys.append(key)
        
        for key in expired_keys:
            del self._memory_cache[key]
            self._access_times.pop(key, None)
        
        if expired_keys:
            logger.debug(f"Cleaned up {len(expired_keys)} expired cache entries")
    
    async def _cleanup_lru_entries(self):
        """清理最久未使用的缓存条目"""
        # 按访问时间排序，删除最久未使用的条目
        sorted_entries = sorted(
            self._access_times.items(), 
            key=lambda x: x[1]
        )
        
        # 删除20%的最旧条目
        cleanup_count = max(1, len(sorted_entries) // 5)
        for key, _ in sorted_entries[:cleanup_count]:
            self._memory_cache.pop(key, None)
            self._access_times.pop(key, None)
        
        logger.debug(f"Cleaned up {cleanup_count} LRU cache entries")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        total_requests = self.stats["total_requests"]
        cache_hits = self.stats["cache_hits"] + self.stats["semantic_matches"]
        
        hit_rate = (cache_hits / total_requests * 100) if total_requests > 0 else 0
        
        return {
            **self.stats,
            "total_cache_hits": cache_hits,
            "hit_rate_percent": round(hit_rate, 2),
            "memory_entries": len(self._memory_cache),
            "cache_size_mb": self._get_cache_size_mb()
        }
    
    def _get_cache_size_mb(self) -> float:
        """估算缓存大小（MB）"""
        try:
            total_size = 0
            for entry in self._memory_cache.values():
                # 粗略估算对象大小
                entry_size = len(json.dumps(entry.to_dict(), ensure_ascii=False).encode('utf-8'))
                total_size += entry_size
            
            return round(total_size / (1024 * 1024), 2)
        except Exception:
            return 0.0
    
    async def clear_cache(self):
        """清空所有缓存"""
        self._memory_cache.clear()
        self._access_times.clear()
        
        # 重置统计信息
        self.stats = {
            "total_requests": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "semantic_matches": 0,
            "cache_saves": 0
        }
        
        # 删除持久化文件
        try:
            cache_file = self.cache_dir / "cache_entries.json"
            if cache_file.exists():
                cache_file.unlink()
        except Exception as e:
            logger.error(f"Failed to delete persistent cache file: {e}")
        
        logger.info("Cache cleared successfully")
    
    async def preload_common_queries(self, common_queries: List[Dict[str, str]]):
        """预加载常见查询"""
        logger.info(f"Preloading {len(common_queries)} common queries...")
        
        for query_info in common_queries:
            question = query_info.get("question", "")
            research_depth = query_info.get("research_depth", "standard")
            
            # 检查是否已缓存
            if not await self.get_cached_result(question, research_depth):
                logger.info(f"Query needs caching: {question[:50]}...")
                # 这里可以触发实际的研究调用来预热缓存
                # 但在当前上下文中，我们只是标记为需要预热
    
    def __del__(self):
        """析构函数 - 确保缓存被保存"""
        try:
            # 注意：在析构函数中不能使用async
            # 这里只是一个保险措施
            pass
        except Exception:
            pass

# 全局缓存实例
_global_cache: Optional[IntelligentCache] = None

def get_cache_instance() -> IntelligentCache:
    """获取全局缓存实例"""
    global _global_cache
    if _global_cache is None:
        _global_cache = IntelligentCache()
    return _global_cache

async def initialize_cache(**kwargs) -> IntelligentCache:
    """初始化缓存系统"""
    global _global_cache
    _global_cache = IntelligentCache(**kwargs)
    await _global_cache._load_persistent_cache()
    return _global_cache