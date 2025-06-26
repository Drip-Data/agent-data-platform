#!/usr/bin/env python3
"""
Enhanced Synthesis Controller - 增强合成控制器
集成所有改进功能的统一控制器，提供完整的任务合成和扩展能力
"""

import asyncio
import json
import logging
import time
from typing import Dict, List, Optional, Any, Callable
from dataclasses import asdict
from datetime import datetime

from core.interfaces import TrajectoryResult
from core.llm_client import LLMClient
from core.toolscore.mcp_client import MCPToolClient

# 导入所有增强组件
from .enhanced_interfaces import (
    AtomicTask, ExtendedTask, CompositeTask, TaskVerificationMetrics,
    AdaptiveExtensionConfig, GenerationMetrics, TaskUnion
)
from .enhanced_synthesis_engine import EnhancedSynthesisEngine
from .depth_extender import DepthExtender
from .width_extender import WidthExtender
from .enhanced_verification_agent import EnhancedVerificationAgent, BatchVerificationProcessor
from .real_time_extension_trigger import RealTimeExtensionTrigger, RealTimeExtensionManager

logger = logging.getLogger(__name__)


class EnhancedSynthesisController:
    """增强合成控制器 - 统一管理所有合成和扩展功能"""
    
    def __init__(self, 
                 llm_client: LLMClient,
                 mcp_client: Optional[MCPToolClient] = None,
                 enable_real_time: bool = True):
        
        self.llm_client = llm_client
        self.mcp_client = mcp_client
        self.enable_real_time = enable_real_time
        
        # 初始化核心组件
        self.synthesis_engine = EnhancedSynthesisEngine(llm_client, mcp_client)
        self.depth_extender = DepthExtender(llm_client, mcp_client)
        self.width_extender = WidthExtender(llm_client, mcp_client)
        self.verification_agent = EnhancedVerificationAgent(llm_client)
        self.batch_processor = BatchVerificationProcessor(self.verification_agent)
        
        # 自适应配置
        self.adaptive_config = AdaptiveExtensionConfig()
        
        # 实时扩展组件（可选）
        self.real_time_trigger = None
        self.real_time_manager = None
        if enable_real_time:
            self._initialize_real_time_components()
        
        # 统计指标
        self.session_metrics = GenerationMetrics(session_id=f"enhanced_{int(time.time())}")
        
        # 任务存储（内存中的缓存，实际应该连接到Redis或数据库）
        self.task_pool = {
            "atomic_tasks": [],
            "extended_tasks": [],
            "composite_tasks": []
        }
        
        # 回调函数注册
        self.callbacks = {
            "task_generated": [],
            "quality_report": [],
            "metrics_updated": []
        }
        
        logger.info("🚀 增强合成控制器初始化完成")
    
    def _initialize_real_time_components(self):
        """初始化实时扩展组件"""
        try:
            self.real_time_trigger = RealTimeExtensionTrigger(
                self.llm_client, 
                self.mcp_client, 
                self.synthesis_engine
            )
            self.real_time_manager = RealTimeExtensionManager(self.real_time_trigger)
            
            # 设置回调函数
            self.real_time_trigger.set_task_generated_callback(self._on_real_time_task_generated)
            self.real_time_trigger.set_quality_report_callback(self._on_real_time_quality_report)
            
            logger.info("✅ 实时扩展组件初始化完成")
            
        except Exception as e:
            logger.error(f"❌ 实时扩展组件初始化失败: {e}")
            self.enable_real_time = False
    
    async def start(self):
        """启动控制器"""
        logger.info("🚀 启动增强合成控制器")
        
        if self.enable_real_time and self.real_time_trigger:
            await self.real_time_trigger.start()
            logger.info("✅ 实时扩展服务已启动")
        
        logger.info("✅ 增强合成控制器启动完成")
    
    async def stop(self):
        """停止控制器"""
        logger.info("🛑 停止增强合成控制器")
        
        if self.enable_real_time and self.real_time_trigger:
            await self.real_time_trigger.stop()
            
        if self.real_time_manager:
            self.real_time_manager.stop_monitoring()
        
        logger.info("✅ 增强合成控制器已停止")
    
    # 核心合成功能
    async def process_trajectory(self, trajectory: TrajectoryResult) -> Dict[str, Any]:
        """处理轨迹并生成任务"""
        logger.info(f"📥 处理轨迹: {trajectory.trajectory_id}")
        
        start_time = time.time()
        
        try:
            # 1. 从轨迹中提取种子任务
            seed_tasks = await self.synthesis_engine.extract_atomic_tasks_from_trajectory(trajectory)
            
            if not seed_tasks:
                return {
                    "success": False,
                    "message": "未能从轨迹中提取种子任务",
                    "trajectory_id": trajectory.trajectory_id
                }
            
            self.session_metrics.atomic_tasks_generated += len(seed_tasks)
            logger.info(f"✅ 提取种子任务: {len(seed_tasks)} 个")
            
            # 2. 执行任务扩展
            extension_results = await self._perform_task_extension(seed_tasks)
            
            # 3. 验证和筛选任务
            verification_results = await self._verify_and_filter_tasks(
                seed_tasks + extension_results["extended_tasks"] + extension_results["composite_tasks"]
            )
            
            # 4. 存储高质量任务
            high_quality_tasks = verification_results["high_quality_tasks"]
            await self._store_tasks(high_quality_tasks)
            
            # 5. 更新自适应配置
            await self._update_adaptive_configuration(verification_results["verification_metrics"])
            
            # 6. 触发实时扩展（如果启用）
            if self.enable_real_time and self.real_time_trigger:
                await self.real_time_trigger.on_trajectory_completed(trajectory)
            
            # 7. 更新统计指标
            processing_time = time.time() - start_time
            self.session_metrics.processing_time_seconds += processing_time
            self.session_metrics.total_trajectories_processed += 1
            
            # 8. 生成处理报告
            report = self._generate_processing_report(
                trajectory, seed_tasks, extension_results, verification_results, processing_time
            )
            
            # 9. 触发回调
            self._trigger_callbacks("metrics_updated", self.session_metrics)
            
            logger.info(f"✅ 轨迹处理完成: {trajectory.trajectory_id} (耗时: {processing_time:.2f}秒)")
            return report
            
        except Exception as e:
            logger.error(f"❌ 轨迹处理失败 {trajectory.trajectory_id}: {e}")
            return {
                "success": False,
                "error": str(e),
                "trajectory_id": trajectory.trajectory_id
            }
    
    async def _perform_task_extension(self, seed_tasks: List[AtomicTask]) -> Dict[str, Any]:
        """执行任务扩展"""
        logger.info(f"🔄 开始任务扩展: {len(seed_tasks)} 个种子任务")
        
        # 并行执行深度和宽度扩展
        depth_task = self.depth_extender.batch_extend_atomic_tasks(seed_tasks, self.adaptive_config)
        width_task = self.width_extender.extend_atomic_tasks_width(seed_tasks, self.adaptive_config)
        
        depth_results, width_results = await asyncio.gather(
            depth_task, width_task, return_exceptions=True
        )
        
        # 处理结果
        extended_tasks = depth_results if isinstance(depth_results, list) else []
        composite_tasks = width_results if isinstance(width_results, list) else []
        
        if isinstance(depth_results, Exception):
            logger.error(f"❌ 深度扩展失败: {depth_results}")
        else:
            self.session_metrics.depth_extended_tasks += len(extended_tasks)
        
        if isinstance(width_results, Exception):
            logger.error(f"❌ 宽度扩展失败: {width_results}")
        else:
            self.session_metrics.width_extended_tasks += len(composite_tasks)
        
        logger.info(f"✅ 任务扩展完成: 深度 {len(extended_tasks)}, 宽度 {len(composite_tasks)}")
        
        return {
            "extended_tasks": extended_tasks,
            "composite_tasks": composite_tasks
        }
    
    async def _verify_and_filter_tasks(self, all_tasks: List[TaskUnion]) -> Dict[str, Any]:
        """验证和筛选任务"""
        logger.info(f"🔍 开始验证 {len(all_tasks)} 个任务")
        
        if not all_tasks:
            return {"high_quality_tasks": [], "verification_metrics": []}
        
        # 批量验证
        verification_metrics = await self.batch_processor.batch_verify_tasks(all_tasks)
        
        # 筛选高质量任务
        high_quality_tasks = []
        for task, metrics in zip(all_tasks, verification_metrics):
            if metrics.verification_passed:
                high_quality_tasks.append(task)
                self.session_metrics.verification_passed += 1
            else:
                self.session_metrics.verification_failed += 1
        
        # 计算平均质量分数
        if verification_metrics:
            total_score = sum(m.overall_score for m in verification_metrics)
            self.session_metrics.average_quality_score = total_score / len(verification_metrics)
        
        logger.info(f"✅ 任务验证完成: {len(high_quality_tasks)}/{len(all_tasks)} 通过")
        
        return {
            "high_quality_tasks": high_quality_tasks,
            "verification_metrics": verification_metrics
        }
    
    async def _store_tasks(self, tasks: List[TaskUnion]):
        """存储任务到任务池"""
        for task in tasks:
            if isinstance(task, AtomicTask):
                self.task_pool["atomic_tasks"].append(task)
            elif isinstance(task, ExtendedTask):
                self.task_pool["extended_tasks"].append(task)
            elif isinstance(task, CompositeTask):
                self.task_pool["composite_tasks"].append(task)
        
        logger.info(f"📝 存储任务: {len(tasks)} 个")
        
        # 触发任务生成回调
        self._trigger_callbacks("task_generated", tasks)
    
    async def _update_adaptive_configuration(self, verification_metrics: List[TaskVerificationMetrics]):
        """更新自适应配置"""
        if not verification_metrics:
            return
        
        # 计算成功率和效率指标
        success_count = sum(1 for m in verification_metrics if m.verification_passed)
        success_rate = success_count / len(verification_metrics)
        
        # 记录成功历史
        for metrics in verification_metrics:
            self.adaptive_config.record_success(metrics.verification_passed)
        
        # 计算效率指标
        efficiency_metrics = {
            "verification_success_rate": success_rate,
            "average_quality_score": sum(m.overall_score for m in verification_metrics) / len(verification_metrics),
            "generation_efficiency": self.session_metrics.generation_efficiency
        }
        
        # 调整阈值
        self.adaptive_config.adjust_thresholds(success_rate, efficiency_metrics)
        
        logger.debug(f"🔧 自适应配置更新完成 (成功率: {success_rate:.3f})")
    
    def _generate_processing_report(self, trajectory: TrajectoryResult, 
                                  seed_tasks: List[AtomicTask],
                                  extension_results: Dict[str, Any],
                                  verification_results: Dict[str, Any],
                                  processing_time: float) -> Dict[str, Any]:
        """生成处理报告"""
        return {
            "success": True,
            "trajectory_id": trajectory.trajectory_id,
            "processing_time_seconds": processing_time,
            "task_generation": {
                "seed_tasks": len(seed_tasks),
                "extended_tasks": len(extension_results["extended_tasks"]),
                "composite_tasks": len(extension_results["composite_tasks"]),
                "total_generated": len(seed_tasks) + len(extension_results["extended_tasks"]) + len(extension_results["composite_tasks"])
            },
            "quality_assessment": {
                "total_verified": len(verification_results["verification_metrics"]),
                "high_quality_count": len(verification_results["high_quality_tasks"]),
                "pass_rate": len(verification_results["high_quality_tasks"]) / max(len(verification_results["verification_metrics"]), 1),
                "average_quality_score": sum(m.overall_score for m in verification_results["verification_metrics"]) / max(len(verification_results["verification_metrics"]), 1)
            },
            "adaptive_config_snapshot": {
                "current_success_rate": self.adaptive_config.get_current_success_rate(),
                "depth_threshold": self.adaptive_config.depth_config["superset_confidence_threshold"],
                "width_threshold": self.adaptive_config.width_config["semantic_similarity_threshold"],
                "batch_size": self.adaptive_config.batch_config["batch_size"]
            },
            "session_metrics": asdict(self.session_metrics)
        }
    
    # 批量处理功能
    async def batch_process_trajectories(self, trajectories: List[TrajectoryResult], 
                                       max_concurrent: int = 3) -> List[Dict[str, Any]]:
        """批量处理轨迹"""
        logger.info(f"🔄 开始批量处理 {len(trajectories)} 个轨迹")
        
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def process_with_semaphore(trajectory):
            async with semaphore:
                return await self.process_trajectory(trajectory)
        
        results = await asyncio.gather(
            *[process_with_semaphore(t) for t in trajectories],
            return_exceptions=True
        )
        
        # 处理结果
        successful_results = []
        for result in results:
            if isinstance(result, dict) and result.get("success", False):
                successful_results.append(result)
            elif isinstance(result, Exception):
                logger.error(f"❌ 批量处理异常: {result}")
        
        logger.info(f"✅ 批量处理完成: {len(successful_results)}/{len(trajectories)} 成功")
        return successful_results
    
    # 回调系统
    def register_callback(self, event_type: str, callback: Callable):
        """注册回调函数"""
        if event_type in self.callbacks:
            self.callbacks[event_type].append(callback)
            logger.info(f"✅ 注册回调函数: {event_type}")
        else:
            logger.warning(f"⚠️ 未知的事件类型: {event_type}")
    
    def _trigger_callbacks(self, event_type: str, data: Any):
        """触发回调函数"""
        for callback in self.callbacks.get(event_type, []):
            try:
                callback(data)
            except Exception as e:
                logger.error(f"❌ 回调函数执行失败 ({event_type}): {e}")
    
    # 实时扩展回调处理
    def _on_real_time_task_generated(self, tasks: List[TaskUnion]):
        """实时任务生成回调"""
        logger.info(f"🔥 实时生成任务: {len(tasks)} 个")
        
        # 存储到任务池
        asyncio.create_task(self._store_tasks(tasks))
    
    def _on_real_time_quality_report(self, report: Dict[str, Any]):
        """实时质量报告回调"""
        logger.info(f"📊 实时质量报告: 通过率 {report.get('processing_summary', {}).get('verification_pass_rate', 0):.3f}")
        
        # 触发质量报告回调
        self._trigger_callbacks("quality_report", report)
    
    # 状态查询和监控
    def get_status(self) -> Dict[str, Any]:
        """获取控制器状态"""
        status = {
            "controller_status": "running",
            "session_metrics": asdict(self.session_metrics),
            "adaptive_config": {
                "current_success_rate": self.adaptive_config.get_current_success_rate(),
                "depth_threshold": self.adaptive_config.depth_config["superset_confidence_threshold"],
                "width_threshold": self.adaptive_config.width_config["semantic_similarity_threshold"],
                "batch_size": self.adaptive_config.batch_config["batch_size"]
            },
            "task_pool_size": {
                "atomic_tasks": len(self.task_pool["atomic_tasks"]),
                "extended_tasks": len(self.task_pool["extended_tasks"]),
                "composite_tasks": len(self.task_pool["composite_tasks"]),
                "total": sum(len(pool) for pool in self.task_pool.values())
            },
            "real_time_enabled": self.enable_real_time
        }
        
        # 添加实时扩展状态
        if self.enable_real_time and self.real_time_trigger:
            status["real_time_status"] = self.real_time_trigger.get_status()
        
        return status
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """获取性能摘要"""
        summary = {
            "session_id": self.session_metrics.session_id,
            "total_trajectories_processed": self.session_metrics.total_trajectories_processed,
            "total_tasks_generated": self.session_metrics.total_tasks_generated,
            "generation_efficiency": self.session_metrics.generation_efficiency,
            "verification_pass_rate": self.session_metrics.verification_pass_rate,
            "average_quality_score": self.session_metrics.average_quality_score,
            "session_duration_seconds": time.time() - float(self.session_metrics.start_time.split("T")[1].replace(":", "").replace("-", "").replace("Z", "")[:6])
        }
        
        # 添加实时扩展性能
        if self.enable_real_time and self.real_time_trigger:
            summary["real_time_performance"] = self.real_time_trigger.get_performance_summary()
        
        return summary
    
    def get_task_pool_statistics(self) -> Dict[str, Any]:
        """获取任务池统计"""
        stats = {}
        
        for task_type, tasks in self.task_pool.items():
            if not tasks:
                stats[task_type] = {"count": 0}
                continue
            
            # 计算统计信息
            quality_scores = []
            difficulty_distribution = {"simple": 0, "medium": 0, "complex": 0}
            
            for task in tasks:
                # 提取质量分数（如果有的话）
                if hasattr(task, 'verification_score'):
                    quality_scores.append(task.verification_score)
                
                # 统计难度分布
                if hasattr(task, 'difficulty_level'):
                    difficulty_distribution[task.difficulty_level.value] += 1
            
            stats[task_type] = {
                "count": len(tasks),
                "average_quality": sum(quality_scores) / len(quality_scores) if quality_scores else 0.0,
                "difficulty_distribution": difficulty_distribution
            }
        
        return stats
    
    # 配置管理
    def update_adaptive_config(self, new_config: Dict[str, Any]):
        """更新自适应配置"""
        try:
            if "depth_config" in new_config:
                self.adaptive_config.depth_config.update(new_config["depth_config"])
            
            if "width_config" in new_config:
                self.adaptive_config.width_config.update(new_config["width_config"])
            
            if "batch_config" in new_config:
                self.adaptive_config.batch_config.update(new_config["batch_config"])
            
            logger.info("✅ 自适应配置更新完成")
            
        except Exception as e:
            logger.error(f"❌ 更新自适应配置失败: {e}")
    
    def export_configuration(self) -> Dict[str, Any]:
        """导出当前配置"""
        return {
            "adaptive_config": {
                "depth_config": self.adaptive_config.depth_config.copy(),
                "width_config": self.adaptive_config.width_config.copy(),
                "batch_config": self.adaptive_config.batch_config.copy()
            },
            "session_metrics": asdict(self.session_metrics),
            "controller_settings": {
                "enable_real_time": self.enable_real_time,
                "task_pool_limits": {
                    "max_atomic_tasks": 1000,
                    "max_extended_tasks": 500,
                    "max_composite_tasks": 200
                }
            }
        }