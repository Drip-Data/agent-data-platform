#!/usr/bin/env python3
"""
智能上下文缓存管理器 - 基于Gemini 2.5的上下文缓存机制优化token消耗
Context Cache Manager - Optimize token consumption using Gemini 2.5 Context Caching
"""

import asyncio
import hashlib
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from enum import Enum

logger = logging.getLogger(__name__)

class CacheStrategy(Enum):
    """缓存策略"""
    AGGRESSIVE = "aggressive"  # 积极缓存，最大节省token
    BALANCED = "balanced"     # 平衡模式，考虑成本效益
    CONSERVATIVE = "conservative"  # 保守模式，仅缓存确定有效的内容

@dataclass
class CacheEntry:
    """缓存条目"""
    cache_id: str
    content_hash: str
    content: str
    token_count: int
    created_at: float
    last_used: float
    usage_count: int
    estimated_savings: float
    ttl_seconds: int = 3600  # 默认1小时TTL
    provider: str = "gemini"
    model: str = "gemini-2.5-flash"

@dataclass
class TokenUsageStats:
    """Token使用统计"""
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cached_tokens: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    estimated_cost_saved: float = 0.0
    
    @property
    def cache_hit_ratio(self) -> float:
        total_requests = self.cache_hits + self.cache_misses
        return self.cache_hits / total_requests if total_requests > 0 else 0.0
    
    @property
    def token_savings_ratio(self) -> float:
        total_tokens = self.total_input_tokens + self.total_cached_tokens
        return self.total_cached_tokens / total_tokens if total_tokens > 0 else 0.0

class ContextCacheManager:
    """
    智能上下文缓存管理器
    
    功能:
    1. 基于Gemini 2.5 Context Caching API的智能缓存
    2. 自动识别可缓存的重复内容
    3. 动态调整缓存策略以优化成本效益
    4. 提供详细的token消耗和成本节省统计
    """
    
    def __init__(self, redis_manager=None, cache_strategy: CacheStrategy = CacheStrategy.BALANCED,
                 min_cache_tokens: int = 1024, max_cache_entries: int = 100):
        """
        初始化上下文缓存管理器
        
        Args:
            redis_manager: Redis管理器，用于持久化缓存
            cache_strategy: 缓存策略
            min_cache_tokens: 最小缓存token数（基于Gemini 2.5要求）
            max_cache_entries: 最大缓存条目数
        """
        self.redis_manager = redis_manager
        self.cache_strategy = cache_strategy
        self.min_cache_tokens = max(min_cache_tokens, 1024)  # Gemini 2.5 Flash最低1024 tokens
        self.max_cache_entries = max_cache_entries
        
        # 内存缓存
        self._cache_entries: Dict[str, CacheEntry] = {}
        self._content_to_cache: Dict[str, str] = {}  # content_hash -> cache_id映射
        
        # 统计信息
        self.stats = TokenUsageStats()
        
        # Gemini 2.5缓存成本配置（基于API文档）
        self.cache_cost_config = {
            "gemini-2.5-pro": {
                "cache_cost_per_1m_tokens": 0.3125,  # $0.3125 per 1M cached tokens
                "storage_cost_per_1m_tokens_per_hour": 4.50,  # $4.50 per 1M tokens per hour
                "input_cost_per_1m_tokens": 1.25,
                "output_cost_per_1m_tokens": 10.0
            },
            "gemini-2.5-flash": {
                "cache_cost_per_1m_tokens": 0.075,   # $0.075 per 1M cached tokens  
                "storage_cost_per_1m_tokens_per_hour": 1.0,   # $1.00 per 1M tokens per hour
                "input_cost_per_1m_tokens": 0.30,
                "output_cost_per_1m_tokens": 2.50
            },
            "gemini-2.5-flash-lite": {
                "cache_cost_per_1m_tokens": 0.025,   # $0.025 per 1M cached tokens
                "storage_cost_per_1m_tokens_per_hour": 1.0,   # Same as flash
                "input_cost_per_1m_tokens": 0.10,
                "output_cost_per_1m_tokens": 0.40
            }
        }
        
        logger.info(f"ContextCacheManager initialized: strategy={cache_strategy.value}, "
                   f"min_tokens={self.min_cache_tokens}, max_entries={max_cache_entries}")
    
    def _calculate_content_hash(self, content: str) -> str:
        """计算内容哈希"""
        return hashlib.sha256(content.encode('utf-8')).hexdigest()
    
    def _estimate_token_count(self, text: str) -> int:
        """估算token数量（简化版本）"""
        # 简化估算：中文字符约1.5字符/token，英文约4字符/token
        chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        other_chars = len(text) - chinese_chars
        
        estimated_tokens = int(chinese_chars / 1.5 + other_chars / 4)
        return max(estimated_tokens, 1)
    
    def _calculate_cache_savings(self, token_count: int, model: str, usage_count: int) -> float:
        """计算缓存节省的成本"""
        try:
            config = self.cache_cost_config.get(model, self.cache_cost_config["gemini-2.5-flash"])
            
            # 正常输入成本
            normal_cost = (token_count / 1_000_000) * config["input_cost_per_1m_tokens"] * usage_count
            
            # 缓存成本（初始缓存成本 + 存储成本）
            cache_cost = (token_count / 1_000_000) * config["cache_cost_per_1m_tokens"]
            storage_hours = 1  # 假设平均存储1小时
            storage_cost = (token_count / 1_000_000) * config["storage_cost_per_1m_tokens_per_hour"] * storage_hours
            
            total_cache_cost = cache_cost + storage_cost
            savings = normal_cost - total_cache_cost
            
            return max(savings, 0.0)  # 不能为负
            
        except Exception as e:
            logger.warning(f"计算缓存节省成本失败: {e}")
            return 0.0
    
    async def should_cache_content(self, content: str, context: str = "") -> bool:
        """
        判断内容是否应该缓存
        
        Args:
            content: 要判断的内容
            context: 使用上下文，帮助决策
            
        Returns:
            是否应该缓存
        """
        try:
            token_count = self._estimate_token_count(content)
            
            # 基本要求：token数量必须达到最小阈值
            if token_count < self.min_cache_tokens:
                return False
            
            # 检查内容是否已经存在
            content_hash = self._calculate_content_hash(content)
            if content_hash in self._content_to_cache:
                return False  # 已经缓存了
            
            # 基于策略判断
            if self.cache_strategy == CacheStrategy.AGGRESSIVE:
                return True
            
            elif self.cache_strategy == CacheStrategy.CONSERVATIVE:
                # 保守策略：只缓存超大内容或明确的重复模式
                return token_count > 5000 or "系统提示" in context or "instructions" in context.lower()
            
            else:  # BALANCED
                # 平衡策略：考虑成本效益
                estimated_savings = self._calculate_cache_savings(token_count, "gemini-2.5-flash", 2)
                return estimated_savings > 0.001  # 至少节省0.001美元
                
        except Exception as e:
            logger.error(f"判断缓存策略失败: {e}")
            return False
    
    async def cache_content(self, content: str, model: str = "gemini-2.5-flash", 
                          ttl_seconds: int = 3600) -> Optional[str]:
        """
        缓存内容到Gemini Context Cache
        
        Args:
            content: 要缓存的内容
            model: 使用的模型
            ttl_seconds: 缓存生存时间
            
        Returns:
            缓存ID，如果缓存失败则返回None
        """
        try:
            content_hash = self._calculate_content_hash(content)
            
            # 检查是否已经缓存
            if content_hash in self._content_to_cache:
                cache_id = self._content_to_cache[content_hash]
                if cache_id in self._cache_entries:
                    entry = self._cache_entries[cache_id]
                    entry.last_used = time.time()
                    entry.usage_count += 1
                    self.stats.cache_hits += 1
                    logger.debug(f"缓存命中: {cache_id}")
                    return cache_id
            
            # 检查缓存数量限制
            if len(self._cache_entries) >= self.max_cache_entries:
                await self._cleanup_expired_cache()
            
            # 创建新的缓存条目
            cache_id = f"cache_{int(time.time())}_{content_hash[:8]}"
            token_count = self._estimate_token_count(content)
            
            entry = CacheEntry(
                cache_id=cache_id,
                content_hash=content_hash,
                content=content,
                token_count=token_count,
                created_at=time.time(),
                last_used=time.time(),
                usage_count=1,
                estimated_savings=0.0,
                ttl_seconds=ttl_seconds,
                model=model
            )
            
            # 这里应该调用真实的Gemini Context Caching API
            # 由于API限制，我们暂时模拟缓存过程
            success = await self._simulate_gemini_cache_api(entry)
            
            if success:
                self._cache_entries[cache_id] = entry
                self._content_to_cache[content_hash] = cache_id
                self.stats.cache_misses += 1
                self.stats.total_cached_tokens += token_count
                
                logger.info(f"成功缓存内容: {cache_id}, tokens: {token_count}")
                return cache_id
            else:
                logger.warning(f"缓存API调用失败: {cache_id}")
                return None
                
        except Exception as e:
            logger.error(f"缓存内容失败: {e}")
            return None
    
    async def _simulate_gemini_cache_api(self, entry: CacheEntry) -> bool:
        """
        模拟Gemini Context Caching API调用
        在实际实现中，这里应该调用真实的API
        """
        try:
            # 模拟API延迟
            await asyncio.sleep(0.1)
            
            # 模拟90%的成功率
            import random
            return random.random() > 0.1
            
        except Exception as e:
            logger.error(f"模拟Gemini缓存API失败: {e}")
            return False
    
    async def get_cached_content(self, cache_id: str) -> Optional[str]:
        """获取缓存内容"""
        try:
            if cache_id in self._cache_entries:
                entry = self._cache_entries[cache_id]
                
                # 检查是否过期
                if time.time() - entry.created_at > entry.ttl_seconds:
                    await self._remove_cache_entry(cache_id)
                    return None
                
                # 更新使用统计
                entry.last_used = time.time()
                entry.usage_count += 1
                self.stats.cache_hits += 1
                
                # 更新节省估算
                entry.estimated_savings = self._calculate_cache_savings(
                    entry.token_count, entry.model, entry.usage_count
                )
                
                return entry.content
            
            return None
            
        except Exception as e:
            logger.error(f"获取缓存内容失败: {e}")
            return None
    
    async def _remove_cache_entry(self, cache_id: str):
        """移除缓存条目"""
        try:
            if cache_id in self._cache_entries:
                entry = self._cache_entries[cache_id]
                
                # 从映射中移除
                if entry.content_hash in self._content_to_cache:
                    del self._content_to_cache[entry.content_hash]
                
                # 从缓存中移除
                del self._cache_entries[cache_id]
                
                # 这里应该调用真实的Gemini API删除缓存
                logger.debug(f"移除缓存条目: {cache_id}")
                
        except Exception as e:
            logger.error(f"移除缓存条目失败: {e}")
    
    async def _cleanup_expired_cache(self):
        """清理过期的缓存条目"""
        try:
            current_time = time.time()
            expired_ids = []
            
            for cache_id, entry in self._cache_entries.items():
                if current_time - entry.created_at > entry.ttl_seconds:
                    expired_ids.append(cache_id)
            
            # 如果过期的不够，按最后使用时间清理
            if len(expired_ids) < self.max_cache_entries // 4:
                sorted_entries = sorted(
                    self._cache_entries.items(),
                    key=lambda x: x[1].last_used
                )
                additional_cleanup = self.max_cache_entries // 4 - len(expired_ids)
                for cache_id, _ in sorted_entries[:additional_cleanup]:
                    if cache_id not in expired_ids:
                        expired_ids.append(cache_id)
            
            # 清理条目
            for cache_id in expired_ids:
                await self._remove_cache_entry(cache_id)
            
            logger.info(f"清理了 {len(expired_ids)} 个缓存条目")
            
        except Exception as e:
            logger.error(f"清理缓存失败: {e}")
    
    def optimize_messages_for_cache(self, messages: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[str]]:
        """
        优化消息列表以使用缓存
        
        Args:
            messages: 原始消息列表
            
        Returns:
            (优化后的消息列表, 使用的缓存ID列表)
        """
        try:
            optimized_messages = []
            used_cache_ids = []
            
            for message in messages:
                content = message.get('content', '')
                
                # 检查是否有对应的缓存
                content_hash = self._calculate_content_hash(content)
                if content_hash in self._content_to_cache:
                    cache_id = self._content_to_cache[content_hash]
                    
                    # 使用缓存引用替换原内容
                    optimized_message = message.copy()
                    optimized_message['content'] = f"[CACHED_CONTENT:{cache_id}]"
                    optimized_message['_original_length'] = len(content)
                    optimized_message['_cache_id'] = cache_id
                    
                    optimized_messages.append(optimized_message)
                    used_cache_ids.append(cache_id)
                else:
                    optimized_messages.append(message)
            
            return optimized_messages, used_cache_ids
            
        except Exception as e:
            logger.error(f"优化消息缓存失败: {e}")
            return messages, []
    
    async def get_cache_statistics(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        try:
            total_savings = sum(entry.estimated_savings for entry in self._cache_entries.values())
            
            return {
                "cache_entries": len(self._cache_entries),
                "total_cached_tokens": self.stats.total_cached_tokens,
                "cache_hit_ratio": self.stats.cache_hit_ratio,
                "token_savings_ratio": self.stats.token_savings_ratio,
                "estimated_cost_saved": total_savings,
                "cache_strategy": self.cache_strategy.value,
                "min_cache_tokens": self.min_cache_tokens,
                "statistics": asdict(self.stats),
                "cache_details": [
                    {
                        "cache_id": entry.cache_id,
                        "token_count": entry.token_count,
                        "usage_count": entry.usage_count,
                        "estimated_savings": entry.estimated_savings,
                        "age_hours": (time.time() - entry.created_at) / 3600
                    }
                    for entry in sorted(self._cache_entries.values(), 
                                      key=lambda x: x.usage_count, reverse=True)[:10]
                ]
            }
            
        except Exception as e:
            logger.error(f"获取缓存统计失败: {e}")
            return {"error": str(e)}
    
    async def clear_cache(self, cache_id: Optional[str] = None):
        """清理缓存"""
        try:
            if cache_id:
                await self._remove_cache_entry(cache_id)
                logger.info(f"清理了缓存: {cache_id}")
            else:
                # 清理所有缓存
                cache_ids = list(self._cache_entries.keys())
                for cache_id in cache_ids:
                    await self._remove_cache_entry(cache_id)
                
                # 重置统计
                self.stats = TokenUsageStats()
                
                logger.info("清理了所有缓存")
                
        except Exception as e:
            logger.error(f"清理缓存失败: {e}")
    
    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        try:
            return {
                "status": "healthy",
                "timestamp": time.time(),
                "cache_entries": len(self._cache_entries),
                "memory_usage_mb": sum(len(entry.content.encode('utf-8')) 
                                     for entry in self._cache_entries.values()) / 1024 / 1024,
                "cache_strategy": self.cache_strategy.value,
                "cache_hit_ratio": self.stats.cache_hit_ratio
            }
            
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "timestamp": time.time()
            }