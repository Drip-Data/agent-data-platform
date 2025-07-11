#!/usr/bin/env python3
"""
智能Token管理器 - 集成Gemini 2.5真实token计数API和上下文优化
Intelligent Token Manager - Integrates real Gemini 2.5 token counting API and context optimization
"""

import asyncio
import json
import logging
import time
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime

from core.context_cache_manager import ContextCacheManager, CacheStrategy
from core.llm_providers.gemini_provider import GeminiProvider

logger = logging.getLogger(__name__)

@dataclass
class TokenUsageRecord:
    """Token使用记录"""
    timestamp: float
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    model: str
    provider: str
    task_id: str
    session_id: Optional[str]
    cached_tokens: int = 0
    cache_hits: int = 0
    estimated_cost: float = 0.0
    actual_api_call: bool = True  # 是否使用真实API计数

@dataclass
class TokenOptimizationStats:
    """Token优化统计"""
    total_requests: int = 0
    total_tokens_saved: int = 0
    total_cost_saved: float = 0.0
    cache_hit_ratio: float = 0.0
    avg_tokens_per_request: float = 0.0
    optimization_efficiency: float = 0.0  # 优化效率百分比

class IntelligentTokenManager:
    """
    智能Token管理器
    
    功能：
    1. 使用Gemini真实API进行精确token计数
    2. 智能上下文缓存和复用
    3. 动态token消耗优化
    4. 详细的成本分析和建议
    5. 实时token消耗监控和预警
    """
    
    def __init__(self, gemini_provider: GeminiProvider, redis_manager=None,
                 cache_strategy: CacheStrategy = CacheStrategy.BALANCED,
                 token_budget_limit: int = 1000000):  # 默认100万token预算
        """
        初始化智能Token管理器
        
        Args:
            gemini_provider: Gemini提供商实例
            redis_manager: Redis管理器
            cache_strategy: 缓存策略
            token_budget_limit: Token预算限制
        """
        self.gemini_provider = gemini_provider
        self.cache_manager = ContextCacheManager(
            redis_manager=redis_manager,
            cache_strategy=cache_strategy
        )
        self.token_budget_limit = token_budget_limit
        
        # Token使用记录
        self.usage_records: List[TokenUsageRecord] = []
        self.optimization_stats = TokenOptimizationStats()
        
        # 实时统计
        self.session_tokens: Dict[str, int] = {}  # session_id -> total_tokens
        self.daily_tokens: Dict[str, int] = {}    # date -> total_tokens
        self.current_budget_used = 0
        
        # Gemini 2.5系列定价配置（美元每100万token）
        self.pricing_config = {
            "gemini-2.5-pro": {
                "input": 1.25,
                "output": 10.0,
                "cache": 0.3125,
                "storage_per_hour": 4.50
            },
            "gemini-2.5-flash": {
                "input": 0.30,
                "output": 2.50,
                "cache": 0.075,
                "storage_per_hour": 1.0
            },
            "gemini-2.5-flash-lite": {
                "input": 0.10,
                "output": 0.40,
                "cache": 0.025,
                "storage_per_hour": 1.0
            }
        }
        
        logger.info(f"IntelligentTokenManager initialized: budget={token_budget_limit:,}, strategy={cache_strategy.value}")
    
    async def count_tokens_accurately(self, text: str, model: str = "gemini-2.5-flash") -> int:
        """
        使用Gemini真实API精确计算token数量
        
        Args:
            text: 要计算的文本
            model: 使用的模型
            
        Returns:
            精确的token数量
        """
        try:
            # 使用Gemini Provider的真实API计数
            token_count = await self.gemini_provider.count_tokens(text, model)
            
            logger.debug(f"📊 精确token计数: {token_count} tokens, 文本长度: {len(text)} 字符")
            return token_count
            
        except Exception as e:
            logger.error(f"精确token计数失败: {e}")
            # 回退到估算
            return self._fallback_token_estimation(text)
    
    def _fallback_token_estimation(self, text: str) -> int:
        """回退token估算方法"""
        if not text:
            return 0
        
        # 使用Provider的回退方法
        return self.gemini_provider._accurate_token_estimation_fallback(text)
    
    async def optimize_messages_with_cache(self, messages: List[Dict[str, Any]], 
                                         model: str = "gemini-2.5-flash",
                                         session_id: Optional[str] = None) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        使用缓存优化消息列表，减少token消耗
        
        Args:
            messages: 原始消息列表
            model: 使用的模型
            session_id: 会话ID
            
        Returns:
            (优化后的消息, 优化统计信息)
        """
        try:
            optimization_info = {
                "original_messages": len(messages),
                "original_tokens": 0,
                "optimized_tokens": 0,
                "tokens_saved": 0,
                "cost_saved": 0.0,
                "cache_operations": []
            }
            
            optimized_messages = []
            
            for i, message in enumerate(messages):
                content = message.get('content', '')
                if not content:
                    optimized_messages.append(message)
                    continue
                
                # 计算原始token数
                original_tokens = await self.count_tokens_accurately(content, model)
                optimization_info["original_tokens"] += original_tokens
                
                # 检查是否应该缓存
                should_cache = await self.cache_manager.should_cache_content(
                    content, f"session:{session_id}" if session_id else ""
                )
                
                if should_cache:
                    # 尝试缓存内容
                    cache_id = await self.cache_manager.cache_content(content, model)
                    if cache_id:
                        # 创建优化的消息
                        optimized_message = message.copy()
                        optimized_message['content'] = f"[CACHED:{cache_id}]"
                        optimized_message['_original_tokens'] = original_tokens
                        optimized_message['_cache_id'] = cache_id
                        
                        optimized_messages.append(optimized_message)
                        
                        # 缓存后的token计算（引用token很少）
                        cached_reference_tokens = await self.count_tokens_accurately(
                            f"[CACHED:{cache_id}]", model
                        )
                        optimization_info["optimized_tokens"] += cached_reference_tokens
                        
                        saved_tokens = original_tokens - cached_reference_tokens
                        optimization_info["tokens_saved"] += saved_tokens
                        
                        # 计算成本节省
                        cost_saved = self._calculate_cost_savings(saved_tokens, model)
                        optimization_info["cost_saved"] += cost_saved
                        
                        optimization_info["cache_operations"].append({
                            "message_index": i,
                            "action": "cached",
                            "cache_id": cache_id,
                            "original_tokens": original_tokens,
                            "cached_tokens": cached_reference_tokens,
                            "tokens_saved": saved_tokens,
                            "cost_saved": cost_saved
                        })
                        
                        logger.debug(f"✅ 消息{i}已缓存，节省{saved_tokens}个token")
                        continue
                
                # 检查是否可以使用现有缓存
                optimized_msg, used_cache_ids = self.cache_manager.optimize_messages_for_cache([message])
                if used_cache_ids:
                    cached_tokens = await self.count_tokens_accurately(
                        optimized_msg[0]['content'], model
                    )
                    optimization_info["optimized_tokens"] += cached_tokens
                    
                    saved_tokens = original_tokens - cached_tokens
                    optimization_info["tokens_saved"] += saved_tokens
                    optimization_info["cost_saved"] += self._calculate_cost_savings(saved_tokens, model)
                    
                    optimized_messages.extend(optimized_msg)
                    
                    optimization_info["cache_operations"].append({
                        "message_index": i,
                        "action": "cache_hit",
                        "cache_ids": used_cache_ids,
                        "original_tokens": original_tokens,
                        "cached_tokens": cached_tokens,
                        "tokens_saved": saved_tokens
                    })
                    
                    logger.debug(f"🎯 消息{i}使用现有缓存，节省{saved_tokens}个token")
                else:
                    # 没有缓存优化，保持原样
                    optimized_messages.append(message)
                    optimization_info["optimized_tokens"] += original_tokens
            
            # 计算优化效率
            if optimization_info["original_tokens"] > 0:
                optimization_info["optimization_ratio"] = (
                    optimization_info["tokens_saved"] / optimization_info["original_tokens"]
                )
            else:
                optimization_info["optimization_ratio"] = 0.0
            
            logger.info(f"🚀 消息优化完成: 原始{optimization_info['original_tokens']:,}token → "
                       f"优化后{optimization_info['optimized_tokens']:,}token, "
                       f"节省{optimization_info['tokens_saved']:,}token "
                       f"({optimization_info['optimization_ratio']:.1%})")
            
            return optimized_messages, optimization_info
            
        except Exception as e:
            logger.error(f"消息优化失败: {e}")
            return messages, {"error": str(e)}
    
    def _calculate_cost_savings(self, tokens_saved: int, model: str) -> float:
        """计算节省的成本"""
        try:
            pricing = self.pricing_config.get(model, self.pricing_config["gemini-2.5-flash"])
            input_cost_per_million = pricing["input"]
            
            cost_saved = (tokens_saved / 1_000_000) * input_cost_per_million
            return cost_saved
            
        except Exception as e:
            logger.warning(f"计算成本节省失败: {e}")
            return 0.0
    
    async def record_token_usage(self, prompt_tokens: int, completion_tokens: int,
                               model: str, provider: str = "gemini",
                               task_id: str = "", session_id: Optional[str] = None,
                               cached_tokens: int = 0, cache_hits: int = 0) -> str:
        """
        记录token使用情况
        
        Args:
            prompt_tokens: 输入token数
            completion_tokens: 输出token数
            model: 使用的模型
            provider: 提供商
            task_id: 任务ID
            session_id: 会话ID
            cached_tokens: 缓存token数
            cache_hits: 缓存命中次数
            
        Returns:
            记录ID
        """
        try:
            total_tokens = prompt_tokens + completion_tokens
            estimated_cost = self._calculate_request_cost(
                prompt_tokens, completion_tokens, model, cached_tokens
            )
            
            # 创建使用记录
            record = TokenUsageRecord(
                timestamp=time.time(),
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                model=model,
                provider=provider,
                task_id=task_id,
                session_id=session_id,
                cached_tokens=cached_tokens,
                cache_hits=cache_hits,
                estimated_cost=estimated_cost,
                actual_api_call=True
            )
            
            # 添加到记录列表
            self.usage_records.append(record)
            
            # 更新统计
            self.current_budget_used += total_tokens
            
            if session_id:
                self.session_tokens[session_id] = self.session_tokens.get(session_id, 0) + total_tokens
            
            date_key = datetime.now().strftime("%Y-%m-%d")
            self.daily_tokens[date_key] = self.daily_tokens.get(date_key, 0) + total_tokens
            
            # 更新优化统计
            self.optimization_stats.total_requests += 1
            if cached_tokens > 0:
                self.optimization_stats.total_tokens_saved += cached_tokens
                self.optimization_stats.total_cost_saved += self._calculate_cost_savings(cached_tokens, model)
            
            if cache_hits > 0:
                hit_ratio = cache_hits / (cache_hits + 1)  # 简化计算
                self.optimization_stats.cache_hit_ratio = (
                    (self.optimization_stats.cache_hit_ratio * (self.optimization_stats.total_requests - 1) + hit_ratio) 
                    / self.optimization_stats.total_requests
                )
            
            # 检查预算限制
            if self.current_budget_used > self.token_budget_limit * 0.9:  # 90%预警
                logger.warning(f"⚠️ Token预算接近限制: {self.current_budget_used:,}/{self.token_budget_limit:,} "
                             f"({self.current_budget_used/self.token_budget_limit:.1%})")
            
            record_id = f"token_record_{int(record.timestamp)}_{task_id[:8]}"
            
            logger.info(f"📊 Token使用已记录: {total_tokens:,}token, 成本: ${estimated_cost:.6f}, "
                       f"缓存节省: {cached_tokens:,}token")
            
            return record_id
            
        except Exception as e:
            logger.error(f"记录token使用失败: {e}")
            return ""
    
    def _calculate_request_cost(self, prompt_tokens: int, completion_tokens: int, 
                              model: str, cached_tokens: int = 0) -> float:
        """计算请求成本"""
        try:
            pricing = self.pricing_config.get(model, self.pricing_config["gemini-2.5-flash"])
            
            # 计算实际输入token成本（减去缓存部分）
            actual_input_tokens = max(0, prompt_tokens - cached_tokens)
            input_cost = (actual_input_tokens / 1_000_000) * pricing["input"]
            
            # 缓存成本
            cache_cost = (cached_tokens / 1_000_000) * pricing["cache"]
            
            # 输出成本
            output_cost = (completion_tokens / 1_000_000) * pricing["output"]
            
            total_cost = input_cost + cache_cost + output_cost
            return total_cost
            
        except Exception as e:
            logger.warning(f"计算请求成本失败: {e}")
            return 0.0
    
    async def get_optimization_recommendations(self) -> Dict[str, Any]:
        """获取token优化建议"""
        try:
            recommendations = {
                "current_status": {
                    "budget_used": self.current_budget_used,
                    "budget_limit": self.token_budget_limit,
                    "usage_percentage": self.current_budget_used / self.token_budget_limit * 100,
                    "total_requests": len(self.usage_records)
                },
                "optimization_stats": asdict(self.optimization_stats),
                "recommendations": []
            }
            
            # 分析近期使用模式
            recent_records = self.usage_records[-100:]  # 最近100次请求
            if recent_records:
                avg_tokens = sum(r.total_tokens for r in recent_records) / len(recent_records)
                avg_cost = sum(r.estimated_cost for r in recent_records) / len(recent_records)
                
                recommendations["recent_analysis"] = {
                    "avg_tokens_per_request": avg_tokens,
                    "avg_cost_per_request": avg_cost,
                    "cache_usage_rate": sum(1 for r in recent_records if r.cached_tokens > 0) / len(recent_records)
                }
                
                # 生成建议
                if avg_tokens > 10000:
                    recommendations["recommendations"].append({
                        "type": "high_token_usage",
                        "message": f"平均请求使用{avg_tokens:.0f}token，建议启用更积极的缓存策略",
                        "action": "考虑使用AGGRESSIVE缓存策略"
                    })
                
                cache_rate = recommendations["recent_analysis"]["cache_usage_rate"]
                if cache_rate < 0.3:
                    recommendations["recommendations"].append({
                        "type": "low_cache_usage",
                        "message": f"缓存使用率仅{cache_rate:.1%}，可优化空间较大",
                        "action": "检查内容重复性，优化缓存策略"
                    })
                
                if self.current_budget_used > self.token_budget_limit * 0.8:
                    recommendations["recommendations"].append({
                        "type": "budget_warning",
                        "message": f"已使用{self.current_budget_used/self.token_budget_limit:.1%}预算",
                        "action": "考虑使用更便宜的模型或增加预算"
                    })
            
            # 模型成本分析
            model_usage = {}
            for record in recent_records:
                if record.model not in model_usage:
                    model_usage[record.model] = {"count": 0, "total_cost": 0.0}
                model_usage[record.model]["count"] += 1
                model_usage[record.model]["total_cost"] += record.estimated_cost
            
            if model_usage:
                most_expensive = max(model_usage.keys(), 
                                   key=lambda k: model_usage[k]["total_cost"])
                
                recommendations["model_analysis"] = {
                    "most_used_model": max(model_usage.keys(), 
                                         key=lambda k: model_usage[k]["count"]),
                    "most_expensive_model": most_expensive,
                    "model_breakdown": model_usage
                }
                
                # 如果使用昂贵模型，建议优化
                if most_expensive.endswith("-pro"):
                    recommendations["recommendations"].append({
                        "type": "expensive_model",
                        "message": f"主要使用{most_expensive}，成本较高",
                        "action": "考虑对简单任务使用flash或flash-lite模型"
                    })
            
            return recommendations
            
        except Exception as e:
            logger.error(f"生成优化建议失败: {e}")
            return {"error": str(e)}
    
    async def get_detailed_statistics(self) -> Dict[str, Any]:
        """获取详细的token使用统计"""
        try:
            stats = {
                "summary": {
                    "total_requests": len(self.usage_records),
                    "total_tokens": sum(r.total_tokens for r in self.usage_records),
                    "total_cost": sum(r.estimated_cost for r in self.usage_records),
                    "total_cached_tokens": sum(r.cached_tokens for r in self.usage_records),
                    "current_budget_used": self.current_budget_used,
                    "budget_remaining": max(0, self.token_budget_limit - self.current_budget_used)
                },
                "optimization": asdict(self.optimization_stats),
                "daily_usage": self.daily_tokens,
                "session_usage": dict(list(self.session_tokens.items())[:10]),  # 前10个会话
                "cache_stats": await self.cache_manager.get_cache_statistics()
            }
            
            # 时间段分析
            if self.usage_records:
                recent_24h = [r for r in self.usage_records 
                             if time.time() - r.timestamp < 24 * 3600]
                recent_1h = [r for r in self.usage_records 
                            if time.time() - r.timestamp < 3600]
                
                stats["time_analysis"] = {
                    "last_24h_requests": len(recent_24h),
                    "last_24h_tokens": sum(r.total_tokens for r in recent_24h),
                    "last_1h_requests": len(recent_1h),
                    "last_1h_tokens": sum(r.total_tokens for r in recent_1h)
                }
            
            return stats
            
        except Exception as e:
            logger.error(f"获取详细统计失败: {e}")
            return {"error": str(e)}
    
    async def reset_budget(self, new_limit: int):
        """重置token预算"""
        try:
            old_limit = self.token_budget_limit
            self.token_budget_limit = new_limit
            self.current_budget_used = 0
            
            logger.info(f"Token预算已重置: {old_limit:,} → {new_limit:,}")
            
        except Exception as e:
            logger.error(f"重置预算失败: {e}")
    
    async def cleanup_old_records(self, days_to_keep: int = 30):
        """清理旧的使用记录"""
        try:
            cutoff_time = time.time() - (days_to_keep * 24 * 3600)
            
            old_count = len(self.usage_records)
            self.usage_records = [r for r in self.usage_records if r.timestamp > cutoff_time]
            new_count = len(self.usage_records)
            
            cleaned = old_count - new_count
            if cleaned > 0:
                logger.info(f"清理了{cleaned}条{days_to_keep}天前的token使用记录")
            
        except Exception as e:
            logger.error(f"清理旧记录失败: {e}")