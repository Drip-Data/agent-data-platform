"""
记忆管理器 - 提供持久化的会话记忆和跨任务学习能力
Memory Manager - Provides persistent conversation memory and cross-task learning capabilities
"""

import asyncio
import json
import logging
import time
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
import hashlib

logger = logging.getLogger(__name__)

@dataclass
class ConversationStep:
    """会话步骤记录"""
    step_id: str
    task_id: str
    session_id: str
    timestamp: float
    user_input: Optional[str] = None
    agent_output: Optional[str] = None
    thinking_summary: Optional[str] = None
    tools_used: List[str] = None
    success: bool = True
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.tools_used is None:
            self.tools_used = []
        if self.metadata is None:
            self.metadata = {}

@dataclass
class SessionSummary:
    """会话摘要"""
    session_id: str
    start_time: float
    end_time: float
    total_steps: int
    successful_steps: int
    main_topics: List[str]
    key_insights: List[str]
    tools_used: List[str]
    
    def __post_init__(self):
        if self.main_topics is None:
            self.main_topics = []
        if self.key_insights is None:
            self.key_insights = []
        if self.tools_used is None:
            self.tools_used = []

class MemoryManager:
    """
    记忆管理器 - 提供持久化的会话记忆和跨任务学习能力
    
    功能:
    1. 存储和检索会话历史
    2. 生成会话摘要和洞察
    3. 跨任务和跨会话的记忆持久化
    4. 为LLM提供上下文记忆注入
    """
    
    def __init__(self, redis_manager=None, max_memory_entries: int = 1000, 
                 max_context_length: int = 4000):
        """
        初始化记忆管理器
        
        Args:
            redis_manager: Redis管理器实例，用于持久化存储
            max_memory_entries: 最大记忆条目数量
            max_context_length: 最大上下文长度（字符）
        """
        self.redis_manager = redis_manager
        self.max_memory_entries = max_memory_entries
        self.max_context_length = max_context_length
        
        # 检查是否使用Redis
        if redis_manager and not redis_manager.is_fallback_mode():
            self.use_redis = True
            self.redis = None  # 将在需要时初始化
        else:
            self.use_redis = False
            self.redis = None
            logger.warning("MemoryManager运行在内存模式，记忆不会持久化")
        
        # 内存缓存
        self._memory_cache: Dict[str, ConversationStep] = {}
        self._session_cache: Dict[str, SessionSummary] = {}
        self._context_cache: Dict[str, List[ConversationStep]] = {}
        
        # 统计信息
        self._stats = {
            "total_conversations": 0,
            "total_steps": 0,
            "cache_hits": 0,
            "cache_misses": 0
        }
        
        logger.info(f"MemoryManager initialized: use_redis={self.use_redis}, max_entries={max_memory_entries}")
    
    async def _get_redis_client(self):
        """获取Redis客户端"""
        if self.use_redis and self.redis is None:
            import redis.asyncio as redis
            self.redis = redis.from_url(self.redis_manager.get_redis_url())
        return self.redis
    
    async def store_conversation_step(self, task_id: str, session_id: str, 
                                    user_input: Optional[str] = None,
                                    agent_output: Optional[str] = None,
                                    thinking_summary: Optional[str] = None,
                                    tools_used: List[str] = None,
                                    success: bool = True,
                                    error_message: Optional[str] = None,
                                    metadata: Dict[str, Any] = None) -> str:
        """
        存储会话步骤
        
        Args:
            task_id: 任务ID
            session_id: 会话ID
            user_input: 用户输入
            agent_output: Agent输出
            thinking_summary: 思考摘要
            tools_used: 使用的工具列表
            success: 是否成功
            error_message: 错误信息
            metadata: 元数据
            
        Returns:
            步骤ID
        """
        try:
            # 生成步骤ID
            step_id = f"{session_id}_{task_id}_{int(time.time() * 1000)}"
            
            # 创建会话步骤
            step = ConversationStep(
                step_id=step_id,
                task_id=task_id,
                session_id=session_id,
                timestamp=time.time(),
                user_input=user_input,
                agent_output=agent_output,
                thinking_summary=thinking_summary,
                tools_used=tools_used or [],
                success=success,
                error_message=error_message,
                metadata=metadata or {}
            )
            
            # 存储到缓存
            self._memory_cache[step_id] = step
            
            # 存储到Redis（如果可用）
            if self.use_redis:
                redis_client = await self._get_redis_client()
                if redis_client:
                    # 存储单个步骤
                    await redis_client.hset(
                        f"memory:step:{step_id}",
                        mapping={
                            "data": json.dumps(asdict(step)),
                            "timestamp": str(step.timestamp)
                        }
                    )
                    
                    # 添加到会话索引
                    await redis_client.zadd(
                        f"memory:session:{session_id}",
                        {step_id: step.timestamp}
                    )
                    
                    # 设置过期时间（30天）
                    await redis_client.expire(f"memory:step:{step_id}", 30 * 24 * 3600)
                    await redis_client.expire(f"memory:session:{session_id}", 30 * 24 * 3600)
            
            # 更新统计
            self._stats["total_steps"] += 1
            
            # 清理旧的缓存条目
            if len(self._memory_cache) > self.max_memory_entries:
                await self._cleanup_old_cache_entries()
            
            logger.debug(f"Stored conversation step: {step_id}")
            return step_id
            
        except Exception as e:
            logger.error(f"Failed to store conversation step: {e}")
            raise
    
    async def get_conversation_context(self, session_id: str, 
                                     max_steps: int = 10,
                                     max_age_hours: int = 24) -> List[ConversationStep]:
        """
        获取会话上下文
        
        Args:
            session_id: 会话ID
            max_steps: 最大步骤数
            max_age_hours: 最大年龄（小时）
            
        Returns:
            会话步骤列表
        """
        try:
            # 检查缓存
            cache_key = f"context:{session_id}:{max_steps}:{max_age_hours}"
            if cache_key in self._context_cache:
                self._stats["cache_hits"] += 1
                return self._context_cache[cache_key]
            
            self._stats["cache_misses"] += 1
            
            # 计算时间范围
            min_timestamp = time.time() - (max_age_hours * 3600)
            steps = []
            
            if self.use_redis:
                # 从Redis获取
                redis_client = await self._get_redis_client()
                if redis_client:
                    # 获取会话中的步骤ID（按时间倒序）
                    step_ids = await redis_client.zrevrangebyscore(
                        f"memory:session:{session_id}",
                        "+inf", min_timestamp,
                        start=0, num=max_steps
                    )
                    
                    # 获取步骤详情
                    for step_id in step_ids:
                        step_data = await redis_client.hget(f"memory:step:{step_id}", "data")
                        if step_data:
                            step_dict = json.loads(step_data)
                            steps.append(ConversationStep(**step_dict))
            
            # 从内存缓存补充
            for step in self._memory_cache.values():
                if (step.session_id == session_id and 
                    step.timestamp >= min_timestamp and
                    len(steps) < max_steps):
                    if not any(s.step_id == step.step_id for s in steps):
                        steps.append(step)
            
            # 按时间排序
            steps.sort(key=lambda x: x.timestamp, reverse=True)
            steps = steps[:max_steps]
            
            # 缓存结果
            self._context_cache[cache_key] = steps
            
            logger.debug(f"Retrieved {len(steps)} conversation steps for session {session_id}")
            return steps
            
        except Exception as e:
            logger.error(f"Failed to get conversation context: {e}")
            return []
    
    async def generate_context_summary(self, session_id: str, 
                                     max_steps: int = 20) -> str:
        """
        生成上下文摘要，用于LLM上下文注入
        
        Args:
            session_id: 会话ID
            max_steps: 最大步骤数
            
        Returns:
            格式化的上下文摘要
        """
        try:
            steps = await self.get_conversation_context(session_id, max_steps)
            
            if not steps:
                return "暂无历史会话记录。"
            
            # 构建摘要
            summary_parts = []
            summary_parts.append(f"=== 会话历史摘要 (最近{len(steps)}步) ===")
            
            # 成功和失败统计
            successful_steps = sum(1 for step in steps if step.success)
            failed_steps = len(steps) - successful_steps
            summary_parts.append(f"成功步骤: {successful_steps}, 失败步骤: {failed_steps}")
            
            # 主要工具使用情况
            all_tools = []
            for step in steps:
                all_tools.extend(step.tools_used)
            tool_usage = {}
            for tool in all_tools:
                tool_usage[tool] = tool_usage.get(tool, 0) + 1
            
            if tool_usage:
                top_tools = sorted(tool_usage.items(), key=lambda x: x[1], reverse=True)[:5]
                summary_parts.append(f"主要工具: {', '.join([f'{tool}({count})' for tool, count in top_tools])}")
            
            # 关键对话摘要
            key_interactions = []
            for step in steps[-5:]:  # 最近5步
                if step.user_input and step.agent_output:
                    # 截断长文本
                    user_input = step.user_input[:100] + "..." if len(step.user_input) > 100 else step.user_input
                    agent_output = step.agent_output[:150] + "..." if len(step.agent_output) > 150 else step.agent_output
                    
                    key_interactions.append(f"用户: {user_input}")
                    key_interactions.append(f"助手: {agent_output}")
            
            if key_interactions:
                summary_parts.append("最近对话:")
                summary_parts.extend(key_interactions[-6:])  # 最多显示3轮对话
            
            # 控制总长度
            full_summary = "\n".join(summary_parts)
            if len(full_summary) > self.max_context_length:
                # 截断到最大长度
                full_summary = full_summary[:self.max_context_length] + "...\n(上下文已截断)"
            
            return full_summary
            
        except Exception as e:
            logger.error(f"Failed to generate context summary: {e}")
            return "生成上下文摘要时出错。"
    
    async def store_session_summary(self, session_id: str, 
                                  main_topics: List[str] = None,
                                  key_insights: List[str] = None) -> bool:
        """
        存储会话摘要
        
        Args:
            session_id: 会话ID
            main_topics: 主要话题
            key_insights: 关键洞察
            
        Returns:
            是否成功
        """
        try:
            # 获取会话步骤
            steps = await self.get_conversation_context(session_id, max_steps=1000)
            
            if not steps:
                return False
            
            # 生成摘要
            summary = SessionSummary(
                session_id=session_id,
                start_time=min(step.timestamp for step in steps),
                end_time=max(step.timestamp for step in steps),
                total_steps=len(steps),
                successful_steps=sum(1 for step in steps if step.success),
                main_topics=main_topics or [],
                key_insights=key_insights or [],
                tools_used=list(set(tool for step in steps for tool in step.tools_used))
            )
            
            # 存储到缓存
            self._session_cache[session_id] = summary
            
            # 存储到Redis
            if self.use_redis:
                redis_client = await self._get_redis_client()
                if redis_client:
                    await redis_client.hset(
                        f"memory:session_summary:{session_id}",
                        mapping={
                            "data": json.dumps(asdict(summary)),
                            "end_time": str(summary.end_time)
                        }
                    )
                    # 设置过期时间（90天）
                    await redis_client.expire(f"memory:session_summary:{session_id}", 90 * 24 * 3600)
            
            logger.info(f"Stored session summary for {session_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to store session summary: {e}")
            return False
    
    async def get_cross_session_insights(self, limit: int = 5) -> List[str]:
        """
        获取跨会话洞察
        
        Args:
            limit: 返回的洞察数量限制
            
        Returns:
            洞察列表
        """
        try:
            insights = []
            
            # 从缓存和Redis收集洞察
            all_summaries = list(self._session_cache.values())
            
            if self.use_redis:
                redis_client = await self._get_redis_client()
                if redis_client:
                    # 获取所有会话摘要
                    keys = await redis_client.keys("memory:session_summary:*")
                    for key in keys[:20]:  # 限制查询数量
                        summary_data = await redis_client.hget(key, "data")
                        if summary_data:
                            summary_dict = json.loads(summary_data)
                            summary = SessionSummary(**summary_dict)
                            if summary.session_id not in self._session_cache:
                                all_summaries.append(summary)
            
            # 分析跨会话模式
            if all_summaries:
                # 分析常用工具
                tool_usage = {}
                for summary in all_summaries:
                    for tool in summary.tools_used:
                        tool_usage[tool] = tool_usage.get(tool, 0) + 1
                
                if tool_usage:
                    top_tools = sorted(tool_usage.items(), key=lambda x: x[1], reverse=True)[:3]
                    insights.append(f"最常用工具: {', '.join([f'{tool}({count}次)' for tool, count in top_tools])}")
                
                # 分析成功率
                total_steps = sum(s.total_steps for s in all_summaries)
                successful_steps = sum(s.successful_steps for s in all_summaries)
                if total_steps > 0:
                    success_rate = successful_steps / total_steps
                    insights.append(f"整体成功率: {success_rate:.1%} ({successful_steps}/{total_steps})")
                
                # 分析活跃时段
                recent_sessions = len([s for s in all_summaries if s.end_time > time.time() - 7*24*3600])
                insights.append(f"最近7天活跃会话: {recent_sessions}个")
            
            return insights[:limit]
            
        except Exception as e:
            logger.error(f"Failed to get cross-session insights: {e}")
            return []
    
    async def _cleanup_old_cache_entries(self):
        """清理旧的缓存条目"""
        try:
            # 按时间排序，删除最旧的条目
            if len(self._memory_cache) > self.max_memory_entries:
                sorted_steps = sorted(
                    self._memory_cache.items(),
                    key=lambda x: x[1].timestamp
                )
                
                # 删除最旧的条目
                entries_to_remove = len(self._memory_cache) - self.max_memory_entries + 100
                for step_id, _ in sorted_steps[:entries_to_remove]:
                    del self._memory_cache[step_id]
                
                logger.debug(f"Cleaned up {entries_to_remove} old cache entries")
            
            # 清理上下文缓存
            if len(self._context_cache) > 100:
                # 简单清理：删除一半
                keys_to_remove = list(self._context_cache.keys())[:50]
                for key in keys_to_remove:
                    del self._context_cache[key]
                    
        except Exception as e:
            logger.error(f"Failed to cleanup cache: {e}")
    
    async def get_memory_stats(self) -> Dict[str, Any]:
        """获取记忆统计信息"""
        try:
            stats = self._stats.copy()
            stats.update({
                "cache_size": len(self._memory_cache),
                "session_cache_size": len(self._session_cache),
                "context_cache_size": len(self._context_cache),
                "use_redis": self.use_redis,
                "max_memory_entries": self.max_memory_entries,
                "max_context_length": self.max_context_length
            })
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get memory stats: {e}")
            return {"error": str(e)}
    
    async def clear_memory(self, session_id: Optional[str] = None):
        """
        清理记忆
        
        Args:
            session_id: 要清理的会话ID，如果为None则清理所有
        """
        try:
            if session_id:
                # 清理特定会话
                steps_to_remove = [
                    step_id for step_id, step in self._memory_cache.items()
                    if step.session_id == session_id
                ]
                
                for step_id in steps_to_remove:
                    del self._memory_cache[step_id]
                
                if session_id in self._session_cache:
                    del self._session_cache[session_id]
                
                # 清理上下文缓存中与该会话相关的缓存
                context_keys_to_remove = [
                    key for key in self._context_cache.keys()
                    if session_id in key
                ]
                for key in context_keys_to_remove:
                    del self._context_cache[key]
                
                # 清理Redis
                if self.use_redis:
                    redis_client = await self._get_redis_client()
                    if redis_client:
                        # 删除会话相关的所有键
                        keys = await redis_client.keys(f"memory:*:{session_id}*")
                        if keys:
                            await redis_client.delete(*keys)
                
                logger.info(f"Cleared memory for session {session_id}")
            else:
                # 清理所有记忆
                self._memory_cache.clear()
                self._session_cache.clear()
                self._context_cache.clear()
                
                if self.use_redis:
                    redis_client = await self._get_redis_client()
                    if redis_client:
                        keys = await redis_client.keys("memory:*")
                        if keys:
                            await redis_client.delete(*keys)
                
                logger.info("Cleared all memory")
                
        except Exception as e:
            logger.error(f"Failed to clear memory: {e}")
    
    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        try:
            health = {
                "status": "healthy",
                "timestamp": time.time(),
                "cache_size": len(self._memory_cache),
                "redis_available": False
            }
            
            # 检查Redis连接
            if self.use_redis:
                try:
                    redis_client = await self._get_redis_client()
                    if redis_client:
                        await redis_client.ping()
                        health["redis_available"] = True
                except:
                    health["redis_available"] = False
                    health["status"] = "degraded"
            
            return health
            
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "timestamp": time.time()
            }