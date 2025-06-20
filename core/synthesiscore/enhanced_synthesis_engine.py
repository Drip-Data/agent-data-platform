#!/usr/bin/env python3
"""
Enhanced Synthesis Engine - 增强合成引擎
基于TaskCraft算法的完整任务生成和验证系统
"""

import asyncio
import json
import logging
import time
from typing import Dict, List, Optional, Any, Union
from dataclasses import asdict
from datetime import datetime

from core.interfaces import TrajectoryResult
from core.llm_client import LLMClient
from core.toolscore.mcp_client import MCPToolClient

from .enhanced_interfaces import (
    CorpusContent, AtomicTask, ExtendedTask, CompositeTask, 
    VerificationResult, GenerationMetrics, TaskUnion,
    EnhancedSynthesisConfig
)
from .corpus_ingestor import CorpusIngestor
from .atomic_task_generator import AtomicTaskGenerator
from .depth_extender import DepthExtender
from .width_extender import WidthExtender
from .verification_agent import EnhancedVerificationEngine
from .enhanced_redis_manager import EnhancedSynthesisRedisManager

logger = logging.getLogger(__name__)


class EnhancedSynthesisEngine:
    """增强合成引擎 - SynthesisCore v2.0的核心引擎"""
    
    def __init__(self, llm_client: LLMClient, mcp_client: Optional[MCPToolClient] = None,
                 redis_url: str = "redis://localhost:6379"):
        self.llm_client = llm_client
        self.mcp_client = mcp_client
        self.config = EnhancedSynthesisConfig()
        
        # 初始化子系统
        self.corpus_ingestor = CorpusIngestor(mcp_client)
        self.atomic_generator = AtomicTaskGenerator(llm_client, mcp_client)
        self.depth_extender = DepthExtender(llm_client, mcp_client)
        self.width_extender = WidthExtender(llm_client, mcp_client)
        self.verification_engine = EnhancedVerificationEngine(llm_client, mcp_client)
        self.redis_manager = EnhancedSynthesisRedisManager(redis_url)
        
        # 会话状态
        self.session_id = f"synthesis_{int(time.time())}"
        self.generation_metrics = GenerationMetrics(session_id=self.session_id)
    
    async def initialize(self):
        """初始化引擎"""
        try:
            await self.redis_manager.initialize()
            logger.info("✅ Enhanced Synthesis Engine 初始化完成")
        except Exception as e:
            logger.error(f"❌ Enhanced Synthesis Engine 初始化失败: {e}")
            raise
    
    async def close(self):
        """关闭引擎"""
        try:
            await self.redis_manager.close()
            logger.info("✅ Enhanced Synthesis Engine 已关闭")
        except Exception as e:
            logger.error(f"❌ Enhanced Synthesis Engine 关闭失败: {e}")
    
    async def synthesize_from_trajectories(self, trajectories: List[TrajectoryResult], 
                                         include_depth_extension: bool = True,
                                         include_width_extension: bool = True,
                                         verify_tasks: bool = True) -> Dict[str, Any]:
        """从轨迹完整合成任务"""
        logger.info(f"🚀 开始从 {len(trajectories)} 个轨迹完整合成任务")
        
        start_time = time.time()
        self.generation_metrics.total_trajectories_processed = len(trajectories)
        
        try:
            # Phase 1: 语料提取
            logger.info("📖 Phase 1: 语料提取")
            corpus_contents = await self.corpus_ingestor.ingest_from_trajectories(trajectories)
            
            if not corpus_contents:
                logger.warning("⚠️ 未提取到有效语料")
                return self._build_empty_result("无有效语料")
            
            # 存储语料到Redis队列
            await self._store_corpus_to_redis(corpus_contents)
            
            # Phase 2: 原子任务生成
            logger.info("⚛️ Phase 2: 原子任务生成")
            atomic_tasks = await self.atomic_generator.generate_atomic_tasks_from_corpus(corpus_contents)
            self.generation_metrics.atomic_tasks_generated = len(atomic_tasks)
            
            if not atomic_tasks:
                logger.warning("⚠️ 未生成原子任务")
                return self._build_empty_result("无原子任务生成")
            
            # 存储原子任务
            await self._store_atomic_tasks_to_redis(atomic_tasks)
            
            # Phase 3: 任务扩展
            extended_tasks = []
            composite_tasks = []
            
            if include_depth_extension:
                logger.info("🔄 Phase 3a: 深度扩展")
                extended_tasks = await self.depth_extender.batch_extend_atomic_tasks(atomic_tasks)
                self.generation_metrics.depth_extended_tasks = len(extended_tasks)
                await self._store_extended_tasks_to_redis(extended_tasks)
            
            if include_width_extension:
                logger.info("🔗 Phase 3b: 宽度扩展")
                composite_tasks = await self.width_extender.extend_atomic_tasks_width(atomic_tasks)
                self.generation_metrics.width_extended_tasks = len(composite_tasks)
                await self._store_extended_tasks_to_redis(composite_tasks)
            
            # Phase 4: 验证
            verification_results = []
            if verify_tasks:
                logger.info("🔍 Phase 4: 任务验证")
                all_tasks = atomic_tasks + extended_tasks + composite_tasks
                verification_results = await self.verification_engine.batch_verification(all_tasks)
                
                # 统计验证结果
                passed = sum(1 for r in verification_results if r.recommendation == "accept")
                failed = sum(1 for r in verification_results if r.recommendation == "reject")
                
                self.generation_metrics.verification_passed = passed
                self.generation_metrics.verification_failed = failed
                
                # 计算平均质量分数
                if verification_results:
                    avg_score = sum(r.overall_score for r in verification_results) / len(verification_results)
                    self.generation_metrics.average_quality_score = avg_score
                
                # 存储验证结果
                await self._store_verification_results_to_redis(verification_results)
            
            # 完成统计
            processing_time = time.time() - start_time
            self.generation_metrics.processing_time_seconds = processing_time
            self.generation_metrics.end_time = datetime.now().isoformat()
            
            # 存储指标
            await self.redis_manager.metrics_manager.update_generation_metrics(
                self.session_id, self.generation_metrics
            )
            
            # 构建结果
            result = {
                "session_id": self.session_id,
                "success": True,
                "corpus_contents": corpus_contents,
                "atomic_tasks": atomic_tasks,
                "extended_tasks": extended_tasks,
                "composite_tasks": composite_tasks,
                "verification_results": verification_results,
                "generation_metrics": asdict(self.generation_metrics),
                "processing_time": processing_time,
                "statistics": await self._generate_comprehensive_statistics(
                    atomic_tasks, extended_tasks, composite_tasks, verification_results
                )
            }
            
            logger.info(f"✅ 任务合成完成 - 原子: {len(atomic_tasks)}, 深度扩展: {len(extended_tasks)}, 宽度扩展: {len(composite_tasks)} (用时: {processing_time:.2f}s)")
            return result
            
        except Exception as e:
            logger.error(f"❌ 任务合成失败: {e}")
            return self._build_error_result(str(e))
    
    async def synthesize_from_external_domains(self, domains: List[str],
                                             include_depth_extension: bool = True,
                                             include_width_extension: bool = True,
                                             verify_tasks: bool = True) -> Dict[str, Any]:
        """从外部领域合成任务"""
        logger.info(f"🔍 开始从外部领域合成任务: {domains}")
        
        start_time = time.time()
        
        try:
            # Phase 1: 外部语料采样
            logger.info("📡 Phase 1: 外部语料采样")
            corpus_contents = await self.corpus_ingestor.ingest_external_corpus(domains)
            
            if not corpus_contents:
                logger.warning("⚠️ 外部语料采样未获得结果")
                return self._build_empty_result("外部语料采样失败")
            
            # 使用语料生成任务（复用轨迹处理流程）
            fake_trajectories = []  # 外部语料不需要轨迹
            self.generation_metrics.total_trajectories_processed = len(corpus_contents)
            
            # 直接从语料生成原子任务
            atomic_tasks = await self.atomic_generator.generate_atomic_tasks_from_corpus(corpus_contents)
            self.generation_metrics.atomic_tasks_generated = len(atomic_tasks)
            
            if not atomic_tasks:
                return self._build_empty_result("无原子任务生成")
            
            # 后续流程与轨迹处理相同
            extended_tasks = []
            composite_tasks = []
            
            if include_depth_extension:
                extended_tasks = await self.depth_extender.batch_extend_atomic_tasks(atomic_tasks)
                self.generation_metrics.depth_extended_tasks = len(extended_tasks)
            
            if include_width_extension:
                composite_tasks = await self.width_extender.extend_atomic_tasks_width(atomic_tasks)
                self.generation_metrics.width_extended_tasks = len(composite_tasks)
            
            verification_results = []
            if verify_tasks:
                all_tasks = atomic_tasks + extended_tasks + composite_tasks
                verification_results = await self.verification_engine.batch_verification(all_tasks)
                
                passed = sum(1 for r in verification_results if r.recommendation == "accept")
                failed = sum(1 for r in verification_results if r.recommendation == "reject")
                
                self.generation_metrics.verification_passed = passed
                self.generation_metrics.verification_failed = failed
            
            processing_time = time.time() - start_time
            self.generation_metrics.processing_time_seconds = processing_time
            self.generation_metrics.end_time = datetime.now().isoformat()
            
            result = {
                "session_id": self.session_id,
                "success": True,
                "domains": domains,
                "corpus_contents": corpus_contents,
                "atomic_tasks": atomic_tasks,
                "extended_tasks": extended_tasks,
                "composite_tasks": composite_tasks,
                "verification_results": verification_results,
                "generation_metrics": asdict(self.generation_metrics),
                "processing_time": processing_time
            }
            
            logger.info(f"✅ 外部领域任务合成完成: {len(atomic_tasks)} 原子任务")
            return result
            
        except Exception as e:
            logger.error(f"❌ 外部领域任务合成失败: {e}")
            return self._build_error_result(str(e))
    
    async def verify_task_quality(self, task: TaskUnion) -> VerificationResult:
        """验证单个任务质量"""
        return await self.verification_engine.comprehensive_task_verification(task)
    
    async def get_session_metrics(self) -> Dict[str, Any]:
        """获取会话指标"""
        return asdict(self.generation_metrics)
    
    async def get_global_metrics(self) -> Dict[str, Any]:
        """获取全局指标"""
        return await self.redis_manager.metrics_manager.get_global_metrics()
    
    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        return await self.redis_manager.health_check()
    
    # 内部辅助方法
    
    async def _store_corpus_to_redis(self, corpus_contents: List[CorpusContent]):
        """存储语料到Redis"""
        try:
            await self.redis_manager.corpus_queue.batch_add_corpus(corpus_contents)
            logger.debug(f"✅ 已存储 {len(corpus_contents)} 个语料到Redis")
        except Exception as e:
            logger.error(f"❌ 存储语料到Redis失败: {e}")
    
    async def _store_atomic_tasks_to_redis(self, atomic_tasks: List[AtomicTask]):
        """存储原子任务到Redis"""
        try:
            await self.redis_manager.task_queue.batch_add_tasks(atomic_tasks)
            logger.debug(f"✅ 已存储 {len(atomic_tasks)} 个原子任务到Redis")
        except Exception as e:
            logger.error(f"❌ 存储原子任务到Redis失败: {e}")
    
    async def _store_extended_tasks_to_redis(self, extended_tasks: List[Union[ExtendedTask, CompositeTask]]):
        """存储扩展任务到Redis"""
        try:
            await self.redis_manager.task_queue.batch_add_tasks(extended_tasks)
            logger.debug(f"✅ 已存储 {len(extended_tasks)} 个扩展任务到Redis")
        except Exception as e:
            logger.error(f"❌ 存储扩展任务到Redis失败: {e}")
    
    async def _store_verification_results_to_redis(self, verification_results: List[VerificationResult]):
        """存储验证结果到Redis"""
        try:
            for result in verification_results:
                await self.redis_manager.verification_queue.add_verification_result(result)
            logger.debug(f"✅ 已存储 {len(verification_results)} 个验证结果到Redis")
        except Exception as e:
            logger.error(f"❌ 存储验证结果到Redis失败: {e}")
    
    async def _generate_comprehensive_statistics(self, atomic_tasks: List[AtomicTask],
                                               extended_tasks: List[ExtendedTask],
                                               composite_tasks: List[CompositeTask],
                                               verification_results: List[VerificationResult]) -> Dict[str, Any]:
        """生成综合统计信息"""
        
        statistics = {
            "task_generation": {
                "atomic_tasks": len(atomic_tasks),
                "depth_extended_tasks": len(extended_tasks),
                "width_extended_tasks": len(composite_tasks),
                "total_tasks": len(atomic_tasks) + len(extended_tasks) + len(composite_tasks)
            },
            "verification": {
                "total_verified": len(verification_results),
                "accepted": sum(1 for r in verification_results if r.recommendation == "accept"),
                "modified": sum(1 for r in verification_results if r.recommendation == "modify"),
                "rejected": sum(1 for r in verification_results if r.recommendation == "reject")
            }
        }
        
        # 添加详细统计
        if atomic_tasks:
            atomic_stats = await self.atomic_generator.get_generation_statistics(atomic_tasks)
            statistics["atomic_task_details"] = atomic_stats
        
        if extended_tasks:
            depth_stats = await self.depth_extender.get_extension_statistics(extended_tasks)
            statistics["depth_extension_details"] = depth_stats
        
        if atomic_tasks and composite_tasks:
            width_stats = await self.width_extender.get_width_extension_statistics(atomic_tasks, composite_tasks)
            statistics["width_extension_details"] = width_stats
        
        # 计算效率指标
        if self.generation_metrics.total_trajectories_processed > 0:
            statistics["efficiency"] = {
                "tasks_per_trajectory": statistics["task_generation"]["total_tasks"] / self.generation_metrics.total_trajectories_processed,
                "verification_pass_rate": self.generation_metrics.verification_pass_rate,
                "generation_efficiency": self.generation_metrics.generation_efficiency
            }
        
        return statistics
    
    def _build_empty_result(self, reason: str) -> Dict[str, Any]:
        """构建空结果"""
        return {
            "session_id": self.session_id,
            "success": False,
            "reason": reason,
            "corpus_contents": [],
            "atomic_tasks": [],
            "extended_tasks": [],
            "composite_tasks": [],
            "verification_results": [],
            "generation_metrics": asdict(self.generation_metrics),
            "processing_time": 0.0
        }
    
    def _build_error_result(self, error: str) -> Dict[str, Any]:
        """构建错误结果"""
        return {
            "session_id": self.session_id,
            "success": False,
            "error": error,
            "corpus_contents": [],
            "atomic_tasks": [],
            "extended_tasks": [],
            "composite_tasks": [],
            "verification_results": [],
            "generation_metrics": asdict(self.generation_metrics),
            "processing_time": 0.0
        }


class SynthesisCoreV2:
    """SynthesisCore v2.0 - 对外统一接口"""
    
    def __init__(self, llm_client: LLMClient, mcp_client: Optional[MCPToolClient] = None,
                 redis_url: str = "redis://localhost:6379"):
        self.engine = EnhancedSynthesisEngine(llm_client, mcp_client, redis_url)
        self.config = EnhancedSynthesisConfig()
        
    async def initialize(self):
        """初始化"""
        await self.engine.initialize()
        logger.info("🚀 SynthesisCore v2.0 已启动")
    
    async def close(self):
        """关闭"""
        await self.engine.close()
        logger.info("🔒 SynthesisCore v2.0 已关闭")
    
    async def synthesize_tasks(self, trajectories: List[TrajectoryResult] = None,
                              domains: List[str] = None,
                              mode: str = "full",
                              verify_quality: bool = True) -> Dict[str, Any]:
        """
        统一的任务合成接口
        
        Args:
            trajectories: 轨迹数据（可选）
            domains: 外部领域（可选）
            mode: 合成模式 (full/atomic_only/depth_only/width_only)
            verify_quality: 是否进行质量验证
        """
        
        include_depth = mode in ["full", "depth_only"]
        include_width = mode in ["full", "width_only"]
        
        if trajectories:
            return await self.engine.synthesize_from_trajectories(
                trajectories, include_depth, include_width, verify_quality
            )
        elif domains:
            return await self.engine.synthesize_from_external_domains(
                domains, include_depth, include_width, verify_quality
            )
        else:
            raise ValueError("必须提供trajectories或domains中的至少一个")
    
    async def verify_task(self, task: TaskUnion) -> VerificationResult:
        """验证单个任务"""
        return await self.engine.verify_task_quality(task)
    
    async def get_metrics(self, scope: str = "session") -> Dict[str, Any]:
        """获取指标"""
        if scope == "session":
            return await self.engine.get_session_metrics()
        elif scope == "global":
            return await self.engine.get_global_metrics()
        else:
            raise ValueError("scope必须是'session'或'global'")
    
    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        return await self.engine.health_check()
    
    def get_config(self) -> EnhancedSynthesisConfig:
        """获取配置"""
        return self.config