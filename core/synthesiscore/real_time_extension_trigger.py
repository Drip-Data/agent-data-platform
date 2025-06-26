#!/usr/bin/env python3
"""
Real-Time Extension Trigger - 实时扩展触发器
实现轨迹完成后的实时任务扩展，驱动数据飞轮闭环加速
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
from .enhanced_interfaces import (
    AtomicTask, ExtendedTask, CompositeTask, GenerationMetrics,
    AdaptiveExtensionConfig, TaskVerificationMetrics
)
from .enhanced_synthesis_engine import EnhancedSynthesisEngine
from .depth_extender import DepthExtender
from .width_extender import WidthExtender
from .enhanced_verification_agent import EnhancedVerificationAgent, BatchVerificationProcessor

logger = logging.getLogger(__name__)


class ExtensionQueue:
    """扩展任务队列"""
    
    def __init__(self, max_size: int = 1000):
        self.queue = asyncio.Queue(maxsize=max_size)
        self.priority_queue = asyncio.Queue(maxsize=100)  # 高优先级队列
        self.processing = False
        
    async def put_high_priority(self, item: Dict[str, Any]):
        """添加高优先级任务"""
        await self.priority_queue.put(item)
    
    async def put_normal(self, item: Dict[str, Any]):
        """添加普通优先级任务"""
        await self.queue.put(item)
    
    async def get_next(self) -> Dict[str, Any]:
        """获取下一个任务（优先处理高优先级）"""
        try:
            # 先检查高优先级队列
            return self.priority_queue.get_nowait()
        except asyncio.QueueEmpty:
            # 再检查普通队列
            return await self.queue.get()
    
    def qsize(self) -> Dict[str, int]:
        """获取队列大小"""
        return {
            "high_priority": self.priority_queue.qsize(),
            "normal": self.queue.qsize(),
            "total": self.priority_queue.qsize() + self.queue.qsize()
        }


class RealTimeExtensionTrigger:
    """实时扩展触发器"""
    
    def __init__(self, 
                 llm_client: LLMClient,
                 mcp_client: Optional[MCPToolClient] = None,
                 synthesis_engine: Optional[EnhancedSynthesisEngine] = None):
        
        self.llm_client = llm_client
        self.mcp_client = mcp_client
        
        # 核心组件
        self.synthesis_engine = synthesis_engine or EnhancedSynthesisEngine(llm_client, mcp_client)
        self.depth_extender = DepthExtender(llm_client, mcp_client)
        self.width_extender = WidthExtender(llm_client, mcp_client)
        self.verification_agent = EnhancedVerificationAgent(llm_client)
        self.batch_processor = BatchVerificationProcessor(self.verification_agent)
        
        # 扩展队列
        self.extension_queue = ExtensionQueue()
        
        # 自适应配置
        self.adaptive_config = AdaptiveExtensionConfig()
        
        # 统计指标
        self.metrics = GenerationMetrics(session_id=f"realtime_{int(time.time())}")
        
        # 回调函数
        self.task_generated_callback: Optional[Callable[[List[Any]], None]] = None
        self.quality_report_callback: Optional[Callable[[Dict[str, Any]], None]] = None
        
        # 控制开关
        self.is_running = False
        self.processing_task = None
        
        logger.info("🚀 实时扩展触发器初始化完成")
    
    async def start(self):
        """启动实时扩展处理"""
        if self.is_running:
            logger.warning("⚠️ 实时扩展触发器已在运行")
            return
        
        self.is_running = True
        self.processing_task = asyncio.create_task(self._process_extension_queue())
        logger.info("✅ 实时扩展触发器已启动")
    
    async def stop(self):
        """停止实时扩展处理"""
        self.is_running = False
        if self.processing_task:
            self.processing_task.cancel()
            try:
                await self.processing_task
            except asyncio.CancelledError:
                pass
        logger.info("🛑 实时扩展触发器已停止")
    
    async def on_trajectory_completed(self, trajectory: TrajectoryResult):
        """轨迹完成时的回调处理"""
        logger.info(f"📥 接收到轨迹完成事件: {trajectory.trajectory_id}")
        
        if not trajectory.is_successful:
            logger.debug(f"⚠️ 轨迹执行失败，跳过扩展: {trajectory.trajectory_id}")
            return
        
        try:
            # 创建扩展请求
            extension_request = {
                "type": "immediate_extension",
                "trajectory": trajectory,
                "priority": self._determine_priority(trajectory),
                "timestamp": datetime.now().isoformat(),
                "request_id": f"ext_{int(time.time())}_{trajectory.trajectory_id}"
            }
            
            # 根据优先级加入队列
            if extension_request["priority"] == "high":
                await self.extension_queue.put_high_priority(extension_request)
                logger.info(f"🔥 高优先级扩展请求已入队: {trajectory.trajectory_id}")
            else:
                await self.extension_queue.put_normal(extension_request)
                logger.info(f"📝 普通扩展请求已入队: {trajectory.trajectory_id}")
            
            # 更新统计
            self.metrics.total_trajectories_processed += 1
            
        except Exception as e:
            logger.error(f"❌ 处理轨迹完成事件失败 {trajectory.trajectory_id}: {e}")
    
    def _determine_priority(self, trajectory: TrajectoryResult) -> str:
        """确定扩展优先级"""
        # 基于轨迹特征确定优先级
        high_priority_conditions = [
            len(trajectory.steps) >= 5,  # 复杂任务
            trajectory.task_complexity_score > 0.7,  # 高复杂度
            any("error" not in step.result.lower() for step in trajectory.steps),  # 无错误执行
            trajectory.processing_time_seconds < 60  # 快速完成
        ]
        
        if sum(high_priority_conditions) >= 2:
            return "high"
        else:
            return "normal"
    
    async def _process_extension_queue(self):
        """处理扩展队列"""
        logger.info("🔄 开始处理扩展队列")
        
        while self.is_running:
            try:
                # 获取下一个扩展请求
                extension_request = await asyncio.wait_for(
                    self.extension_queue.get_next(), 
                    timeout=5.0
                )
                
                # 处理扩展请求
                await self._handle_extension_request(extension_request)
                
            except asyncio.TimeoutError:
                # 队列为空，继续等待
                continue
            except Exception as e:
                logger.error(f"❌ 处理扩展队列异常: {e}")
                await asyncio.sleep(1)  # 防止异常循环
        
        logger.info("🛑 扩展队列处理已停止")
    
    async def _handle_extension_request(self, request: Dict[str, Any]):
        """处理单个扩展请求"""
        request_id = request.get("request_id", "unknown")
        trajectory = request.get("trajectory")
        
        logger.info(f"🔧 开始处理扩展请求: {request_id}")
        
        try:
            start_time = time.time()
            
            # 1. 从轨迹中提取种子任务
            seed_tasks = await self.synthesis_engine.extract_atomic_tasks_from_trajectory(trajectory)
            
            if not seed_tasks:
                logger.warning(f"⚠️ 未从轨迹中提取到种子任务: {request_id}")
                return
            
            logger.info(f"✅ 提取到 {len(seed_tasks)} 个种子任务")
            self.metrics.atomic_tasks_generated += len(seed_tasks)
            
            # 2. 并行执行深度和宽度扩展
            depth_task = self._perform_depth_extension(seed_tasks)
            width_task = self._perform_width_extension(seed_tasks)
            
            depth_results, width_results = await asyncio.gather(
                depth_task, width_task, return_exceptions=True
            )
            
            # 处理扩展结果
            all_extended_tasks = []
            
            if isinstance(depth_results, list):
                all_extended_tasks.extend(depth_results)
                self.metrics.depth_extended_tasks += len(depth_results)
                logger.info(f"✅ 深度扩展生成 {len(depth_results)} 个任务")
            elif isinstance(depth_results, Exception):
                logger.error(f"❌ 深度扩展失败: {depth_results}")
            
            if isinstance(width_results, list):
                all_extended_tasks.extend(width_results)
                self.metrics.width_extended_tasks += len(width_results)
                logger.info(f"✅ 宽度扩展生成 {len(width_results)} 个任务")
            elif isinstance(width_results, Exception):
                logger.error(f"❌ 宽度扩展失败: {width_results}")
            
            # 3. 批量验证扩展任务
            if all_extended_tasks:
                verification_results = await self._verify_extended_tasks(all_extended_tasks)
                
                # 4. 筛选高质量任务
                high_quality_tasks = self._filter_high_quality_tasks(
                    all_extended_tasks, verification_results
                )
                
                # 5. 添加到任务池并触发回调
                if high_quality_tasks:
                    await self._add_to_task_pool(high_quality_tasks)
                    
                    if self.task_generated_callback:
                        try:
                            self.task_generated_callback(high_quality_tasks)
                        except Exception as e:
                            logger.error(f"❌ 任务生成回调失败: {e}")
                
                # 6. 更新自适应配置
                await self._update_adaptive_config(verification_results)
                
                # 7. 生成质量报告
                quality_report = self._generate_quality_report(verification_results, request)
                if self.quality_report_callback:
                    try:
                        self.quality_report_callback(quality_report)
                    except Exception as e:
                        logger.error(f"❌ 质量报告回调失败: {e}")
            
            processing_time = time.time() - start_time
            self.metrics.processing_time_seconds += processing_time
            
            logger.info(f"✅ 扩展请求处理完成: {request_id} (耗时: {processing_time:.2f}秒)")
            
        except Exception as e:
            logger.error(f"❌ 扩展请求处理失败 {request_id}: {e}")
    
    async def _perform_depth_extension(self, seed_tasks: List[AtomicTask]) -> List[ExtendedTask]:
        """执行深度扩展"""
        try:
            batch_size = self.adaptive_config.batch_config["batch_size"]
            
            # 分批处理以优化性能
            all_results = []
            for i in range(0, len(seed_tasks), batch_size):
                batch = seed_tasks[i:i + batch_size]
                batch_results = await self.depth_extender.batch_extend_atomic_tasks(batch)
                all_results.extend(batch_results)
            
            return all_results
            
        except Exception as e:
            logger.error(f"❌ 深度扩展执行失败: {e}")
            return []
    
    async def _perform_width_extension(self, seed_tasks: List[AtomicTask]) -> List[CompositeTask]:
        """执行宽度扩展"""
        try:
            return await self.width_extender.extend_atomic_tasks_width(seed_tasks)
        except Exception as e:
            logger.error(f"❌ 宽度扩展执行失败: {e}")
            return []
    
    async def _verify_extended_tasks(self, tasks: List[Any]) -> List[TaskVerificationMetrics]:
        """验证扩展任务"""
        try:
            max_concurrent = self.adaptive_config.batch_config["max_concurrent_batches"]
            return await self.batch_processor.batch_verify_tasks(tasks, max_concurrent)
        except Exception as e:
            logger.error(f"❌ 任务验证失败: {e}")
            return []
    
    def _filter_high_quality_tasks(self, tasks: List[Any], 
                                  verification_results: List[TaskVerificationMetrics]) -> List[Any]:
        """筛选高质量任务"""
        high_quality_tasks = []
        
        for task, verification in zip(tasks, verification_results):
            if verification.verification_passed:
                high_quality_tasks.append(task)
                self.metrics.verification_passed += 1
            else:
                self.metrics.verification_failed += 1
        
        logger.info(f"✅ 筛选出 {len(high_quality_tasks)} 个高质量任务")
        return high_quality_tasks
    
    async def _add_to_task_pool(self, tasks: List[Any]):
        """添加任务到任务池"""
        try:
            # 这里应该调用实际的任务池存储逻辑
            # 比如存储到Redis、数据库等
            logger.info(f"📝 {len(tasks)} 个任务已添加到任务池")
            
            # 示例：存储到Redis (需要实际的Redis客户端)
            # await self._store_tasks_to_redis(tasks)
            
        except Exception as e:
            logger.error(f"❌ 添加任务到任务池失败: {e}")
    
    async def _update_adaptive_config(self, verification_results: List[TaskVerificationMetrics]):
        """更新自适应配置"""
        try:
            if not verification_results:
                return
            
            # 计算成功率
            passed_count = sum(1 for r in verification_results if r.verification_passed)
            success_rate = passed_count / len(verification_results)
            
            # 记录成功率历史
            for result in verification_results:
                self.adaptive_config.record_success(result.verification_passed)
            
            # 计算效率指标
            efficiency_metrics = {
                "verification_success_rate": success_rate,
                "average_quality_score": sum(r.overall_score for r in verification_results) / len(verification_results),
                "processing_efficiency": self.metrics.generation_efficiency
            }
            
            # 调整阈值
            self.adaptive_config.adjust_thresholds(success_rate, efficiency_metrics)
            
            logger.debug(f"🔧 自适应配置已更新 (成功率: {success_rate:.3f})")
            
        except Exception as e:
            logger.error(f"❌ 更新自适应配置失败: {e}")
    
    def _generate_quality_report(self, verification_results: List[TaskVerificationMetrics], 
                               request: Dict[str, Any]) -> Dict[str, Any]:
        """生成质量报告"""
        try:
            analysis = self.batch_processor.analyze_verification_results(verification_results)
            
            report = {
                "request_id": request.get("request_id", "unknown"),
                "timestamp": datetime.now().isoformat(),
                "trajectory_id": request.get("trajectory", {}).get("trajectory_id", "unknown"),
                "processing_summary": {
                    "seed_tasks_generated": self.metrics.atomic_tasks_generated,
                    "depth_extended_tasks": self.metrics.depth_extended_tasks,
                    "width_extended_tasks": self.metrics.width_extended_tasks,
                    "verification_pass_rate": analysis.get("pass_rate", 0.0),
                    "average_quality_score": analysis.get("average_overall_score", 0.0)
                },
                "quality_analysis": analysis,
                "adaptive_config_snapshot": {
                    "current_success_rate": self.adaptive_config.get_current_success_rate(),
                    "depth_threshold": self.adaptive_config.depth_config["superset_confidence_threshold"],
                    "width_threshold": self.adaptive_config.width_config["semantic_similarity_threshold"],
                    "batch_size": self.adaptive_config.batch_config["batch_size"]
                },
                "performance_metrics": {
                    "total_processing_time": self.metrics.processing_time_seconds,
                    "average_time_per_trajectory": (
                        self.metrics.processing_time_seconds / max(self.metrics.total_trajectories_processed, 1)
                    ),
                    "generation_efficiency": self.metrics.generation_efficiency
                }
            }
            
            return report
            
        except Exception as e:
            logger.error(f"❌ 生成质量报告失败: {e}")
            return {"error": str(e)}
    
    # 回调函数设置
    def set_task_generated_callback(self, callback: Callable[[List[Any]], None]):
        """设置任务生成回调函数"""
        self.task_generated_callback = callback
        logger.info("✅ 任务生成回调函数已设置")
    
    def set_quality_report_callback(self, callback: Callable[[Dict[str, Any]], None]):
        """设置质量报告回调函数"""
        self.quality_report_callback = callback
        logger.info("✅ 质量报告回调函数已设置")
    
    # 状态查询方法
    def get_status(self) -> Dict[str, Any]:
        """获取触发器状态"""
        return {
            "is_running": self.is_running,
            "queue_sizes": self.extension_queue.qsize(),
            "metrics": asdict(self.metrics),
            "adaptive_config": {
                "current_success_rate": self.adaptive_config.get_current_success_rate(),
                "depth_threshold": self.adaptive_config.depth_config["superset_confidence_threshold"],
                "width_threshold": self.adaptive_config.width_config["semantic_similarity_threshold"],
                "batch_size": self.adaptive_config.batch_config["batch_size"]
            }
        }
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """获取性能总结"""
        if self.metrics.total_trajectories_processed == 0:
            return {"status": "no_data"}
        
        return {
            "total_trajectories": self.metrics.total_trajectories_processed,
            "total_tasks_generated": self.metrics.total_tasks_generated,
            "generation_efficiency": self.metrics.generation_efficiency,
            "verification_pass_rate": self.metrics.verification_pass_rate,
            "average_processing_time": (
                self.metrics.processing_time_seconds / self.metrics.total_trajectories_processed
            ),
            "quality_score": self.metrics.average_quality_score,
            "uptime_seconds": time.time() - self.metrics.start_time
        }


class RealTimeExtensionManager:
    """实时扩展管理器 - 提供统一的管理接口"""
    
    def __init__(self, trigger: RealTimeExtensionTrigger):
        self.trigger = trigger
        self.monitoring_enabled = False
        self.performance_history = []
    
    async def start_monitoring(self, interval_seconds: int = 60):
        """开始性能监控"""
        self.monitoring_enabled = True
        
        while self.monitoring_enabled:
            try:
                await asyncio.sleep(interval_seconds)
                
                # 收集性能数据
                performance_data = {
                    "timestamp": datetime.now().isoformat(),
                    "status": self.trigger.get_status(),
                    "performance": self.trigger.get_performance_summary()
                }
                
                self.performance_history.append(performance_data)
                
                # 保持历史记录大小
                if len(self.performance_history) > 100:
                    self.performance_history.pop(0)
                
                # 日志记录
                status = performance_data["status"]
                queue_total = status["queue_sizes"]["total"]
                success_rate = status["adaptive_config"]["current_success_rate"]
                
                logger.info(f"📊 性能监控 - 队列: {queue_total}, 成功率: {success_rate:.3f}")
                
            except Exception as e:
                logger.error(f"❌ 性能监控异常: {e}")
    
    def stop_monitoring(self):
        """停止性能监控"""
        self.monitoring_enabled = False
        logger.info("🛑 性能监控已停止")
    
    def get_monitoring_report(self) -> Dict[str, Any]:
        """获取监控报告"""
        if not self.performance_history:
            return {"status": "no_monitoring_data"}
        
        recent_data = self.performance_history[-10:]  # 最近10次监控数据
        
        # 计算趋势
        success_rates = [d["status"]["adaptive_config"]["current_success_rate"] for d in recent_data]
        avg_success_rate = sum(success_rates) / len(success_rates)
        
        queue_sizes = [d["status"]["queue_sizes"]["total"] for d in recent_data]
        avg_queue_size = sum(queue_sizes) / len(queue_sizes)
        
        return {
            "monitoring_period": {
                "start": self.performance_history[0]["timestamp"],
                "end": self.performance_history[-1]["timestamp"],
                "data_points": len(self.performance_history)
            },
            "current_status": self.trigger.get_status(),
            "trends": {
                "average_success_rate": avg_success_rate,
                "average_queue_size": avg_queue_size,
                "success_rate_trend": "stable" if max(success_rates) - min(success_rates) < 0.1 else "variable"
            },
            "recommendations": self._generate_monitoring_recommendations(avg_success_rate, avg_queue_size)
        }
    
    def _generate_monitoring_recommendations(self, avg_success_rate: float, avg_queue_size: float) -> List[str]:
        """生成监控建议"""
        recommendations = []
        
        if avg_success_rate < 0.7:
            recommendations.append("成功率较低，建议检查质量验证标准")
        
        if avg_queue_size > 50:
            recommendations.append("队列积压严重，建议增加处理并发数")
        elif avg_queue_size < 5:
            recommendations.append("队列使用率较低，可以考虑降低处理资源")
        
        return recommendations