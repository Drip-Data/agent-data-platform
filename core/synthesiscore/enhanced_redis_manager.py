#!/usr/bin/env python3
"""
Enhanced Redis Manager - 增强的Redis队列管理器
支持SynthesisCore v2.0的多种队列和数据流
"""

import asyncio
import json
import logging
import time
from typing import Dict, List, Optional, Any, Union
from datetime import datetime, timedelta

import redis.asyncio as redis
import redis.exceptions
import inspect

from .enhanced_interfaces import (
    CorpusContent, AtomicTask, ExtendedTask, CompositeTask, 
    VerificationResult, GenerationMetrics, PromptTemplate, 
    FewShotExample, TaskUnion, EnhancedSynthesisConfig
)

logger = logging.getLogger(__name__)


async def safe_redis_call(redis_method, *args, **kwargs):
    """安全地调用Redis方法，自动处理同步/异步差异"""
    try:
        # 检查方法是否是协程
        if inspect.iscoroutinefunction(redis_method):
            return await redis_method(*args, **kwargs)
        else:
            # 同步方法直接调用
            return redis_method(*args, **kwargs)
    except TypeError as e:
        if "can't be used in 'await' expression" in str(e):
            # 如果是await错误，尝试同步调用
            return redis_method(*args, **kwargs)
        else:
            raise


class EnhancedRedisManager:
    """增强的Redis管理器"""
    
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis_url = redis_url
        self.redis_client: Optional[redis.Redis] = None
        self.config = EnhancedSynthesisConfig()
        self.streams = self.config.REDIS_CONFIG['streams']
        self.keys = self.config.REDIS_CONFIG['keys']
    
    async def initialize(self):
        """初始化Redis连接"""
        try:
            # 确保使用异步Redis客户端
            self.redis_client = redis.Redis.from_url(self.redis_url)
            
            # 测试连接
            ping_result = await safe_redis_call(self.redis_client.ping)
            if ping_result:
                logger.info("✅ Redis连接初始化成功")
            else:
                raise Exception("Redis ping failed")
            
            # 初始化流和键
            await self._initialize_streams_and_keys()
            
        except Exception as e:
            logger.error(f"❌ Redis连接初始化失败: {e}")
            raise
    
    async def close(self):
        """关闭Redis连接"""
        if self.redis_client:
            await self.redis_client.close()
            logger.info("✅ Redis连接已关闭")
    
    async def _initialize_streams_and_keys(self):
        """初始化流和键"""
        try:
            # 为每个流创建消费者组（如果不存在）
            for stream_name in self.streams.values():
                try:
                    await safe_redis_call(
                        self.redis_client.xgroup_create,
                        stream_name, 
                        "synthesis_workers", 
                        id="0", 
                        mkstream=True
                    )
                    logger.debug(f"✅ 创建消费者组: {stream_name}")
                except redis.exceptions.ResponseError as e:
                    if "BUSYGROUP" in str(e):
                        logger.debug(f"⚠️ 消费者组已存在: {stream_name}")
                    else:
                        raise
            
            # 初始化配置键
            await self._initialize_config_keys()
            
        except Exception as e:
            logger.error(f"❌ 初始化流和键失败: {e}")
            raise
    
    async def _initialize_config_keys(self):
        """初始化配置键"""
        # 初始化配置
        config_data = {
            "version": "2.0",
            "initialized_at": datetime.now().isoformat(),
            "features": {
                "atomic_generation": True,
                "depth_extension": True, 
                "width_extension": True,
                "adaptive_prompts": True,
                "quality_verification": True
            }
        }
        
        await safe_redis_call(
            self.redis_client.hset,
            self.keys['config'],
            mapping={k: json.dumps(v) if not isinstance(v, str) else v for k, v in config_data.items()}
        )
        
        logger.info("✅ Redis配置键初始化完成")


class CorpusQueueManager:
    """语料队列管理器"""
    
    def __init__(self, redis_manager: EnhancedRedisManager):
        self.redis_manager = redis_manager
        self.redis_client = redis_manager.redis_client
        self.stream_name = redis_manager.streams['corpus_queue']
        self.config = EnhancedSynthesisConfig()
    
    async def add_corpus(self, corpus_content: CorpusContent) -> str:
        """添加语料到队列"""
        try:
            corpus_data = {
                "corpus_id": corpus_content.corpus_id,
                "source": corpus_content.source,
                "content_type": corpus_content.content_type.value,
                "text_content": corpus_content.text_content,
                "metadata": json.dumps(corpus_content.metadata),
                "extracted_at": corpus_content.extracted_at,
                "processing_status": corpus_content.processing_status
            }
            
            message_id = await self.redis_client.xadd(self.stream_name, corpus_data)
            logger.debug(f"✅ 语料已添加到队列: {corpus_content.corpus_id}")
            return message_id.decode() if isinstance(message_id, bytes) else message_id
            
        except Exception as e:
            logger.error(f"❌ 添加语料到队列失败: {e}")
            raise
    
    async def batch_add_corpus(self, corpus_list: List[CorpusContent]) -> List[str]:
        """批量添加语料到队列"""
        message_ids = []
        
        # 检查Redis客户端是否有效
        if not self.redis_client:
            logger.error("❌ Redis客户端未初始化")
            raise Exception("Redis client not initialized")
        
        # 使用pipeline提高性能
        try:
            pipeline = self.redis_client.pipeline()
        except Exception as e:
            logger.warning(f"⚠️ Pipeline创建失败，回退到单个操作: {e}")
            # 回退到单个添加
            for corpus in corpus_list:
                try:
                    msg_id = await self.add_corpus(corpus)
                    message_ids.append(msg_id)
                except Exception as corpus_e:
                    logger.error(f"❌ 添加单个语料失败: {corpus_e}")
            return message_ids
        
        for corpus in corpus_list:
            corpus_data = {
                "corpus_id": corpus.corpus_id,
                "source": corpus.source,
                "content_type": corpus.content_type.value,
                "text_content": corpus.text_content,
                "metadata": json.dumps(corpus.metadata),
                "extracted_at": corpus.extracted_at,
                "processing_status": corpus.processing_status
            }
            pipeline.xadd(self.stream_name, corpus_data)
        
        try:
            results = await pipeline.execute()
            message_ids = [result.decode() if isinstance(result, bytes) else result for result in results]
            logger.info(f"✅ 批量添加语料完成: {len(corpus_list)} 个语料")
            return message_ids
            
        except Exception as e:
            logger.error(f"❌ 批量添加语料失败: {e}")
            raise
    
    async def consume_corpus(self, consumer_name: str, count: int = 1, block: int = 1000) -> List[Dict]:
        """消费语料"""
        try:
            messages = await self.redis_client.xreadgroup(
                "synthesis_workers",
                consumer_name,
                {self.stream_name: ">"},
                count=count,
                block=block
            )
            
            consumed_corpus = []
            for stream_name, stream_messages in messages:
                for message_id, fields in stream_messages:
                    try:
                        # 解码字段
                        decoded_fields = {k.decode(): v.decode() for k, v in fields.items()}
                        
                        # 重构CorpusContent对象
                        corpus_content = CorpusContent(
                            corpus_id=decoded_fields['corpus_id'],
                            source=decoded_fields['source'],
                            content_type=decoded_fields['content_type'],
                            text_content=decoded_fields['text_content'],
                            metadata=json.loads(decoded_fields['metadata']),
                            extracted_at=decoded_fields['extracted_at'],
                            processing_status=decoded_fields['processing_status']
                        )
                        
                        consumed_corpus.append({
                            "message_id": message_id.decode(),
                            "corpus_content": corpus_content
                        })
                        
                    except Exception as e:
                        logger.error(f"❌ 解析语料消息失败 {message_id}: {e}")
                        continue
            
            if consumed_corpus:
                logger.debug(f"✅ 消费语料: {len(consumed_corpus)} 个")
            
            return consumed_corpus
            
        except Exception as e:
            logger.error(f"❌ 消费语料失败: {e}")
            return []
    
    async def acknowledge_corpus(self, message_id: str) -> bool:
        """确认语料处理完成"""
        try:
            await self.redis_client.xack("synthesis_workers", self.stream_name, message_id)
            logger.debug(f"✅ 语料处理确认: {message_id}")
            return True
        except Exception as e:
            logger.error(f"❌ 语料处理确认失败 {message_id}: {e}")
            return False


class TaskQueueManager:
    """任务队列管理器"""
    
    def __init__(self, redis_manager: EnhancedRedisManager):
        self.redis_manager = redis_manager
        self.redis_client = redis_manager.redis_client
        self.config = EnhancedSynthesisConfig()
    
    async def add_atomic_task(self, task: AtomicTask) -> str:
        """添加原子任务"""
        return await self._add_task_to_stream(
            self.redis_manager.streams['atomic_tasks'],
            task,
            "atomic"
        )
    
    async def add_extended_task(self, task: ExtendedTask) -> str:
        """添加扩展任务"""
        return await self._add_task_to_stream(
            self.redis_manager.streams['extended_tasks'],
            task,
            "extended"
        )
    
    async def batch_add_tasks(self, tasks: List[TaskUnion]) -> List[str]:
        """批量添加任务"""
        message_ids = []
        
        # 按任务类型分组
        atomic_tasks = [t for t in tasks if isinstance(t, AtomicTask)]
        extended_tasks = [t for t in tasks if isinstance(t, (ExtendedTask, CompositeTask))]
        
        # 批量添加原子任务
        if atomic_tasks:
            atomic_ids = await self._batch_add_to_stream(
                self.redis_manager.streams['atomic_tasks'],
                atomic_tasks,
                "atomic"
            )
            message_ids.extend(atomic_ids)
        
        # 批量添加扩展任务
        if extended_tasks:
            extended_ids = await self._batch_add_to_stream(
                self.redis_manager.streams['extended_tasks'],
                extended_tasks,
                "extended"
            )
            message_ids.extend(extended_ids)
        
        logger.info(f"✅ 批量添加任务完成: {len(tasks)} 个任务")
        return message_ids
    
    async def _add_task_to_stream(self, stream_name: str, task: TaskUnion, task_category: str) -> str:
        """添加任务到指定流"""
        try:
            task_data = self._serialize_task(task, task_category)
            message_id = await self.redis_client.xadd(stream_name, task_data)
            logger.debug(f"✅ 任务已添加到 {stream_name}: {task.task_id}")
            return message_id.decode() if isinstance(message_id, bytes) else message_id
            
        except Exception as e:
            logger.error(f"❌ 添加任务到流失败 {task.task_id}: {e}")
            raise
    
    async def _batch_add_to_stream(self, stream_name: str, tasks: List[TaskUnion], task_category: str) -> List[str]:
        """批量添加任务到流"""
        pipeline = self.redis_client.pipeline()
        
        for task in tasks:
            task_data = self._serialize_task(task, task_category)
            pipeline.xadd(stream_name, task_data)
        
        try:
            results = await pipeline.execute()
            message_ids = [result.decode() if isinstance(result, bytes) else result for result in results]
            logger.info(f"✅ 批量添加到 {stream_name}: {len(tasks)} 个任务")
            return message_ids
            
        except Exception as e:
            logger.error(f"❌ 批量添加任务失败: {e}")
            raise
    
    def _serialize_task(self, task: TaskUnion, task_category: str) -> Dict[str, str]:
        """序列化任务数据"""
        base_data = {
            "task_id": task.task_id,
            "task_category": task_category,
            "task_type": task.task_type.value,
            "question": task.question,
            "difficulty_level": task.difficulty_level.value,
            "created_at": task.created_at
        }
        
        if isinstance(task, AtomicTask):
            base_data.update({
                "golden_answer": task.golden_answer,
                "content_identifier": task.content_identifier,
                "source_corpus": task.source_corpus,
                "verification_score": str(task.verification_score),
                "required_tools": json.dumps(task.required_tools),
                "atomicity_verified": str(task.atomicity_verified),
                "executability_verified": str(task.executability_verified)
            })
        
        elif isinstance(task, ExtendedTask):
            base_data.update({
                "golden_answer": task.golden_answer,
                "hop_level": str(task.hop_level),
                "source_atomic_task": task.source_atomic_task,
                "intermediate_steps": json.dumps([{
                    "identifier": step.identifier,
                    "relation": step.relation,
                    "search_query": step.search_query,
                    "confidence": step.confidence,
                    "source_urls": step.source_urls,
                    "validation_passed": step.validation_passed
                } for step in task.intermediate_steps]),
                "expected_tools": json.dumps(task.expected_tools),
                "complexity_score": str(task.complexity_score)
            })
        
        elif isinstance(task, CompositeTask):
            base_data.update({
                "golden_answers": json.dumps(task.golden_answers),
                "source_atomic_tasks": json.dumps(task.source_atomic_tasks),
                "original_questions": json.dumps(task.original_questions),
                "content_identifier": task.content_identifier,
                "expected_tools": json.dumps(task.expected_tools),
                "merge_strategy": task.merge_strategy
            })
        
        return base_data


class VerificationQueueManager:
    """验证队列管理器"""
    
    def __init__(self, redis_manager: EnhancedRedisManager):
        self.redis_manager = redis_manager
        self.redis_client = redis_manager.redis_client
        self.stream_name = redis_manager.streams['verification_queue']
        self.config = EnhancedSynthesisConfig()
    
    async def add_verification_request(self, task: TaskUnion, priority: str = "normal") -> str:
        """添加验证请求"""
        try:
            verification_data = {
                "task_id": task.task_id,
                "task_type": type(task).__name__,
                "task_data": json.dumps(self._task_to_dict(task)),
                "priority": priority,
                "requested_at": datetime.now().isoformat()
            }
            
            message_id = await self.redis_client.xadd(self.stream_name, verification_data)
            logger.debug(f"✅ 验证请求已添加: {task.task_id}")
            return message_id.decode() if isinstance(message_id, bytes) else message_id
            
        except Exception as e:
            logger.error(f"❌ 添加验证请求失败 {task.task_id}: {e}")
            raise
    
    async def add_verification_result(self, result: VerificationResult) -> str:
        """添加验证结果"""
        try:
            result_data = {
                "task_id": result.task_id,
                "overall_score": str(result.overall_score),
                "recommendation": result.recommendation,
                "verification_dimensions": json.dumps(result.verification_dimensions),
                "suggested_improvements": json.dumps(result.suggested_improvements),
                "details": json.dumps(result.details),
                "verified_at": result.verified_at
            }
            
            # 存储到verification结果流
            result_stream = f"{self.stream_name}:results"
            message_id = await self.redis_client.xadd(result_stream, result_data)
            
            # 同时存储到哈希表以便快速查询
            result_key = f"verification_result:{result.task_id}"
            await self.redis_client.hset(result_key, mapping=result_data)
            await self.redis_client.expire(result_key, 7 * 24 * 3600)  # 7天过期
            
            logger.debug(f"✅ 验证结果已存储: {result.task_id}")
            return message_id.decode() if isinstance(message_id, bytes) else message_id
            
        except Exception as e:
            logger.error(f"❌ 存储验证结果失败 {result.task_id}: {e}")
            raise
    
    def _task_to_dict(self, task: TaskUnion) -> Dict[str, Any]:
        """将任务转换为字典"""
        # 这里简化处理，实际可以使用dataclass的asdict方法
        task_dict = {
            "task_id": task.task_id,
            "question": task.question,
            "task_type": task.task_type.value,
            "difficulty_level": task.difficulty_level.value,
            "created_at": task.created_at
        }
        
        if hasattr(task, 'golden_answer'):
            task_dict['golden_answer'] = task.golden_answer
        if hasattr(task, 'golden_answers'):
            task_dict['golden_answers'] = task.golden_answers
        if hasattr(task, 'required_tools'):
            task_dict['required_tools'] = task.required_tools
        if hasattr(task, 'expected_tools'):
            task_dict['expected_tools'] = task.expected_tools
        
        return task_dict


class MetricsManager:
    """指标管理器"""
    
    def __init__(self, redis_manager: EnhancedRedisManager):
        self.redis_manager = redis_manager
        self.redis_client = redis_manager.redis_client
        self.metrics_key = redis_manager.keys['generation_metrics']
        self.config = EnhancedSynthesisConfig()
    
    async def update_generation_metrics(self, session_id: str, metrics: GenerationMetrics):
        """更新生成指标"""
        try:
            metrics_data = {
                "session_id": metrics.session_id,
                "total_trajectories_processed": str(metrics.total_trajectories_processed),
                "atomic_tasks_generated": str(metrics.atomic_tasks_generated),
                "depth_extended_tasks": str(metrics.depth_extended_tasks),
                "width_extended_tasks": str(metrics.width_extended_tasks),
                "verification_passed": str(metrics.verification_passed),
                "verification_failed": str(metrics.verification_failed),
                "average_quality_score": str(metrics.average_quality_score),
                "processing_time_seconds": str(metrics.processing_time_seconds),
                "start_time": metrics.start_time,
                "end_time": metrics.end_time or "",
                "updated_at": datetime.now().isoformat()
            }
            
            # 存储到哈希表
            session_key = f"{self.metrics_key}:{session_id}"
            await self.redis_client.hset(session_key, mapping=metrics_data)
            await self.redis_client.expire(session_key, 30 * 24 * 3600)  # 30天过期
            
            # 更新全局统计
            await self._update_global_stats(metrics)
            
            logger.debug(f"✅ 生成指标已更新: {session_id}")
            
        except Exception as e:
            logger.error(f"❌ 更新生成指标失败 {session_id}: {e}")
            raise
    
    async def _update_global_stats(self, metrics: GenerationMetrics):
        """更新全局统计数据"""
        try:
            global_key = f"{self.metrics_key}:global"
            
            # 使用pipeline进行原子操作
            pipeline = self.redis_client.pipeline()
            
            # 累加各项指标
            pipeline.hincrby(global_key, "total_trajectories_processed", metrics.total_trajectories_processed)
            pipeline.hincrby(global_key, "total_atomic_tasks", metrics.atomic_tasks_generated)
            pipeline.hincrby(global_key, "total_depth_extended_tasks", metrics.depth_extended_tasks)
            pipeline.hincrby(global_key, "total_width_extended_tasks", metrics.width_extended_tasks)
            pipeline.hincrby(global_key, "total_verification_passed", metrics.verification_passed)
            pipeline.hincrby(global_key, "total_verification_failed", metrics.verification_failed)
            
            # 更新最后更新时间
            pipeline.hset(global_key, "last_updated", datetime.now().isoformat())
            
            await pipeline.execute()
            
        except Exception as e:
            logger.error(f"❌ 更新全局统计失败: {e}")
    
    async def get_global_metrics(self) -> Dict[str, Any]:
        """获取全局指标"""
        try:
            global_key = f"{self.metrics_key}:global"
            raw_data = await self.redis_client.hgetall(global_key)
            
            if not raw_data:
                return {}
            
            # 解码数据
            decoded_data = {k.decode(): v.decode() for k, v in raw_data.items()}
            
            # 转换数值类型
            metrics = {}
            for key, value in decoded_data.items():
                if key in ["last_updated"]:
                    metrics[key] = value
                else:
                    try:
                        metrics[key] = int(value)
                    except ValueError:
                        metrics[key] = value
            
            # 计算衍生指标
            total_tasks = (
                metrics.get("total_atomic_tasks", 0) + 
                metrics.get("total_depth_extended_tasks", 0) + 
                metrics.get("total_width_extended_tasks", 0)
            )
            
            total_trajectories = metrics.get("total_trajectories_processed", 0)
            if total_trajectories > 0:
                metrics["generation_efficiency"] = total_tasks / total_trajectories
            else:
                metrics["generation_efficiency"] = 0.0
            
            total_verifications = (
                metrics.get("total_verification_passed", 0) + 
                metrics.get("total_verification_failed", 0)
            )
            if total_verifications > 0:
                metrics["verification_pass_rate"] = metrics.get("total_verification_passed", 0) / total_verifications
            else:
                metrics["verification_pass_rate"] = 0.0
            
            return metrics
            
        except Exception as e:
            logger.error(f"❌ 获取全局指标失败: {e}")
            return {}


class PromptVersionManager:
    """提示词版本管理器"""
    
    def __init__(self, redis_manager: EnhancedRedisManager):
        self.redis_manager = redis_manager
        self.redis_client = redis_manager.redis_client
        self.prompt_key = redis_manager.keys['prompt_versions']
        self.few_shot_key = redis_manager.keys['few_shot_examples']
        self.config = EnhancedSynthesisConfig()
    
    async def save_prompt_template(self, template: PromptTemplate):
        """保存提示词模板"""
        try:
            template_data = {
                "template_id": template.template_id,
                "template_name": template.template_name,
                "template_content": template.template_content,
                "template_type": template.template_type,
                "version": template.version,
                "success_rate": str(template.success_rate),
                "usage_count": str(template.usage_count),
                "created_at": template.created_at,
                "last_updated": template.last_updated
            }
            
            template_key = f"{self.prompt_key}:{template.template_type}:{template.template_id}"
            await self.redis_client.hset(template_key, mapping=template_data)
            
            # 维护版本索引
            version_index_key = f"{self.prompt_key}:index:{template.template_type}"
            await self.redis_client.zadd(
                version_index_key, 
                {template.template_id: template.success_rate}
            )
            
            logger.debug(f"✅ 提示词模板已保存: {template.template_id}")
            
        except Exception as e:
            logger.error(f"❌ 保存提示词模板失败 {template.template_id}: {e}")
            raise
    
    async def get_best_prompt_template(self, template_type: str) -> Optional[PromptTemplate]:
        """获取最佳提示词模板"""
        try:
            version_index_key = f"{self.prompt_key}:index:{template_type}"
            
            # 获取成功率最高的模板ID
            best_templates = await self.redis_client.zrevrange(version_index_key, 0, 0, withscores=True)
            
            if not best_templates:
                return None
            
            best_template_id = best_templates[0][0].decode()
            
            # 获取模板数据
            template_key = f"{self.prompt_key}:{template_type}:{best_template_id}"
            template_data = await self.redis_client.hgetall(template_key)
            
            if not template_data:
                return None
            
            # 重构PromptTemplate对象
            decoded_data = {k.decode(): v.decode() for k, v in template_data.items()}
            
            return PromptTemplate(
                template_id=decoded_data['template_id'],
                template_name=decoded_data['template_name'],
                template_content=decoded_data['template_content'],
                template_type=decoded_data['template_type'],
                version=decoded_data['version'],
                success_rate=float(decoded_data['success_rate']),
                usage_count=int(decoded_data['usage_count']),
                created_at=decoded_data['created_at'],
                last_updated=decoded_data['last_updated']
            )
            
        except Exception as e:
            logger.error(f"❌ 获取最佳提示词模板失败 {template_type}: {e}")
            return None
    
    async def save_few_shot_example(self, example: FewShotExample):
        """保存少样本示例"""
        try:
            example_data = {
                "example_id": example.example_id,
                "task_type": example.task_type,
                "input_data": json.dumps(example.input_data),
                "expected_output": json.dumps(example.expected_output),
                "quality_score": str(example.quality_score),
                "usage_count": str(example.usage_count),
                "created_at": example.created_at
            }
            
            example_key = f"{self.few_shot_key}:{example.task_type}:{example.example_id}"
            await self.redis_client.hset(example_key, mapping=example_data)
            
            # 维护质量排序索引
            quality_index_key = f"{self.few_shot_key}:quality:{example.task_type}"
            await self.redis_client.zadd(
                quality_index_key,
                {example.example_id: example.quality_score}
            )
            
            logger.debug(f"✅ 少样本示例已保存: {example.example_id}")
            
        except Exception as e:
            logger.error(f"❌ 保存少样本示例失败 {example.example_id}: {e}")
            raise
    
    async def get_top_few_shot_examples(self, task_type: str, count: int = 5) -> List[FewShotExample]:
        """获取顶级少样本示例"""
        try:
            quality_index_key = f"{self.few_shot_key}:quality:{task_type}"
            
            # 获取质量分数最高的示例ID
            top_example_ids = await self.redis_client.zrevrange(quality_index_key, 0, count - 1)
            
            examples = []
            for example_id in top_example_ids:
                example_key = f"{self.few_shot_key}:{task_type}:{example_id.decode()}"
                example_data = await self.redis_client.hgetall(example_key)
                
                if example_data:
                    decoded_data = {k.decode(): v.decode() for k, v in example_data.items()}
                    
                    example = FewShotExample(
                        example_id=decoded_data['example_id'],
                        task_type=decoded_data['task_type'],
                        input_data=json.loads(decoded_data['input_data']),
                        expected_output=json.loads(decoded_data['expected_output']),
                        quality_score=float(decoded_data['quality_score']),
                        usage_count=int(decoded_data['usage_count']),
                        created_at=decoded_data['created_at']
                    )
                    examples.append(example)
            
            logger.debug(f"✅ 获取顶级少样本示例: {task_type} ({len(examples)} 个)")
            return examples
            
        except Exception as e:
            logger.error(f"❌ 获取顶级少样本示例失败 {task_type}: {e}")
            return []


# 统一管理器类
class EnhancedSynthesisRedisManager:
    """增强合成Redis统一管理器"""
    
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis_manager = EnhancedRedisManager(redis_url)
        self.corpus_queue = CorpusQueueManager(self.redis_manager)
        self.task_queue = TaskQueueManager(self.redis_manager)
        self.verification_queue = VerificationQueueManager(self.redis_manager)
        self.metrics_manager = MetricsManager(self.redis_manager)
        self.prompt_manager = PromptVersionManager(self.redis_manager)
    
    async def initialize(self):
        """初始化所有管理器"""
        await self.redis_manager.initialize()
        
        # 更新所有子管理器的Redis客户端引用
        self.corpus_queue.redis_client = self.redis_manager.redis_client
        self.task_queue.redis_client = self.redis_manager.redis_client
        self.verification_queue.redis_client = self.redis_manager.redis_client
        self.metrics_manager.redis_client = self.redis_manager.redis_client
        self.prompt_manager.redis_client = self.redis_manager.redis_client
        
        logger.info("✅ 增强合成Redis管理器初始化完成")
    
    async def close(self):
        """关闭所有连接"""
        await self.redis_manager.close()
        logger.info("✅ 增强合成Redis管理器已关闭")
    
    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        try:
            # 检查Redis连接
            ping_result = await safe_redis_call(self.redis_manager.redis_client.ping)
            if not ping_result:
                raise Exception("Redis connection failed")
            
            # 获取队列长度
            corpus_length = await safe_redis_call(
                self.redis_manager.redis_client.xlen,
                self.redis_manager.streams['corpus_queue']
            )
            atomic_length = await safe_redis_call(
                self.redis_manager.redis_client.xlen,
                self.redis_manager.streams['atomic_tasks']
            )
            verification_length = await safe_redis_call(
                self.redis_manager.redis_client.xlen,
                self.redis_manager.streams['verification_queue']
            )
            
            # 获取全局指标
            global_metrics = await self.metrics_manager.get_global_metrics()
            
            return {
                "status": "healthy",
                "redis_connected": True,
                "queue_lengths": {
                    "corpus_queue": corpus_length,
                    "atomic_tasks": atomic_length,
                    "verification_queue": verification_length
                },
                "global_metrics": global_metrics,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }