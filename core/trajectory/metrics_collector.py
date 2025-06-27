"""
轨迹指标收集器
Trajectory metrics collector for performance and cost analysis
"""

import time
import json
import re
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from datetime import datetime
import logging

from .optimized_structures import TokenMetrics, PerformanceMetrics, QualityAssessment, ReasoningQuality

logger = logging.getLogger(__name__)

@dataclass
class StepMonitor:
    """步骤监控器"""
    step_id: int
    start_time: float
    start_memory: float = 0.0
    token_count_start: int = 0
    
    def get_duration_ms(self) -> int:
        """获取执行时间（毫秒）"""
        return int((time.time() - self.start_time) * 1000)

class MetricsCollector:
    """指标收集器"""
    
    def __init__(self):
        self.model_pricing = {
            "gpt-4": {"input": 0.03, "output": 0.06},
            "gpt-3.5-turbo": {"input": 0.001, "output": 0.002},
            "claude-3": {"input": 0.015, "output": 0.075},
            "gemini-pro": {"input": 0.00025, "output": 0.0005},
            "default": {"input": 0.001, "output": 0.002}
        }
        
        self.retry_counts = {}
        self.backtrack_counts = {}
    
    def start_step_monitoring(self, step_id: int) -> StepMonitor:
        """开始步骤监控"""
        return StepMonitor(
            step_id=step_id,
            start_time=time.time()
        )
    
    def collect_step_metrics(self, 
                           monitor: StepMonitor,
                           step_data: Dict[str, Any],
                           llm_response: str = "",
                           tool_result: Any = None) -> PerformanceMetrics:
        """收集步骤性能指标"""
        
        # 执行时间
        execution_time_ms = monitor.get_duration_ms()
        
        # Token指标
        token_metrics = self._calculate_token_metrics(step_data, llm_response)
        
        # 重试和回溯统计
        step_id = monitor.step_id
        retry_count = self.retry_counts.get(step_id, 0)
        backtrack_count = self.backtrack_counts.get(step_id, 0)
        
        # 成功概率
        success = step_data.get('success', True)
        success_probability = 1.0 if success else 0.0
        
        # 效率评分
        efficiency_score = self._calculate_efficiency_score(
            execution_time_ms, retry_count, success
        )
        
        return PerformanceMetrics(
            execution_time_ms=execution_time_ms,
            token_metrics=token_metrics,
            retry_count=retry_count,
            backtrack_count=backtrack_count,
            success_probability=success_probability,
            efficiency_score=efficiency_score
        )
    
    def assess_step_quality(self, 
                          step_data: Dict[str, Any],
                          cleaned_output: str = "") -> QualityAssessment:
        """评估步骤质量"""
        
        thinking = step_data.get('thinking', '')
        tool_output = step_data.get('tool_output', '')
        success = step_data.get('success', True)
        
        # 推理质量评估
        reasoning_quality = self._assess_reasoning_quality(thinking)
        
        # 输出完整性
        output_completeness = self._assess_output_completeness(tool_output, cleaned_output)
        
        # 准确性评分
        accuracy_score = 1.0 if success else 0.5
        
        # 解释清晰度
        explanation_clarity = self._assess_explanation_clarity(thinking, cleaned_output)
        
        # 总体评分
        overall_score = (
            self._quality_to_score(reasoning_quality) * 0.3 +
            output_completeness * 0.3 +
            accuracy_score * 0.25 +
            explanation_clarity * 0.15
        )
        
        return QualityAssessment(
            reasoning_quality=reasoning_quality,
            output_completeness=output_completeness,
            accuracy_score=accuracy_score,
            explanation_clarity=explanation_clarity,
            overall_score=overall_score
        )
    
    def record_retry(self, step_id: int):
        """记录重试"""
        self.retry_counts[step_id] = self.retry_counts.get(step_id, 0) + 1
    
    def record_backtrack(self, step_id: int):
        """记录回溯"""
        self.backtrack_counts[step_id] = self.backtrack_counts.get(step_id, 0) + 1
    
    def _calculate_token_metrics(self, step_data: Dict[str, Any], llm_response: str) -> TokenMetrics:
        """计算Token指标"""
        
        # 尝试从step_data中提取token信息
        llm_interactions = step_data.get('llm_interactions', [])
        
        total_input = 0
        total_output = 0
        model_name = "unknown"
        
        for interaction in llm_interactions:
            if isinstance(interaction, dict):
                total_input += interaction.get('input_tokens', 0)
                total_output += interaction.get('output_tokens', 0)
                if not model_name or model_name == "unknown":
                    model_name = interaction.get('model', 'unknown')
        
        # 如果没有记录，尝试估算
        if total_input == 0 and total_output == 0:
            thinking = step_data.get('thinking', '')
            tool_output = step_data.get('tool_output', '')
            
            # 简单估算：4个字符约等于1个token
            total_input = max(len(thinking) // 4, 1)
            total_output = max(len(tool_output) // 4, 1)
        
        # 计算成本
        cost_estimate = self._calculate_cost(total_input, total_output, model_name)
        
        return TokenMetrics(
            input_tokens=total_input,
            output_tokens=total_output,
            total_tokens=total_input + total_output,
            cost_estimate=cost_estimate,
            model_name=model_name
        )
    
    def _calculate_cost(self, input_tokens: int, output_tokens: int, model_name: str) -> float:
        """计算成本"""
        pricing = self.model_pricing.get(model_name, self.model_pricing["default"])
        
        input_cost = (input_tokens / 1000) * pricing["input"]
        output_cost = (output_tokens / 1000) * pricing["output"]
        
        return input_cost + output_cost
    
    def _calculate_efficiency_score(self, execution_time_ms: int, retry_count: int, success: bool) -> float:
        """计算效率评分"""
        base_score = 1.0 if success else 0.3
        
        # 时间惩罚（超过30秒开始惩罚）
        if execution_time_ms > 30000:
            time_penalty = min(0.5, (execution_time_ms - 30000) / 60000)
            base_score *= (1 - time_penalty)
        
        # 重试惩罚
        retry_penalty = min(0.3, retry_count * 0.1)
        base_score *= (1 - retry_penalty)
        
        return max(0.0, min(1.0, base_score))
    
    def _assess_reasoning_quality(self, thinking: str) -> ReasoningQuality:
        """评估推理质量"""
        if not thinking:
            return ReasoningQuality.POOR
        
        # 检查结构化程度
        has_steps = bool(re.search(r'STEP\s+\d+', thinking, re.IGNORECASE))
        has_analysis = any(keyword in thinking.lower() for keyword in 
                          ['analysis', 'reasoning', 'because', 'therefore', 'logic'])
        has_confidence = 'confidence' in thinking.lower()
        
        quality_indicators = sum([has_steps, has_analysis, has_confidence])
        
        if quality_indicators >= 3:
            return ReasoningQuality.EXCELLENT
        elif quality_indicators >= 2:
            return ReasoningQuality.GOOD
        elif quality_indicators >= 1:
            return ReasoningQuality.FAIR
        else:
            return ReasoningQuality.POOR
    
    def _assess_output_completeness(self, raw_output: str, cleaned_output: str) -> float:
        """评估输出完整性"""
        if not raw_output and not cleaned_output:
            return 0.0
        
        # 检查输出长度
        output_length = len(cleaned_output) if cleaned_output else len(raw_output)
        
        if output_length > 1000:
            return 1.0
        elif output_length > 500:
            return 0.8
        elif output_length > 100:
            return 0.6
        elif output_length > 10:
            return 0.4
        else:
            return 0.2
    
    def _assess_explanation_clarity(self, thinking: str, output: str) -> float:
        """评估解释清晰度"""
        total_text = f"{thinking} {output}".lower()
        
        # 检查清晰度指标
        clarity_indicators = [
            'because', 'therefore', 'as a result', 'due to', 'since',
            'first', 'second', 'third', 'finally', 'in conclusion',
            'specifically', 'for example', 'such as', 'namely'
        ]
        
        found_indicators = sum(1 for indicator in clarity_indicators if indicator in total_text)
        
        return min(1.0, found_indicators / 5.0)
    
    def _quality_to_score(self, quality: ReasoningQuality) -> float:
        """将质量等级转换为数值"""
        quality_scores = {
            ReasoningQuality.POOR: 0.25,
            ReasoningQuality.FAIR: 0.5,
            ReasoningQuality.GOOD: 0.75,
            ReasoningQuality.EXCELLENT: 1.0
        }
        return quality_scores.get(quality, 0.5)

class TrajectoryAggregator:
    """轨迹聚合器"""
    
    def __init__(self):
        self.metrics_collector = MetricsCollector()
    
    def aggregate_trajectory_metrics(self, steps: List[Dict[str, Any]]) -> Dict[str, Any]:
        """聚合轨迹指标"""
        
        if not steps:
            return self._empty_metrics()
        
        # 聚合性能指标
        total_duration_ms = sum(step.get('duration', 0) * 1000 for step in steps)
        total_tokens = 0
        total_cost = 0.0
        success_count = 0
        total_retries = 0
        total_backtracks = 0
        quality_scores = []
        
        for step in steps:
            # 模拟指标收集
            monitor = StepMonitor(step_id=step.get('step_id', 0), start_time=time.time())
            metrics = self.metrics_collector.collect_step_metrics(monitor, step)
            quality = self.metrics_collector.assess_step_quality(step)
            
            total_tokens += metrics.token_metrics.total_tokens
            total_cost += metrics.token_metrics.cost_estimate
            total_retries += metrics.retry_count
            total_backtracks += metrics.backtrack_count
            quality_scores.append(quality.overall_score)
            
            if step.get('success', True):
                success_count += 1
        
        # 计算聚合指标
        success_rate = success_count / len(steps) if steps else 0
        avg_quality = sum(quality_scores) / len(quality_scores) if quality_scores else 0
        efficiency_score = self._calculate_trajectory_efficiency(
            total_duration_ms, total_retries, success_rate
        )
        
        return {
            "total_steps": len(steps),
            "successful_steps": success_count,
            "success_rate": success_rate,
            "total_duration_ms": int(total_duration_ms),
            "total_tokens": total_tokens,
            "total_cost": total_cost,
            "total_retries": total_retries,
            "total_backtracks": total_backtracks,
            "average_quality_score": avg_quality,
            "efficiency_score": efficiency_score,
            "cost_per_step": total_cost / len(steps) if steps else 0,
            "tokens_per_step": total_tokens / len(steps) if steps else 0
        }
    
    def _empty_metrics(self) -> Dict[str, Any]:
        """空指标"""
        return {
            "total_steps": 0,
            "successful_steps": 0,
            "success_rate": 0.0,
            "total_duration_ms": 0,
            "total_tokens": 0,
            "total_cost": 0.0,
            "total_retries": 0,
            "total_backtracks": 0,
            "average_quality_score": 0.0,
            "efficiency_score": 0.0,
            "cost_per_step": 0.0,
            "tokens_per_step": 0.0
        }
    
    def _calculate_trajectory_efficiency(self, duration_ms: int, retries: int, success_rate: float) -> float:
        """计算轨迹效率"""
        base_score = success_rate
        
        # 时间效率（假设理想时间为30秒）
        time_efficiency = max(0.0, min(1.0, 30000 / max(duration_ms, 1000)))
        
        # 重试效率
        retry_efficiency = max(0.0, 1.0 - (retries * 0.1))
        
        return (base_score * 0.5 + time_efficiency * 0.3 + retry_efficiency * 0.2)