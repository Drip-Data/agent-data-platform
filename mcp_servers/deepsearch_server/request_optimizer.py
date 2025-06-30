#!/usr/bin/env python3
"""
请求优化器 - LLM调用合并和优化策略
减少LLM调用次数，提升整体性能
"""

import asyncio
import logging
import time
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)

@dataclass
class LLMRequest:
    """LLM请求数据结构"""
    task_type: str  # "query_generation", "search_execution", "reflection", "synthesis"
    prompt: str
    priority: int = 1  # 1=高优先级, 2=中优先级, 3=低优先级
    timeout: float = 120.0  # 增加到120秒
    created_at: datetime = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()

class RequestOptimizer:
    """请求优化器 - 合并和优化LLM调用"""
    
    def __init__(self, llm_client, batch_size: int = 3, batch_timeout: float = 2.0, 
                 max_concurrent_requests: int = 5, default_timeout: float = 120.0):  # 增加到120秒
        self.llm_client = llm_client
        self.batch_size = batch_size
        self.batch_timeout = batch_timeout
        self.max_concurrent_requests = max_concurrent_requests
        self.default_timeout = default_timeout
        
        # 请求队列和批处理
        self._pending_requests: List[Tuple[LLMRequest, asyncio.Future]] = []
        self._batch_lock = asyncio.Lock()
        self._batch_task = None
        
        # 并发控制
        self._active_requests = 0
        self._concurrent_lock = asyncio.Lock()
        self._request_semaphore = asyncio.Semaphore(max_concurrent_requests)
        
        # 性能统计
        self.stats = {
            "total_requests": 0,
            "merged_requests": 0,
            "batch_calls": 0,
            "time_saved_seconds": 0.0,
            "timeout_errors": 0,
            "concurrent_limit_hits": 0,
            "max_concurrent_reached": 0
        }
    
    async def execute_request(self, request: LLMRequest) -> str:
        """执行LLM请求（可能会批处理）"""
        self.stats["total_requests"] += 1
        
        # 检查并发限制
        async with self._concurrent_lock:
            if self._active_requests >= self.max_concurrent_requests:
                self.stats["concurrent_limit_hits"] += 1
                logger.warning(f"Concurrent request limit reached: {self._active_requests}/{self.max_concurrent_requests}")
        
        # 使用信号量控制并发
        async with self._request_semaphore:
            async with self._concurrent_lock:
                self._active_requests += 1
                if self._active_requests > self.stats["max_concurrent_reached"]:
                    self.stats["max_concurrent_reached"] = self._active_requests
            
            try:
                # 创建Future用于异步等待结果
                future = asyncio.Future()
                
                async with self._batch_lock:
                    self._pending_requests.append((request, future))
                    
                    # 如果达到批处理条件，立即处理
                    if len(self._pending_requests) >= self.batch_size:
                        await self._process_batch()
                    else:
                        # 启动批处理超时任务
                        if self._batch_task is None or self._batch_task.done():
                            self._batch_task = asyncio.create_task(self._batch_timeout_handler())
                
                # 等待结果并应用超时控制
                timeout = request.timeout if request.timeout > 0 else self.default_timeout
                try:
                    result = await asyncio.wait_for(future, timeout=timeout)
                    return result
                except asyncio.TimeoutError:
                    self.stats["timeout_errors"] += 1
                    logger.error(f"Request timeout after {timeout}s for task: {request.task_type}")
                    raise TimeoutError(f"LLM request timed out after {timeout}s")
                    
            finally:
                async with self._concurrent_lock:
                    self._active_requests -= 1
    
    async def _batch_timeout_handler(self):
        """批处理超时处理器"""
        try:
            await asyncio.sleep(self.batch_timeout)
            async with self._batch_lock:
                if self._pending_requests:
                    await self._process_batch()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Batch timeout handler error: {e}")
    
    async def _process_batch(self):
        """处理当前批次的请求"""
        if not self._pending_requests:
            return
        
        current_batch = self._pending_requests.copy()
        self._pending_requests.clear()
        
        # 取消批处理超时任务
        if self._batch_task and not self._batch_task.done():
            self._batch_task.cancel()
        
        logger.info(f"Processing batch of {len(current_batch)} requests")
        
        try:
            # 尝试合并兼容的请求
            merged_groups = self._group_compatible_requests(current_batch)
            
            for group in merged_groups:
                if len(group) > 1:
                    # 合并处理
                    await self._process_merged_group(group)
                    self.stats["merged_requests"] += len(group)
                else:
                    # 单独处理
                    await self._process_single_request(group[0])
                
                self.stats["batch_calls"] += 1
                
        except Exception as e:
            logger.error(f"Batch processing error: {e}")
            # 失败时回退到单独处理
            for request, future in current_batch:
                if not future.done():
                    try:
                        result = await self._execute_single_llm_call(request.prompt)
                        future.set_result(result)
                    except Exception as single_error:
                        future.set_exception(single_error)
    
    def _group_compatible_requests(self, requests: List[Tuple[LLMRequest, asyncio.Future]]) -> List[List[Tuple[LLMRequest, asyncio.Future]]]:
        """将兼容的请求分组"""
        groups = []
        
        # 按任务类型分组
        task_groups = {}
        for request, future in requests:
            task_type = request.task_type
            if task_type not in task_groups:
                task_groups[task_type] = []
            task_groups[task_type].append((request, future))
        
        # 对于某些任务类型，尝试进一步合并
        for task_type, group in task_groups.items():
            if task_type in ["search_execution", "query_generation"] and len(group) > 1:
                # 这些任务类型可以尝试合并
                merged_group = self._try_merge_similar_tasks(group)
                groups.extend(merged_group)
            else:
                # 其他任务类型单独处理
                for item in group:
                    groups.append([item])
        
        return groups
    
    def _try_merge_similar_tasks(self, group: List[Tuple[LLMRequest, asyncio.Future]]) -> List[List[Tuple[LLMRequest, asyncio.Future]]]:
        """尝试合并相似任务"""
        # 简单策略：如果prompts相似度高，可以合并
        if len(group) <= 1:
            return [[item] for item in group]
        
        # 当前简单实现：将小批量分组
        merged_groups = []
        for i in range(0, len(group), 2):  # 每2个一组
            subgroup = group[i:i+2]
            merged_groups.append(subgroup)
        
        return merged_groups
    
    async def _process_merged_group(self, group: List[Tuple[LLMRequest, asyncio.Future]]):
        """处理合并的请求组"""
        try:
            if len(group) == 2:
                # 双请求合并
                await self._process_dual_requests(group)
            else:
                # 多请求合并（当前回退到单独处理）
                for request, future in group:
                    await self._process_single_request((request, future))
                    
        except Exception as e:
            logger.error(f"Merged group processing error: {e}")
            # 错误时回退到单独处理
            for request, future in group:
                if not future.done():
                    try:
                        result = await self._execute_single_llm_call(request.prompt)
                        future.set_result(result)
                    except Exception as single_error:
                        future.set_exception(single_error)
    
    async def _process_dual_requests(self, dual_group: List[Tuple[LLMRequest, asyncio.Future]]):
        """处理双请求合并"""
        req1, future1 = dual_group[0]
        req2, future2 = dual_group[1]
        
        # 构建合并的prompt
        merged_prompt = self._create_merged_prompt(req1, req2)
        
        try:
            start_time = time.time()
            
            # 执行合并的LLM调用
            merged_result = await self._execute_single_llm_call(merged_prompt)
            
            execution_time = time.time() - start_time
            
            # 解析合并结果
            result1, result2 = self._parse_merged_result(merged_result, req1.task_type, req2.task_type)
            
            # 设置结果
            future1.set_result(result1)
            future2.set_result(result2)
            
            # 统计时间节省（估算）
            estimated_saved_time = execution_time * 0.5  # 假设节省50%时间
            self.stats["time_saved_seconds"] += estimated_saved_time
            
            logger.debug(f"Merged execution completed in {execution_time:.2f}s")
            
        except Exception as e:
            logger.error(f"Dual request processing error: {e}")
            # 回退到单独处理
            for request, future in dual_group:
                if not future.done():
                    try:
                        result = await self._execute_single_llm_call(request.prompt)
                        future.set_result(result)
                    except Exception as single_error:
                        future.set_exception(single_error)
    
    def _create_merged_prompt(self, req1: LLMRequest, req2: LLMRequest) -> str:
        """创建合并的prompt"""
        return f"""请处理以下两个任务，并分别返回结果：

任务1 ({req1.task_type}):
{req1.prompt}

任务2 ({req2.task_type}):
{req2.prompt}

请按以下格式返回结果：
```json
{{
  "task1_result": "任务1的结果",
  "task2_result": "任务2的结果"
}}
```"""
    
    def _parse_merged_result(self, merged_result: str, task_type1: str, task_type2: str) -> Tuple[str, str]:
        """解析合并结果"""
        try:
            import json
            import re
            
            # 尝试提取JSON
            json_match = re.search(r'```json\s*\n(.*?)\n```', merged_result, re.DOTALL)
            if json_match:
                json_content = json_match.group(1)
                parsed = json.loads(json_content)
                
                result1 = parsed.get("task1_result", "")
                result2 = parsed.get("task2_result", "")
                
                return str(result1), str(result2)
            
        except Exception as e:
            logger.warning(f"Failed to parse merged result: {e}")
        
        # 回退：分割结果
        parts = merged_result.split("\n\n")
        if len(parts) >= 2:
            return parts[0], parts[1]
        else:
            return merged_result, merged_result
    
    async def _process_single_request(self, item: Tuple[LLMRequest, asyncio.Future]):
        """处理单个请求"""
        request, future = item
        
        try:
            result = await self._execute_single_llm_call(request.prompt)
            future.set_result(result)
        except Exception as e:
            future.set_exception(e)
    
    async def _execute_single_llm_call(self, prompt: str) -> str:
        """执行单个LLM调用（带超时控制）"""
        messages = [{"role": "user", "content": prompt}]
        try:
            # 应用默认超时控制
            result = await asyncio.wait_for(
                self.llm_client._call_api(messages), 
                timeout=self.default_timeout
            )
            return result
        except asyncio.TimeoutError:
            self.stats["timeout_errors"] += 1
            logger.error(f"Single LLM call timeout after {self.default_timeout}s")
            raise TimeoutError(f"LLM API call timed out after {self.default_timeout}s")
    
    def get_stats(self) -> Dict[str, Any]:
        """获取优化统计信息"""
        total_requests = self.stats["total_requests"]
        merged_requests = self.stats["merged_requests"]
        
        merge_rate = (merged_requests / total_requests * 100) if total_requests > 0 else 0
        timeout_rate = (self.stats["timeout_errors"] / total_requests * 100) if total_requests > 0 else 0
        
        return {
            **self.stats,
            "merge_rate_percent": round(merge_rate, 2),
            "timeout_rate_percent": round(timeout_rate, 2),
            "average_batch_size": round(merged_requests / max(1, self.stats["batch_calls"]), 2),
            "current_active_requests": self._active_requests,
            "max_concurrent_limit": self.max_concurrent_requests
        }
    
    async def flush_pending(self):
        """刷新所有待处理的请求"""
        async with self._batch_lock:
            if self._pending_requests:
                await self._process_batch()
    
    async def wait_for_completion(self, timeout: float = 60.0):
        """等待所有活动请求完成"""
        start_time = time.time()
        while self._active_requests > 0:
            if time.time() - start_time > timeout:
                logger.warning(f"Timeout waiting for {self._active_requests} active requests to complete")
                break
            await asyncio.sleep(0.1)
        
        # 刷新待处理请求
        await self.flush_pending()
    
    def get_health_status(self) -> Dict[str, Any]:
        """获取系统健康状态"""
        total_requests = self.stats["total_requests"]
        timeout_rate = (self.stats["timeout_errors"] / total_requests * 100) if total_requests > 0 else 0
        
        # 健康评分（0-100）
        health_score = 100
        if timeout_rate > 10:  # 超时率超过10%
            health_score -= 30
        elif timeout_rate > 5:  # 超时率超过5%
            health_score -= 15
        
        if self.stats["concurrent_limit_hits"] > total_requests * 0.1:  # 并发限制命中超过10%
            health_score -= 20
        
        status = "healthy"
        if health_score < 50:
            status = "unhealthy"
        elif health_score < 80:
            status = "degraded"
        
        return {
            "status": status,
            "health_score": health_score,
            "active_requests": self._active_requests,
            "pending_requests": len(self._pending_requests),
            "timeout_rate_percent": round(timeout_rate, 2),
            "last_check": datetime.now().isoformat()
        }

# 优化的搜索执行方法
class OptimizedSearchMixin:
    """优化的搜索混入类"""
    
    def __init__(self):
        # 在使用该mixin的类中需要有llm_client属性
        self.request_optimizer = None
    
    def _init_request_optimizer(self):
        """初始化请求优化器"""
        if hasattr(self, 'llm_client') and self.request_optimizer is None:
            # 从配置中获取并发和超时参数
            max_concurrent = getattr(self, 'config', {}).get('max_concurrent_requests', 5)
            default_timeout = getattr(self, 'config', {}).get('default_timeout', 30.0)
            batch_size = getattr(self, 'config', {}).get('batch_size', 3)
            
            self.request_optimizer = RequestOptimizer(
                self.llm_client, 
                batch_size=batch_size,
                max_concurrent_requests=max_concurrent,
                default_timeout=default_timeout
            )
    
    async def _optimized_llm_call(self, prompt: str, task_type: str = "general", priority: int = 1) -> str:
        """优化的LLM调用"""
        if self.request_optimizer is None:
            self._init_request_optimizer()
        
        if self.request_optimizer:
            request = LLMRequest(
                task_type=task_type,
                prompt=prompt,
                priority=priority
            )
            return await self.request_optimizer.execute_request(request)
        else:
            # 回退到直接调用
            messages = [{"role": "user", "content": prompt}]
            return await self.llm_client._call_api(messages)
    
    def get_optimization_stats(self) -> Dict[str, Any]:
        """获取优化统计信息"""
        if self.request_optimizer:
            return self.request_optimizer.get_stats()
        return {"optimization_enabled": False}
    
    def get_health_status(self) -> Dict[str, Any]:
        """获取系统健康状态"""
        if self.request_optimizer:
            return self.request_optimizer.get_health_status()
        return {"status": "unknown", "optimization_enabled": False}
    
    async def wait_for_completion(self, timeout: float = 60.0):
        """等待所有活动请求完成"""
        if self.request_optimizer:
            await self.request_optimizer.wait_for_completion(timeout)