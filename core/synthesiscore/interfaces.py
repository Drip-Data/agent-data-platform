#!/usr/bin/env python3
"""
Synthesis Core - 接口定义
专注于 Synthesis 算法的核心数据结构
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any, Union
import uuid
from datetime import datetime


class TaskType(Enum):
    """任务类型"""
    TOOL_REQUIRED = "tool_required"      # 需要工具调用的任务
    REASONING_ONLY = "reasoning_only"    # 仅需推理的任务
    

class TaskComplexity(Enum):
    """任务复杂度"""
    ATOMIC = "atomic"        # 原子任务（单步）
    DEPTH = "depth"          # 深度扩展任务（多步依赖）
    WIDTH = "width"          # 宽度扩展任务（并行合并）


@dataclass
class SynthesisInput:
    """Synthesis 输入：iT"""
    input_id: str
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SynthesisContent:
    """Synthesis 内容：C"""
    content_id: str
    raw_content: str
    processed_content: str
    source_tool: Optional[str] = None


@dataclass
class SynthesisAnswer:
    """Synthesis 答案：a"""
    answer_id: str
    answer: str
    confidence: float = 1.0


@dataclass
class SynthesisRelation:
    """Synthesis 关系：R"""
    relation_id: str
    relation_type: str
    description: str
    parameters: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AtomicTask:
    """原子任务：q = f(iT, R) -> a"""
    task_id: str
    task_type: TaskType
    complexity: TaskComplexity
    
    # Synthesis 核心要素
    input_info: SynthesisInput
    answer: SynthesisAnswer  
    relation: SynthesisRelation
    
    # 任务描述
    question: str
    domain: str
    
    # 验证信息
    requires_tool: bool
    expected_tools: List[str] = field(default_factory=list)
    
    # 元数据
    created_at: datetime = field(default_factory=datetime.now)
    source_trajectory_id: Optional[str] = None
    
    @classmethod
    def create_atomic(cls, question: str, input_info: SynthesisInput, 
                     answer: SynthesisAnswer, relation: SynthesisRelation,
                     domain: str = "general", requires_tool: bool = True,
                     expected_tools: List[str] = None) -> "AtomicTask":
        """创建原子任务"""
        return cls(
            task_id=f"atomic_{uuid.uuid4().hex[:8]}",
            task_type=TaskType.TOOL_REQUIRED if requires_tool else TaskType.REASONING_ONLY,
            complexity=TaskComplexity.ATOMIC,
            input_info=input_info,
            answer=answer,
            relation=relation,
            question=question,
            domain=domain,
            requires_tool=requires_tool,
            expected_tools=expected_tools or []
        )


@dataclass
class DepthExtendedTask:
    """深度扩展任务"""
    task_id: str
    base_task: AtomicTask
    intermediate_task: AtomicTask
    
    # 超集信息
    superset_input: SynthesisInput
    superset_relation: SynthesisRelation
    
    # 组合任务
    combined_question: str
    combined_answer: str
    
    complexity: TaskComplexity = TaskComplexity.DEPTH
    created_at: datetime = field(default_factory=datetime.now)
    
    @classmethod
    def create_depth_extended(cls, base_task: AtomicTask, 
                            superset_input: SynthesisInput,
                            superset_relation: SynthesisRelation,
                            intermediate_question: str,
                            combined_question: str,
                            combined_answer: str) -> "DepthExtendedTask":
        """创建深度扩展任务"""
        # 创建中间任务
        intermediate_task = AtomicTask.create_atomic(
            question=intermediate_question,
            input_info=superset_input,
            answer=SynthesisAnswer(
                answer_id=f"intermediate_{uuid.uuid4().hex[:8]}",
                answer=base_task.input_info.content
            ),
            relation=superset_relation,
            domain=base_task.domain,
            requires_tool=True
        )
        
        return cls(
            task_id=f"depth_{uuid.uuid4().hex[:8]}",
            base_task=base_task,
            intermediate_task=intermediate_task,
            superset_input=superset_input,
            superset_relation=superset_relation,
            combined_question=combined_question,
            combined_answer=combined_answer
        )


@dataclass
class WidthExtendedTask:
    """宽度扩展任务"""
    task_id: str
    component_tasks: List[AtomicTask]
    
    # 合并信息
    merged_question: str
    merged_answer: str
    merge_strategy: str
    
    complexity: TaskComplexity = TaskComplexity.WIDTH
    created_at: datetime = field(default_factory=datetime.now)
    
    @classmethod
    def create_width_extended(cls, component_tasks: List[AtomicTask],
                            merged_question: str, merged_answer: str,
                            merge_strategy: str = "parallel") -> "WidthExtendedTask":
        """创建宽度扩展任务"""
        return cls(
            task_id=f"width_{uuid.uuid4().hex[:8]}",
            component_tasks=component_tasks,
            merged_question=merged_question,
            merged_answer=merged_answer,
            merge_strategy=merge_strategy
        )


@dataclass
class TaskValidationResult:
    """任务验证结果"""
    task_id: str
    is_valid: bool
    requires_tool: bool
    validation_score: float
    
    # 验证详情
    tool_necessity_check: bool  # 是否需要工具
    reasoning_sufficiency_check: bool  # 仅推理是否足够
    atomicity_check: bool  # 原子性检查
    
    # 错误信息
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    # 验证元数据
    validation_method: str = "llm_verification"
    validated_at: datetime = field(default_factory=datetime.now)
    
    @property
    def validation_reason(self) -> str:
        """获取验证失败原因的简要描述"""
        if self.is_valid:
            return "Task passed validation"
        
        reasons = []
        if not self.atomicity_check:
            reasons.append("不符合原子性要求")
        if not self.tool_necessity_check:
            reasons.append("不需要工具调用")
        if self.reasoning_sufficiency_check:
            reasons.append("仅通过推理即可解决")
            
        return "; ".join(reasons) if reasons else "Unknown validation failure"


@dataclass
class SynthesisResult:
    """合成结果"""
    session_id: str
    
    # 生成的任务
    atomic_tasks: List[AtomicTask] = field(default_factory=list)
    depth_extended_tasks: List[DepthExtendedTask] = field(default_factory=list)
    width_extended_tasks: List[WidthExtendedTask] = field(default_factory=list)
    
    # 验证结果
    validation_results: List[TaskValidationResult] = field(default_factory=list)
    
    # 统计信息
    total_tasks_generated: int = 0
    valid_tasks_count: int = 0
    tool_required_count: int = 0
    reasoning_only_count: int = 0
    
    # 🆕 真实成本分析信息
    synthesis_cost_analysis: Optional[Dict[str, Any]] = None
    
    # 元数据
    created_at: datetime = field(default_factory=datetime.now)
    source_trajectories: List[str] = field(default_factory=list)


# 类型别名
TaskUnion = Union[AtomicTask, DepthExtendedTask, WidthExtendedTask]


def generate_task_id(task_type: str) -> str:
    """生成任务ID"""
    return f"{task_type}_{uuid.uuid4().hex[:8]}"


def get_task_type_from_complexity(complexity: TaskComplexity) -> str:
    """从复杂度获取任务类型"""
    mapping = {
        TaskComplexity.ATOMIC: "atomic",
        TaskComplexity.DEPTH: "depth_extended", 
        TaskComplexity.WIDTH: "width_extended"
    }
    return mapping.get(complexity, "unknown")


# === 向后兼容的TaskCraft名称 ===
# 为了保持向后兼容性，保留旧的TaskCraft命名别名
TaskCraftInput = SynthesisInput
TaskCraftContent = SynthesisContent
TaskCraftAnswer = SynthesisAnswer
TaskCraftRelation = SynthesisRelation