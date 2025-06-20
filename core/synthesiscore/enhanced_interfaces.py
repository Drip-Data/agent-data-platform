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
    """增强合成配置类"""
    
    # 原子任务生成配置
    ATOMIC_GENERATION_CONFIG = {
        "max_conclusions_per_corpus": 20,        # 每个语料最大结论数
        "max_candidate_atomic_tasks": 10,        # 最大候选原子任务数
        "conclusion_extraction_confidence": 0.7, # 结论提取置信度阈值
        "atomicity_verification_threshold": 0.8, # 原子性验证阈值
        "parallel_workers": 4                    # 并行工作线程数
    }
    
    # 深度扩展配置
    DEPTH_EXTENSION_CONFIG = {
        "max_hops": 3,                          # 最大跳跃数
        "max_backward_search_attempts": 5,      # 最大反向搜索尝试次数
        "superset_validation_threshold": 0.8,   # 超集验证阈值
        "intermediate_task_quality_threshold": 0.7, # 中间任务质量阈值
        "max_search_results_per_query": 10     # 每个查询最大搜索结果数
    }
    
    # 宽度扩展配置
    WIDTH_EXTENSION_CONFIG = {
        "min_tasks_for_grouping": 2,            # 分组最小任务数
        "max_tasks_per_group": 3,               # 每组最大任务数
        "semantic_similarity_threshold": 0.6,   # 语义相似度阈值
        "decomposition_validation_threshold": 0.8, # 分解验证阈值
        "complexity_validation_threshold": 0.7  # 复杂性验证阈值
    }
    
    # 验证引擎配置
    VERIFICATION_CONFIG = {
        "overall_quality_threshold": 0.75,      # 总体质量阈值
        "dimension_weight": {                   # 各维度权重
            "executability": 0.25,
            "difficulty": 0.15,
            "answer_uniqueness": 0.15,
            "tool_requirements": 0.15,
            "language_quality": 0.15,
            "cognitive_complexity": 0.10,
            "atomicity": 0.05
        },
        "execution_timeout_seconds": 60,        # 执行超时时间
        "max_verification_retries": 3          # 最大验证重试次数
    }
    
    # 自适应提示词配置
    ADAPTIVE_PROMPT_CONFIG = {
        "prompt_optimization_threshold": 0.1,   # 提示词优化阈值 (10%改进)
        "few_shot_examples_per_type": 20,      # 每种类型的少样本示例数
        "ab_test_sample_size": 50,             # A/B测试样本大小
        "success_rate_window_size": 100,       # 成功率计算窗口大小
        "prompt_version_retention": 5          # 保留的提示词版本数
    }
    
    # Redis队列配置
    REDIS_CONFIG = {
        "streams": {
            "corpus_queue": "synthesis:v2:corpus_queue",
            "atomic_tasks": "synthesis:v2:atomic_tasks",
            "extended_tasks": "synthesis:v2:extended_tasks", 
            "verification_queue": "synthesis:v2:verification_queue",
            "training_data": "synthesis:v2:training_data",
            "quality_reports": "synthesis:v2:quality_reports"
        },
        "keys": {
            "config": "synthesis:v2:config",
            "prompt_versions": "synthesis:v2:prompt_versions",
            "success_rates": "synthesis:v2:success_rates",
            "few_shot_examples": "synthesis:v2:few_shot_examples",
            "generation_metrics": "synthesis:v2:generation_metrics"
        },
        "batch_size": 10,                       # 批处理大小
        "processing_timeout": 300               # 处理超时时间 (秒)
    }


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