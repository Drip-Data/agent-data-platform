"""
优化的轨迹数据结构
Optimized trajectory data structures with enhanced readability and metrics
"""

import re
import json
import time
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Union
from datetime import datetime
from enum import Enum

class ReasoningQuality(Enum):
    """推理质量等级"""
    POOR = "poor"
    FAIR = "fair"
    GOOD = "good"
    EXCELLENT = "excellent"

@dataclass
class TokenMetrics:
    """Token使用指标"""
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost_estimate: float = 0.0
    model_name: str = "unknown"
    
    def __post_init__(self):
        if self.total_tokens == 0:
            self.total_tokens = self.input_tokens + self.output_tokens

@dataclass
class DecisionContext:
    """决策上下文"""
    situation_analysis: str = ""
    available_options: List[str] = field(default_factory=list)
    selected_option: str = ""
    selection_reasoning: str = ""
    confidence_score: float = 0.0
    alternatives_considered: List[str] = field(default_factory=list)

@dataclass
class PerformanceMetrics:
    """性能指标"""
    execution_time_ms: int = 0
    token_metrics: TokenMetrics = field(default_factory=TokenMetrics)
    retry_count: int = 0
    backtrack_count: int = 0
    success_probability: float = 1.0
    efficiency_score: float = 1.0

@dataclass
class QualityAssessment:
    """质量评估"""
    reasoning_quality: ReasoningQuality = ReasoningQuality.FAIR
    output_completeness: float = 1.0
    accuracy_score: float = 1.0
    explanation_clarity: float = 1.0
    overall_score: float = 1.0

@dataclass
class OptimizedTrajectoryStep:
    """优化的轨迹步骤"""
    step_id: int
    step_type: str
    timestamp: datetime = field(default_factory=datetime.now)
    
    # 决策和推理
    decision_context: DecisionContext = field(default_factory=DecisionContext)
    raw_thinking: str = ""
    structured_reasoning: Dict[str, str] = field(default_factory=dict)
    
    # 执行细节
    tool_id: str = ""
    action: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)
    raw_output: str = ""
    cleaned_output: str = ""
    
    # 指标和质量
    performance_metrics: PerformanceMetrics = field(default_factory=PerformanceMetrics)
    quality_assessment: QualityAssessment = field(default_factory=QualityAssessment)
    
    # 状态
    success: bool = True
    error_message: str = ""

@dataclass
class OptimizedTrajectory:
    """优化的完整轨迹"""
    task_id: str
    task_name: str
    task_description: str
    runtime_id: str
    
    # 执行步骤
    steps: List[OptimizedTrajectoryStep] = field(default_factory=list)
    
    # 整体结果
    success: bool = True
    final_result: str = ""
    total_duration_ms: int = 0
    
    # 聚合指标
    total_tokens: int = 0
    total_cost: float = 0.0
    overall_quality_score: float = 1.0
    
    # 统计信息
    step_count: int = 0
    retry_count: int = 0
    backtrack_count: int = 0
    tool_switch_count: int = 0
    
    # 元数据
    created_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)