"""
轨迹增强器 - 收集和计算详细的执行元数据
实现OpenHands风格的细粒度追踪
"""

import time
import uuid
import logging
import psutil
import platform
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from core.interfaces import TrajectoryResult, ExecutionStep, LLMInteraction

logger = logging.getLogger(__name__)

@dataclass
class ResourceMetrics:
    """资源使用指标"""
    cpu_percent: float = 0.0
    memory_mb: float = 0.0
    network_bytes_sent: int = 0
    network_bytes_received: int = 0
    start_timestamp: float = field(default_factory=time.time)
    end_timestamp: Optional[float] = None
    
    def calculate_duration(self) -> float:
        """计算持续时间"""
        end_time = self.end_timestamp or time.time()
        return end_time - self.start_timestamp

class TrajectoryEnhancer:
    """轨迹增强器 - 收集详细的执行元数据"""
    
    def __init__(self):
        self.session_start_time = time.time()
        self.task_resource_start = {}  # 记录每个任务的资源开始状态
        
    def start_task_tracking(self, task_id: str) -> Dict[str, Any]:
        """开始跟踪任务的资源使用"""
        try:
            process = psutil.Process()
            net_io = psutil.net_io_counters()
            
            start_metrics = ResourceMetrics(
                cpu_percent=process.cpu_percent(),
                memory_mb=process.memory_info().rss / 1024 / 1024,
                network_bytes_sent=net_io.bytes_sent if net_io else 0,
                network_bytes_received=net_io.bytes_recv if net_io else 0
            )
            
            self.task_resource_start[task_id] = start_metrics
            
            return {
                "tracking_started": True,
                "start_time": start_metrics.start_timestamp,
                "process_id": process.pid
            }
        except Exception as e:
            logger.warning(f"无法启动资源跟踪: {e}")
            return {"tracking_started": False, "error": str(e)}
    
    def calculate_step_resource_usage(self, step_start_time: float, step_end_time: float) -> Dict[str, Any]:
        """计算步骤的资源使用情况"""
        try:
            process = psutil.Process()
            
            return {
                "cpu_usage_percent": process.cpu_percent(),
                "memory_usage_mb": round(process.memory_info().rss / 1024 / 1024, 2),
                "execution_time_ms": round((step_end_time - step_start_time) * 1000, 2),
                "timestamp": step_end_time
            }
        except Exception as e:
            logger.warning(f"无法计算资源使用: {e}")
            return {"error": str(e)}
    
    def create_sub_event(self, event_type: str, description: str, metadata: Dict[str, Any] = None) -> Dict[str, Any]:
        """创建子事件记录"""
        return {
            "event_id": str(uuid.uuid4()),
            "timestamp": time.time(),
            "event_type": event_type,
            "description": description,
            "metadata": metadata or {}
        }
    
    def calculate_llm_metrics(self, trajectory: TrajectoryResult) -> Dict[str, Any]:
        """计算累积的LLM使用指标"""
        total_interactions = 0
        total_prompt_tokens = 0
        total_completion_tokens = 0
        total_cost = 0.0
        total_response_time = 0.0
        
        providers_used = set()
        models_used = set()
        
        for step in trajectory.steps:
            for interaction in step.llm_interactions:
                total_interactions += 1
                
                # 提取令牌使用信息
                if interaction.token_usage:
                    total_prompt_tokens += interaction.token_usage.get('prompt_tokens', 0)
                    total_completion_tokens += interaction.token_usage.get('completion_tokens', 0)
                
                # 提取成本信息
                if interaction.cost_info:
                    total_cost += interaction.cost_info.get('total_cost', 0.0)
                
                total_response_time += interaction.response_time
                
                if interaction.provider:
                    providers_used.add(interaction.provider)
                if interaction.model:
                    models_used.add(interaction.model)
        
        return {
            "total_interactions": total_interactions,
            "accumulated_cost": round(total_cost, 6),
            "accumulated_token_usage": {
                "total_tokens": total_prompt_tokens + total_completion_tokens,
                "prompt_tokens": total_prompt_tokens,
                "completion_tokens": total_completion_tokens
            },
            "average_response_time": round(total_response_time / max(total_interactions, 1), 3),
            "total_response_time": round(total_response_time, 3),
            "providers_used": list(providers_used),
            "models_used": list(models_used)
        }
    
    def calculate_error_handling_stats(self, trajectory: TrajectoryResult) -> Dict[str, Any]:
        """计算错误处理统计"""
        errors_encountered = 0
        retry_attempts = 0
        error_types = []
        recovery_successful = trajectory.success
        
        for step in trajectory.steps:
            if step.error_type or step.error_message:
                errors_encountered += 1
                if step.error_type:
                    error_types.append(step.error_type.value if hasattr(step.error_type, 'value') else str(step.error_type))
            
            # 检查是否有重试尝试（基于相似的action_params）
            # 这是一个简化的实现，实际中可能需要更复杂的逻辑
            if not step.success and step.step_id > 1:
                retry_attempts += 1
        
        return {
            "errors_encountered": errors_encountered,
            "retry_attempts": retry_attempts,
            "error_types": list(set(error_types)),
            "recovery_successful": recovery_successful,
            "error_rate": round(errors_encountered / max(len(trajectory.steps), 1), 3)
        }
    
    def get_execution_environment(self) -> Dict[str, Any]:
        """获取执行环境信息"""
        try:
            return {
                "platform": platform.system(),
                "platform_version": platform.version(),
                "python_version": platform.python_version(),
                "cpu_count": psutil.cpu_count(),
                "total_memory_gb": round(psutil.virtual_memory().total / 1024 / 1024 / 1024, 2),
                "session_start_time": self.session_start_time,
                "environment_id": str(uuid.uuid4())
            }
        except Exception as e:
            logger.warning(f"无法获取环境信息: {e}")
            return {"error": str(e)}
    
    def enhance_trajectory(self, trajectory: TrajectoryResult) -> TrajectoryResult:
        """增强轨迹，添加详细元数据"""
        try:
            # 计算LLM指标
            trajectory.llm_metrics = self.calculate_llm_metrics(trajectory)
            
            # 添加执行环境信息
            trajectory.execution_environment = self.get_execution_environment()
            
            # 计算错误处理统计
            trajectory.error_handling = self.calculate_error_handling_stats(trajectory)
            
            # 添加会话级别的元数据
            if 'session_id' not in trajectory.metadata:
                trajectory.metadata['session_id'] = f"session_{trajectory.task_id}_{int(trajectory.created_at)}"
            
            trajectory.metadata['enhanced_at'] = time.time()
            trajectory.metadata['enhancer_version'] = "1.0.0"
            
            logger.info(f"轨迹增强完成: {trajectory.task_id}")
            return trajectory
            
        except Exception as e:
            logger.error(f"轨迹增强失败: {e}")
            return trajectory
    
    def enhance_step_with_causality(self, step: ExecutionStep, 
                                  previous_step: Optional[ExecutionStep] = None,
                                  triggering_event: str = None) -> ExecutionStep:
        """为步骤添加因果关系信息"""
        if previous_step:
            step.caused_by_step = previous_step.step_id
        
        if triggering_event:
            step.triggering_event = triggering_event
        
        return step
    
    def add_sub_event_to_step(self, step: ExecutionStep, event_type: str, 
                            description: str, metadata: Dict[str, Any] = None) -> ExecutionStep:
        """为步骤添加子事件"""
        sub_event = self.create_sub_event(event_type, description, metadata)
        step.sub_events.append(sub_event)
        return step