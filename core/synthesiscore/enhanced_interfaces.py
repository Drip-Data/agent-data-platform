#!/usr/bin/env python3
"""
Enhanced SynthesisCore Interfaces - 基于TaskCraft算法的增强数据结构
"""

import time
import uuid
from datetime import datetime
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Union
from enum import Enum

from core.interfaces import TrajectoryResult, ExecutionStep


class TaskDifficulty(Enum):
    """任务难度枚举"""
    SIMPLE = "simple"      # 1步任务
    MEDIUM = "medium"      # 2-3步任务  
    COMPLEX = "complex"    # 4+步任务


class TaskType(Enum):
    """增强任务类型枚举"""
    ATOMIC = "atomic"          # 原子任务
    DEPTH_EXTENDED = "depth"   # 深度扩展任务
    WIDTH_EXTENDED = "width"   # 宽度扩展任务
    COMPOSITE = "composite"    # 复合任务


class ContentType(Enum):
    """语料内容类型"""
    WEB = "web"
    PDF = "pdf"
    CODE_OUTPUT = "code_output"
    TRAJECTORY = "trajectory"
    IMAGE = "image"


@dataclass
class CorpusContent:
    """语料内容数据结构"""
    source: str                           # 语料来源
    content_type: ContentType             # 内容类型
    text_content: str                     # 文本内容
    metadata: Dict[str, Any]              # 元数据
    extracted_at: str = field(default_factory=lambda: datetime.now().isoformat())
    processing_status: str = "pending"    # 处理状态: pending/processing/completed/failed
    corpus_id: str = field(default_factory=lambda: f"corpus_{uuid.uuid4().hex[:8]}")


@dataclass
class TaskConclusion:
    """任务结论数据结构 - 基于TaskCraft的结论提取"""
    conclusion: str                       # 结论内容
    relationship: str                     # 关系描述 (R)
    content_identifier: str               # 内容标识符
    extraction_confidence: float = 0.0   # 提取置信度
    atomicity_score: float = 0.0        # 原子性评分
    verifiability: bool = False          # 可验证性


@dataclass  
class AtomicTask:
    """原子任务数据结构"""
    task_id: str                         # 任务ID
    question: str                        # 问题
    golden_answer: str                   # 标准答案
    content_identifier: str              # 内容标识符
    source_corpus: str                   # 源语料ID
    verification_score: float            # 验证分数
    required_tools: List[str]            # 所需工具
    difficulty_level: TaskDifficulty = TaskDifficulty.SIMPLE
    task_type: TaskType = TaskType.ATOMIC
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    atomicity_verified: bool = False     # 原子性已验证
    executability_verified: bool = False # 可执行性已验证


@dataclass
class SupersetInfo:
    """超集信息数据结构 - 用于深度扩展"""
    identifier: str                      # 超集标识符
    relation: str                        # 与子集的关系
    search_query: str                    # 搜索查询
    confidence: float                    # 置信度
    source_urls: List[str] = field(default_factory=list)  # 来源URL
    validation_passed: bool = False     # 验证是否通过


@dataclass
class ExtendedTask:
    """扩展任务数据结构 - 深度扩展结果"""
    task_id: str                         # 任务ID
    question: str                        # 扩展后问题
    golden_answer: str                   # 标准答案
    hop_level: int                       # 跳跃级别 (1,2,3...)
    source_atomic_task: str              # 源原子任务ID
    intermediate_steps: List[SupersetInfo] # 中间步骤
    expected_tools: List[str]            # 预期工具
    difficulty_level: TaskDifficulty = TaskDifficulty.MEDIUM
    task_type: TaskType = TaskType.DEPTH_EXTENDED
    complexity_score: float = 0.0       # 复杂度分数
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class CompositeTask:
    """复合任务数据结构 - 宽度扩展结果"""
    task_id: str                         # 任务ID
    question: str                        # 融合后问题
    golden_answers: List[str]            # 多个标准答案
    source_atomic_tasks: List[str]       # 源原子任务ID列表
    original_questions: List[str]        # 原始问题列表
    content_identifier: str              # 内容标识符
    expected_tools: List[str]            # 预期工具
    difficulty_level: TaskDifficulty = TaskDifficulty.COMPLEX
    task_type: TaskType = TaskType.WIDTH_EXTENDED
    merge_strategy: str = "width"        # 合并策略
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class VerificationResult:
    """验证结果数据结构"""
    task_id: str                         # 任务ID
    overall_score: float                 # 总体分数 (0-1)
    details: Dict[str, Any]              # 详细验证结果
    recommendation: str                  # 建议: accept/reject/modify
    suggested_improvements: List[str]    # 改进建议
    verification_dimensions: Dict[str, float] = field(default_factory=dict)  # 各维度分数
    verified_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def __post_init__(self):
        """初始化验证维度"""
        if not self.verification_dimensions:
            self.verification_dimensions = {
                "executability": 0.0,      # 可执行性
                "difficulty": 0.0,         # 难度适中性
                "answer_uniqueness": 0.0,  # 答案唯一性
                "tool_requirements": 0.0,  # 工具需求准确性
                "language_quality": 0.0,   # 语言质量
                "cognitive_complexity": 0.0, # 认知复杂度
                "atomicity": 0.0           # 原子性 (仅适用于原子任务)
            }


@dataclass
class GenerationMetrics:
    """生成指标数据结构"""
    session_id: str                      # 会话ID
    total_trajectories_processed: int = 0 # 处理的轨迹总数
    atomic_tasks_generated: int = 0     # 生成的原子任务数
    depth_extended_tasks: int = 0       # 深度扩展任务数
    width_extended_tasks: int = 0       # 宽度扩展任务数
    verification_passed: int = 0        # 验证通过数
    verification_failed: int = 0        # 验证失败数
    average_quality_score: float = 0.0  # 平均质量分数
    processing_time_seconds: float = 0.0 # 处理时间
    start_time: str = field(default_factory=lambda: datetime.now().isoformat())
    end_time: Optional[str] = None
    
    @property
    def total_tasks_generated(self) -> int:
        """总生成任务数"""
        return self.atomic_tasks_generated + self.depth_extended_tasks + self.width_extended_tasks
    
    @property
    def generation_efficiency(self) -> float:
        """生成效率: 任务数/轨迹数"""
        if self.total_trajectories_processed == 0:
            return 0.0
        return self.total_tasks_generated / self.total_trajectories_processed
    
    @property
    def verification_pass_rate(self) -> float:
        """验证通过率"""
        total_verified = self.verification_passed + self.verification_failed
        if total_verified == 0:
            return 0.0
        return self.verification_passed / total_verified


@dataclass
class PromptTemplate:
    """提示词模板数据结构"""
    template_id: str                     # 模板ID
    template_name: str                   # 模板名称
    template_content: str                # 模板内容
    template_type: str                   # 模板类型: atomic/depth/width/verification
    version: str = "1.0"                 # 版本号
    success_rate: float = 0.0           # 成功率
    usage_count: int = 0                # 使用次数
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_updated: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class FewShotExample:
    """少样本示例数据结构"""
    example_id: str                      # 示例ID
    task_type: str                       # 任务类型
    input_data: Dict[str, Any]          # 输入数据
    expected_output: Dict[str, Any]     # 期望输出
    quality_score: float                # 质量分数
    usage_count: int = 0                # 使用次数
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


# 类型别名定义
TaskUnion = Union[AtomicTask, ExtendedTask, CompositeTask]
"""任务联合类型"""

ProcessingResult = Dict[str, Any]
"""处理结果类型"""

QualityMetrics = Dict[str, float]
"""质量指标类型"""


class EnhancedSynthesisConfig:
    """增强合成配置类 - 现在使用YAML配置文件"""
    
    def __init__(self):
        """初始化配置，使用配置加载器"""
        from .config_loader import get_synthesis_config
        self._config_loader = get_synthesis_config()
    
    @property
    def ATOMIC_GENERATION_CONFIG(self) -> Dict[str, Any]:
        """原子任务生成配置"""
        return self._config_loader.get_atomic_generation_config()
    
    @property
    def DEPTH_EXTENSION_CONFIG(self) -> Dict[str, Any]:
        """深度扩展配置"""
        return self._config_loader.get_depth_extension_config()
    
    @property
    def WIDTH_EXTENSION_CONFIG(self) -> Dict[str, Any]:
        """宽度扩展配置"""
        return self._config_loader.get_width_extension_config()
    
    @property
    def VERIFICATION_CONFIG(self) -> Dict[str, Any]:
        """验证引擎配置"""
        config = self._config_loader.get_verification_config()
        # 确保dimension_weights键存在（兼容旧代码中的dimension_weight）
        if "dimension_weights" in config and "dimension_weight" not in config:
            config["dimension_weight"] = config["dimension_weights"]
        return config
    
    @property
    def ADAPTIVE_PROMPT_CONFIG(self) -> Dict[str, Any]:
        """自适应提示词配置"""
        return self._config_loader.get_adaptive_prompt_config()
    
    @property
    def REDIS_CONFIG(self) -> Dict[str, Any]:
        """Redis队列配置"""
        return self._config_loader.get_redis_config()
    
    def get_config_value(self, section: str, key: str, default=None):
        """获取指定配置值"""
        return self._config_loader.get_config_value(section, key, default)
    
    def update_config_value(self, section: str, key: str, value: Any) -> None:
        """动态更新配置值"""
        self._config_loader.update_config_value(section, key, value)
    
    def reload_config(self) -> None:
        """重新加载配置"""
        self._config_loader.reload_config()
    
    def print_current_config(self) -> None:
        """打印当前配置摘要"""
        self._config_loader.print_current_config()


def generate_task_id(task_type: TaskType, suffix: str = "") -> str:
    """生成任务ID"""
    timestamp = int(time.time())
    random_suffix = uuid.uuid4().hex[:8]
    if suffix:
        return f"{task_type.value}_{timestamp}_{suffix}_{random_suffix}"
    return f"{task_type.value}_{timestamp}_{random_suffix}"


def calculate_complexity_score(task: TaskUnion) -> float:
    """计算任务复杂度分数"""
    base_score = 0.0
    
    # 基于任务类型的基础分数
    if isinstance(task, AtomicTask):
        base_score = 1.0
    elif isinstance(task, ExtendedTask):
        base_score = 1.0 + (task.hop_level * 0.5)
    elif isinstance(task, CompositeTask):
        base_score = 1.0 + (len(task.source_atomic_tasks) * 0.3)
    
    # 基于工具需求的额外分数
    if hasattr(task, 'expected_tools'):
        tool_complexity = len(task.expected_tools) * 0.2
        base_score += tool_complexity
    elif hasattr(task, 'required_tools'):
        tool_complexity = len(task.required_tools) * 0.2
        base_score += tool_complexity
    
    # 标准化到0-1范围
    return min(base_score / 5.0, 1.0)


def get_task_difficulty_from_score(complexity_score: float) -> TaskDifficulty:
    """根据复杂度分数确定任务难度"""
    if complexity_score < 0.3:
        return TaskDifficulty.SIMPLE
    elif complexity_score < 0.7:
        return TaskDifficulty.MEDIUM
    else:
        return TaskDifficulty.COMPLEX


@dataclass
class TaskVerificationMetrics:
    """多维度任务验证指标"""
    task_id: str
    verification_dimensions: Dict[str, float] = field(default_factory=lambda: {
        "executability": 0.0,      # 可执行性
        "difficulty": 0.0,         # 难度适中性
        "answer_uniqueness": 0.0,  # 答案唯一性
        "tool_requirements": 0.0,  # 工具需求准确性
        "language_quality": 0.0,   # 语言质量
        "cognitive_complexity": 0.0, # 认知复杂度
        "atomicity": 0.0           # 原子性 (仅适用于原子任务)
    })
    
    dimension_weights: Dict[str, float] = field(default_factory=lambda: {
        "executability": 0.25,
        "difficulty": 0.15,
        "answer_uniqueness": 0.15,
        "tool_requirements": 0.15,
        "language_quality": 0.15,
        "cognitive_complexity": 0.10,
        "atomicity": 0.05
    })
    
    overall_score: float = 0.0
    verification_passed: bool = False
    detailed_feedback: List[str] = field(default_factory=list)
    verification_timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    overall_quality_threshold: float = 0.75
    
    def calculate_overall_score(self) -> float:
        """计算总体验证分数"""
        total_score = 0.0
        for dimension, score in self.verification_dimensions.items():
            weight = self.dimension_weights.get(dimension, 0.0)
            total_score += score * weight
        
        self.overall_score = total_score
        self.verification_passed = total_score >= self.overall_quality_threshold
        return total_score


@dataclass
class AdaptiveExtensionConfig:
    """自适应扩展配置"""
    # 深度扩展自适应参数
    depth_config: Dict[str, Any] = field(default_factory=lambda: {
        "max_hops": 3,
        "superset_confidence_threshold": 0.8,  # 根据成功率动态调整
        "max_search_results_per_query": 5,
        "quality_threshold_adaptive": True,     # 启用自适应质量阈值
        "success_rate_window": 100,            # 成功率统计窗口
        "min_threshold": 0.6,                  # 最小阈值
        "max_threshold": 0.95                  # 最大阈值
    })
    
    # 宽度扩展自适应参数  
    width_config: Dict[str, Any] = field(default_factory=lambda: {
        "semantic_similarity_threshold": 0.6,  # 根据分组效果动态调整
        "min_tasks_for_grouping": 2,
        "max_tasks_per_group": 3,
        "grouping_efficiency_target": 0.7,     # 目标分组效率
        "adjustment_sensitivity": 0.1           # 调整敏感度
    })
    
    # 批量处理优化配置
    batch_config: Dict[str, Any] = field(default_factory=lambda: {
        "batch_size": 10,                      # 批处理大小
        "max_concurrent_batches": 3,           # 最大并发批次
        "adaptive_batch_sizing": True,         # 自适应批大小
        "performance_threshold": 0.8           # 性能阈值
    })
    
    # 统计窗口
    success_history: List[bool] = field(default_factory=list)
    efficiency_history: List[Dict[str, float]] = field(default_factory=list)
    last_adjustment_time: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def adjust_thresholds(self, success_rate: float, efficiency_metrics: Dict[str, float]):
        """根据成功率和效率指标调整阈值"""
        if success_rate < 0.6:
            # 降低阈值，提高通过率
            self.depth_config["superset_confidence_threshold"] = max(
                self.depth_config["superset_confidence_threshold"] * 0.9,
                self.depth_config["min_threshold"]
            )
            self.width_config["semantic_similarity_threshold"] = max(
                self.width_config["semantic_similarity_threshold"] * 0.9,
                0.4
            )
        elif success_rate > 0.9:
            # 提高阈值，保证质量
            self.depth_config["superset_confidence_threshold"] = min(
                self.depth_config["superset_confidence_threshold"] * 1.1,
                self.depth_config["max_threshold"]
            )
            self.width_config["semantic_similarity_threshold"] = min(
                self.width_config["semantic_similarity_threshold"] * 1.1,
                0.85
            )
        
        # 根据分组效率调整批处理大小
        grouping_efficiency = efficiency_metrics.get("grouping_efficiency", 0.5)
        if self.batch_config["adaptive_batch_sizing"]:
            if grouping_efficiency < self.width_config["grouping_efficiency_target"]:
                self.batch_config["batch_size"] = max(self.batch_config["batch_size"] - 2, 5)
            elif grouping_efficiency > 0.9:
                self.batch_config["batch_size"] = min(self.batch_config["batch_size"] + 2, 20)
        
        self.last_adjustment_time = datetime.now().isoformat()
    
    def record_success(self, success: bool):
        """记录成功/失败"""
        self.success_history.append(success)
        # 保持窗口大小
        if len(self.success_history) > self.depth_config["success_rate_window"]:
            self.success_history.pop(0)
    
    def get_current_success_rate(self) -> float:
        """获取当前成功率"""
        if not self.success_history:
            return 0.5  # 默认值
        return sum(self.success_history) / len(self.success_history)