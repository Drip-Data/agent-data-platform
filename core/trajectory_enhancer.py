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
        """增强轨迹，添加详细元数据和成本信息"""
        try:
            # 计算LLM指标
            trajectory.llm_metrics = self.calculate_llm_metrics(trajectory)
            
            # 🆕 注入成本分析信息
            from core.cost_analyzer import get_cost_analyzer
            cost_analyzer = get_cost_analyzer()
            
            # 构建步骤日志用于成本分析
            step_logs = []
            for step in trajectory.steps:
                step_log = {
                    'step_id': step.step_id,
                    'token_usage': {},
                    'cost_info': {},
                    'tools_used': [step.action_params.get('tool', 'unknown')] if step.action_params else []
                }
                
                # 从LLM交互中收集token和成本信息
                for interaction in step.llm_interactions:
                    if interaction.token_usage:
                        step_log['token_usage'] = interaction.token_usage
                    if interaction.cost_info:
                        step_log['cost_info'] = interaction.cost_info
                
                step_logs.append(step_log)
            
            # 将轨迹数据转换为字典格式用于成本分析
            trajectory_dict = {
                'task_id': trajectory.task_id,
                'task_type': getattr(trajectory, 'task_type', 'unknown'),
                'success': trajectory.success,
                'execution_time': trajectory.total_duration,
                'step_logs': step_logs
            }
            
            # 分析并设置成本信息
            cost_analysis = cost_analyzer.analyze_trajectory_cost(trajectory_dict, step_logs)
            trajectory.cost_analysis = cost_analysis
            
            # 添加执行环境信息
            trajectory.execution_environment = self.get_execution_environment()
            
            # 计算错误处理统计
            trajectory.error_handling = self.calculate_error_handling_stats(trajectory)
            
            # 添加会话级别的元数据
            if 'session_id' not in trajectory.metadata:
                trajectory.metadata['session_id'] = f"session_{trajectory.task_id}_{int(trajectory.created_at)}"
            
            trajectory.metadata['enhanced_at'] = time.time()
            trajectory.metadata['enhancer_version'] = "1.1.0"  # 版本号更新，表示加入了成本分析
            
            logger.info(f"轨迹增强完成 (含成本分析): {trajectory.task_id}, 成本: ${cost_analysis.total_cost_usd:.4f}")
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
    
    def merge_related_steps(self, trajectory: TrajectoryResult) -> TrajectoryResult:
        """🔧 优化：合并相关步骤，减少轨迹复杂度
        
        智能合并连续的相关步骤，保持轨迹的逻辑清晰度
        """
        if not trajectory.steps or len(trajectory.steps) <= 2:
            return trajectory
        
        logger.info(f"🔄 开始合并轨迹步骤: 原始步骤数 {len(trajectory.steps)}")
        
        merged_steps = []
        i = 0
        
        while i < len(trajectory.steps):
            current_step = trajectory.steps[i]
            
            # 检查是否可以与后续步骤合并
            merge_group = [current_step]
            j = i + 1
            
            while j < len(trajectory.steps):
                next_step = trajectory.steps[j]
                
                if self._should_merge_steps(current_step, next_step):
                    merge_group.append(next_step)
                    j += 1
                else:
                    break
            
            if len(merge_group) > 1:
                # 合并多个步骤
                merged_step = self._merge_step_group(merge_group)
                merged_steps.append(merged_step)
                logger.debug(f"🔗 合并了 {len(merge_group)} 个步骤到步骤 {merged_step.step_id}")
            else:
                # 单个步骤，不需要合并
                merged_steps.append(current_step)
            
            i = j if j > i + 1 else i + 1
        
        # 重新编号步骤
        for idx, step in enumerate(merged_steps):
            step.step_id = idx + 1
        
        trajectory.steps = merged_steps
        logger.info(f"✅ 步骤合并完成: {len(merged_steps)} 个合并后步骤 (压缩率: {len(merged_steps)/len(trajectory.steps)*100:.1f}%)")
        
        return trajectory
    
    def _should_merge_steps(self, step1: ExecutionStep, step2: ExecutionStep) -> bool:
        """判断两个步骤是否应该合并"""
        # 不合并失败步骤，保持错误的可见性
        if not step1.success or not step2.success:
            return False
        
        # 不合并不同工具的操作
        params1 = step1.action_params or {}
        params2 = step2.action_params or {}
        tool1 = params1.get('tool_id', '')
        tool2 = params2.get('tool_id', '')
        
        if tool1 != tool2:
            return False
        
        # 不合并动作类型差异很大的步骤
        if step1.action_type != step2.action_type:
            # 除非是相关的动作类型
            related_action_types = [
                {'CODE_GENERATION', 'CODE_EXECUTION'},
                {'RESEARCH_QUERY', 'KNOWLEDGE_EXTRACTION'},
                {'DATA_RETRIEVAL', 'ANALYSIS_PROCESSING'},
            ]
            
            action1_name = step1.action_type.value if hasattr(step1.action_type, 'value') else str(step1.action_type)
            action2_name = step2.action_type.value if hasattr(step2.action_type, 'value') else str(step2.action_type)
            
            is_related = any(
                action1_name in group and action2_name in group 
                for group in related_action_types
            )
            
            if not is_related:
                return False
        
        # 检查时间间隔，如果太久远则不合并
        time_diff = abs(step2.timestamp - step1.timestamp)
        if time_diff > 30:  # 超过30秒不合并
            return False
        
        # 检查是否是连续的重试步骤
        action1 = params1.get('action', '')
        action2 = params2.get('action', '')
        if action1 == action2 and 'retry' in step2.observation.lower():
            return True
        
        # 检查是否是相同工具的连续操作
        if tool1 == tool2 and action1 == action2:
            return True
        
        return False
    
    def _merge_step_group(self, steps: List[ExecutionStep]) -> ExecutionStep:
        """合并一组相关步骤"""
        if not steps:
            raise ValueError("Cannot merge empty step group")
        
        if len(steps) == 1:
            return steps[0]
        
        # 使用第一个步骤作为基础
        merged_step = steps[0]
        
        # 合并观察结果
        observations = []
        for i, step in enumerate(steps):
            if step.observation:
                prefix = f"[步骤{i+1}] " if len(steps) > 1 else ""
                observations.append(f"{prefix}{step.observation}")
        
        merged_step.observation = "\n".join(observations)
        
        # 合并执行时间
        total_duration = sum(step.duration for step in steps)
        merged_step.duration = total_duration
        
        # 合并LLM交互
        all_interactions = []
        for step in steps:
            all_interactions.extend(step.llm_interactions)
        merged_step.llm_interactions = all_interactions
        
        # 合并子事件
        all_sub_events = []
        for step in steps:
            all_sub_events.extend(step.sub_events)
        merged_step.sub_events = all_sub_events
        
        # 更新元数据
        merged_step.sub_events.append({
            "event_type": "step_merge",
            "description": f"合并了 {len(steps)} 个相关步骤",
            "timestamp": time.time(),
            "metadata": {
                "original_step_count": len(steps),
                "merged_step_ids": [step.step_id for step in steps],
                "total_duration": total_duration
            }
        })
        
        return merged_step
    
    def generate_execution_summary(self, trajectory: TrajectoryResult) -> Dict[str, Any]:
        """🔧 优化：生成执行摘要和推荐信息
        
        分析轨迹并生成详细的执行摘要，包含性能指标和改进建议
        """
        summary = {
            "overview": {},
            "performance_metrics": {},
            "tool_usage_analysis": {},
            "error_analysis": {},
            "recommendations": [],
            "success_factors": [],
            "improvement_areas": []
        }
        
        steps = trajectory.steps
        if not steps:
            return summary
        
        # 基础概览
        summary["overview"] = {
            "total_steps": len(steps),
            "successful_steps": sum(1 for step in steps if step.success),
            "failed_steps": sum(1 for step in steps if not step.success),
            "execution_time": trajectory.total_duration,
            "success_rate": sum(1 for step in steps if step.success) / len(steps) if steps else 0,
            "task_complexity": self._assess_task_complexity(trajectory)
        }
        
        # 性能指标
        summary["performance_metrics"] = {
            "average_step_duration": trajectory.total_duration / len(steps) if steps else 0,
            "longest_step_duration": max((step.duration for step in steps), default=0),
            "total_llm_interactions": sum(len(step.llm_interactions) for step in steps),
            "retry_attempts": sum(1 for step in steps if 'retry' in step.observation.lower() or not step.success),
            "efficiency_score": self._calculate_efficiency_score(trajectory)
        }
        
        # 工具使用分析
        summary["tool_usage_analysis"] = self._analyze_tool_usage(trajectory)
        
        # 错误分析
        summary["error_analysis"] = self._analyze_errors(trajectory)
        
        # 生成推荐
        summary["recommendations"] = self._generate_recommendations(trajectory, summary)
        
        # 成功因素
        summary["success_factors"] = self._identify_success_factors(trajectory)
        
        # 改进领域
        summary["improvement_areas"] = self._identify_improvement_areas(trajectory, summary)
        
        return summary
    
    def _assess_task_complexity(self, trajectory: TrajectoryResult) -> str:
        """评估任务复杂度"""
        steps = trajectory.steps
        tool_count = len(trajectory.used_tools) if trajectory.used_tools else 0
        error_count = sum(1 for step in steps if not step.success)
        
        if len(steps) > 15 or tool_count > 5 or error_count > 5:
            return "high"
        elif len(steps) > 8 or tool_count > 3 or error_count > 2:
            return "medium"
        else:
            return "low"
    
    def _calculate_efficiency_score(self, trajectory: TrajectoryResult) -> float:
        """计算执行效率分数 (0-1)"""
        if not trajectory.steps:
            return 0.0
        
        success_rate = sum(1 for step in trajectory.steps if step.success) / len(trajectory.steps)
        
        # 重试惩罚
        retry_penalty = sum(1 for step in trajectory.steps if 'retry' in step.observation.lower()) * 0.1
        retry_penalty = min(retry_penalty, 0.3)  # 最大惩罚30%
        
        # 时间效率（基于平均步骤时间）
        avg_duration = trajectory.total_duration / len(trajectory.steps)
        time_efficiency = 1.0 if avg_duration < 5 else max(0.5, 1.0 - (avg_duration - 5) * 0.05)
        
        efficiency = (success_rate * 0.6 + time_efficiency * 0.4) - retry_penalty
        return max(0.0, min(1.0, efficiency))
    
    def _analyze_tool_usage(self, trajectory: TrajectoryResult) -> Dict[str, Any]:
        """分析工具使用情况"""
        tool_usage = {}
        action_types = {}
        
        for step in trajectory.steps:
            if hasattr(step, 'action_params') and step.action_params:
                # 优先从step本身获取tool_id，增强轨迹分析的准确性
                tool_id = getattr(step, 'tool_id', None) or step.action_params.get('tool_id', 'unknown')
                tool_usage[tool_id] = tool_usage.get(tool_id, 0) + 1
            
            action_type = step.action_type.value if hasattr(step.action_type, 'value') else str(step.action_type)
            action_types[action_type] = action_types.get(action_type, 0) + 1
        
        most_used_tool = max(tool_usage, key=tool_usage.get) if tool_usage else None
        dominant_action_type = max(action_types, key=action_types.get) if action_types else None
        
        return {
            "tools_used": list(tool_usage.keys()),
            "tool_usage_frequency": tool_usage,
            "most_used_tool": most_used_tool,
            "action_type_distribution": action_types,
            "dominant_action_type": dominant_action_type,
            "tool_switching_frequency": self._calculate_tool_switching(trajectory.steps)
        }
    
    def _calculate_tool_switching(self, steps: List[ExecutionStep]) -> int:
        """计算工具切换频率"""
        switches = 0
        prev_tool = None
        
        for step in steps:
            if hasattr(step, 'action_params') and step.action_params:
                current_tool = step.action_params.get('tool_id')
                if prev_tool and prev_tool != current_tool:
                    switches += 1
                prev_tool = current_tool
        
        return switches
    
    def _analyze_errors(self, trajectory: TrajectoryResult) -> Dict[str, Any]:
        """分析错误模式"""
        failed_steps = [step for step in trajectory.steps if not step.success]
        
        error_types = {}
        error_tools = {}
        error_patterns = []
        
        for step in failed_steps:
            if step.error_type:
                error_type = step.error_type.value if hasattr(step.error_type, 'value') else str(step.error_type)
                error_types[error_type] = error_types.get(error_type, 0) + 1
            
            if hasattr(step, 'action_params') and step.action_params:
                tool_id = step.action_params.get('tool_id', 'unknown')
                error_tools[tool_id] = error_tools.get(tool_id, 0) + 1
            
            # 检测错误模式
            if step.error_message:
                if 'timeout' in step.error_message.lower():
                    error_patterns.append("timeout_issues")
                elif 'parameter' in step.error_message.lower():
                    error_patterns.append("parameter_errors")
                elif 'network' in step.error_message.lower():
                    error_patterns.append("network_issues")
        
        return {
            "total_errors": len(failed_steps),
            "error_rate": len(failed_steps) / len(trajectory.steps) if trajectory.steps else 0,
            "error_types": error_types,
            "problematic_tools": error_tools,
            "error_patterns": list(set(error_patterns)),
            "recovery_success": self._calculate_recovery_success(trajectory.steps)
        }
    
    def _calculate_recovery_success(self, steps: List[ExecutionStep]) -> float:
        """计算错误恢复成功率"""
        recovery_attempts = 0
        successful_recoveries = 0
        
        for i, step in enumerate(steps[:-1]):
            if not step.success:
                recovery_attempts += 1
                # 检查下一个步骤是否成功（可能是恢复）
                if i + 1 < len(steps) and steps[i + 1].success:
                    successful_recoveries += 1
        
        return successful_recoveries / recovery_attempts if recovery_attempts > 0 else 0.0
    
    def _generate_recommendations(self, trajectory: TrajectoryResult, summary: Dict[str, Any]) -> List[str]:
        """生成改进推荐"""
        recommendations = []
        
        # 基于成功率的推荐
        if summary["overview"]["success_rate"] < 0.7:
            recommendations.append("建议优化错误处理机制，提高任务执行成功率")
        
        # 基于效率的推荐
        if summary["performance_metrics"]["efficiency_score"] < 0.6:
            recommendations.append("建议优化执行流程，减少不必要的重试和等待时间")
        
        # 基于工具使用的推荐
        tool_switching = summary["tool_usage_analysis"]["tool_switching_frequency"]
        if tool_switching > len(trajectory.steps) * 0.5:
            recommendations.append("频繁的工具切换可能影响效率，建议优化工具选择策略")
        
        # 基于错误分析的推荐
        error_rate = summary["error_analysis"]["error_rate"]
        if error_rate > 0.3:
            recommendations.append("错误率较高，建议加强参数验证和错误预防")
        
        # 基于复杂度的推荐
        if summary["overview"]["task_complexity"] == "high":
            recommendations.append("任务复杂度较高，建议考虑将任务分解为更小的子任务")
        
        return recommendations
    
    def _identify_success_factors(self, trajectory: TrajectoryResult) -> List[str]:
        """识别成功因素"""
        factors = []
        
        if trajectory.success:
            factors.append("任务成功完成")
            
            # 分析成功步骤的模式
            successful_tools = set()
            for step in trajectory.steps:
                if step.success and hasattr(step, 'action_params') and step.action_params:
                    tool_id = step.action_params.get('tool_id')
                    if tool_id:
                        successful_tools.add(tool_id)
            
            if successful_tools:
                factors.append(f"有效使用了以下工具: {', '.join(list(successful_tools)[:3])}")
        
        # 识别高效执行模式
        quick_successes = [step for step in trajectory.steps if step.success and step.duration < 2]
        if len(quick_successes) > len(trajectory.steps) * 0.5:
            factors.append("大部分步骤执行迅速，显示了良好的执行效率")
        
        return factors
    
    def _identify_improvement_areas(self, trajectory: TrajectoryResult, summary: Dict[str, Any]) -> List[str]:
        """识别改进领域"""
        areas = []
        
        # 基于性能指标
        if summary["performance_metrics"]["retry_attempts"] > 3:
            areas.append("减少重试次数和错误恢复时间")
        
        if summary["performance_metrics"]["average_step_duration"] > 10:
            areas.append("优化步骤执行时间，提高整体效率")
        
        # 基于错误分析
        if summary["error_analysis"]["error_rate"] > 0.2:
            areas.append("改进错误预防和处理机制")
        
        # 基于工具使用
        if len(summary["tool_usage_analysis"]["tools_used"]) > 5:
            areas.append("简化工具使用策略，减少工具切换开销")
        
        return areas