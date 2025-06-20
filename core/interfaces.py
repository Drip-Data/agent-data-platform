from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict, field
from typing import List, Dict, Any, Optional
from enum import Enum
import time
import json
import uuid

class TaskType(Enum):
    CODE = "code"
    WEB = "web"
    REASONING = "reasoning"
    RESEARCH = "research"  # 添加研究任务类型
    # GENERAL = "general"  # 添加通用任务类型

class ActionType(Enum):
    CODE_GENERATION = "code_generation"
    CODE_EXECUTION = "code_execution"
    BROWSER_ACTION = "browser_action"
    TOOL_CALL = "tool_call"

class ErrorType(Enum):
    TIMEOUT = "timeout"
    NETWORK_ERROR = "network_error"
    RATE_LIMIT = "rate_limit"  # 添加速率限制错误
    COMPILE_ERROR = "compile_error"
    RUNTIME_ERROR = "runtime_error"
    BROWSER_ERROR = "browser_error"
    SYSTEM_ERROR = "system_error"
    TOOL_ERROR = "tool_error"
    EXECUTION_ERROR = "ExecutionError"
    EXECUTION_FAILED = "execution_failed"  # 添加缺失的枚举值

@dataclass
class TaskSpec:
    """标准任务规范"""
    task_id: str
    task_type: TaskType
    description: str
    context: Optional[str] = None # 新增：任务的上下文信息
    expected_tools: List[str] = field(default_factory=list)
    constraints: Dict[str, Any] = field(default_factory=dict)
    max_steps: int = 3
    timeout: int = 300
    priority: int = 1
    
    def __post_init__(self):
        if not self.task_id:
            self.task_id = str(uuid.uuid4())
        if isinstance(self.task_type, str):
            self.task_type = TaskType(self.task_type)
    
    def to_dict(self) -> Dict:
        data = asdict(self)
        data['task_type'] = self.task_type.value
        return data
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'TaskSpec':
        if isinstance(data.get('task_type'), str):
            data['task_type'] = TaskType(data['task_type'])
        return cls(**data)
    
    def json(self) -> str:
        return json.dumps(self.to_dict())

@dataclass
class ExecutionStep:
    """执行步骤"""
    step_id: int
    action_type: ActionType
    action_params: Dict[str, Any]
    observation: str
    success: bool
    thinking: Optional[str] = None  # LLM思考过程
    execution_code: Optional[str] = None  # 生成的工具调用代码
    error_type: Optional[ErrorType] = None
    error_message: Optional[str] = None
    timestamp: float = field(default_factory=time.time)
    duration: float = 0.0
    
    # 🔍 新增：LLM交互记录
    llm_interactions: List['LLMInteraction'] = field(default_factory=list)
    
    # 🔍 新增：事件因果关系和源归属
    event_source: str = "agent"  # "agent" | "user" | "system" | "environment"
    caused_by_step: Optional[int] = None
    triggering_event: Optional[str] = None
    
    # 🔍 新增：性能和资源使用
    resource_usage: Dict[str, Any] = field(default_factory=dict)
    
    # 🔍 新增：子事件（细粒度追踪）
    sub_events: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式，用于日志和序列化"""
        # 安全处理error_type，可能是字符串或ErrorType枚举
        error_type_value = None
        if self.error_type:
            if hasattr(self.error_type, 'value'):
                error_type_value = self.error_type.value
            else:
                error_type_value = str(self.error_type)
        
        return {
            'step_id': self.step_id,
            'action_type': self.action_type.value if hasattr(self.action_type, 'value') else str(self.action_type),
            'tool_input': self.action_params,  # 使用tool_input保持一致性
            'tool_output': self.observation,   # 使用tool_output保持一致性
            'success': self.success,
            'thinking': self.thinking,
            'execution_code': self.execution_code,
            'error_type': error_type_value,
            'error_message': self.error_message,
            'timestamp': self.timestamp,
            'duration': self.duration,
            # 🔍 LLM交互记录
            'llm_interactions': [interaction.to_dict() for interaction in self.llm_interactions],
            # 🔍 新增：事件因果关系和源归属
            'event_source': self.event_source,
            'caused_by_step': self.caused_by_step,
            'triggering_event': self.triggering_event,
            # 🔍 新增：性能和资源使用
            'resource_usage': self.resource_usage,
            # 🔍 新增：子事件（细粒度追踪）
            'sub_events': self.sub_events
        }

@dataclass
class TrajectoryResult:
    """轨迹结果"""
    task_name: str  # 原 task_id 值迁移
    task_id: str  # 新 UUID 格式 ID
    task_description: str
    runtime_id: str
    success: bool
    steps: List[ExecutionStep]
    final_result: str
    error_type: Optional[ErrorType] = None
    error_message: Optional[str] = None
    total_duration: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    
    # 🔍 工具使用跟踪
    available_tools: List[Dict[str, Any]] = field(default_factory=list)  # 任务开始时可用的MCP服务器
    used_tools: Dict[str, bool] = field(default_factory=dict)           # 实际使用的工具: {tool_key: success_status}
    
    # 🔍 新增：累积的LLM元数据
    llm_metrics: Dict[str, Any] = field(default_factory=dict)  # 累积的令牌使用、成本等
    
    # 🔍 新增：执行环境信息
    execution_environment: Dict[str, Any] = field(default_factory=dict)
    
    # 🔍 新增：错误处理统计
    error_handling: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        # 安全处理error_type
        error_type_value = None
        if self.error_type:
            if hasattr(self.error_type, 'value'):
                error_type_value = self.error_type.value
            else:
                error_type_value = str(self.error_type)
        
        return {
            'task_id': self.task_id,  # 将task_id放在第一行
            'task_name': self.task_name,
            'task_description': self.task_description,
            'runtime_id': self.runtime_id,
            'success': self.success,
            'steps': [step.to_dict() for step in self.steps], # 调用 ExecutionStep.to_dict()
            'final_result': self.final_result,
            'error_type': error_type_value,
            'error_message': self.error_message,
            'total_duration': self.total_duration,
            'metadata': self.metadata,
            'created_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(self.created_at)),
            # 🔍 工具使用跟踪
            'available_tools': self.available_tools,
            'used_tools': self.used_tools,
            # 🔍 新增：累积的LLM元数据
            'llm_metrics': self.llm_metrics,
            # 🔍 新增：执行环境信息
            'execution_environment': self.execution_environment,
            # 🔍 新增：错误处理统计
            'error_handling': self.error_handling
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'TrajectoryResult':
        """从字典创建TrajectoryResult实例"""
        # 处理steps
        steps = []
        for step_data in data.get('steps', []):
            step = ExecutionStep(
                step_id=step_data['step_id'],
                action_type=ActionType(step_data['action_type']),
                action_params=step_data['action_params'],
                observation=step_data['observation'],
                success=step_data['success'],
                error_type=ErrorType(step_data['error_type']) if step_data.get('error_type') else None,
                error_message=step_data.get('error_message'),
                timestamp=step_data.get('timestamp', time.time()),
                duration=step_data.get('duration', 0.0)
            )
            steps.append(step)
        
        return cls(
            task_name=data['task_name'],
            task_id=data['task_id'],
            task_description=data['task_description'],
            runtime_id=data['runtime_id'],
            success=data['success'],
            steps=steps,
            final_result=data['final_result'],
            error_type=ErrorType(data['error_type']) if data.get('error_type') else None,
            error_message=data.get('error_message'),
            total_duration=data.get('total_duration', 0.0),
            metadata=data.get('metadata', {}),
            created_at=data.get('created_at', time.time()),
            # 🔍 新增：工具使用跟踪
            available_tools=data.get('available_tools', []),
            used_tools=data.get('used_tools', {})
        )
    
    def json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)

class RuntimeInterface(ABC):
    """运行时标准接口"""
    
    @property
    @abstractmethod
    def runtime_id(self) -> str:
        pass
    
    @property
    @abstractmethod
    def capabilities(self) -> List[str]:
        pass
    
    @abstractmethod
    async def execute(self, task: TaskSpec) -> TrajectoryResult:
        pass
    
    @abstractmethod
    async def health_check(self) -> bool:
        pass
    
    @abstractmethod
    async def cleanup(self):
        pass

@dataclass
class LLMInteraction:
    """LLM交互记录 - 用于审计和分析"""
    interaction_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    provider: str = ""  # LLM提供商 (gemini, openai, etc.)
    model: str = ""     # 使用的模型名称
    context: str = ""   # 交互上下文 (工具选择、任务分析等)
    
    # 输入信息
    prompt: str = ""
    prompt_length: int = 0
    prompt_type: str = ""  # tool_selection, task_analysis, reasoning等
    input_metadata: Dict[str, Any] = field(default_factory=dict)
    
    # 输出信息
    response: str = ""
    response_length: int = 0
    response_time: float = 0.0  # 响应时间（秒）
    
    # 🔍 新增：详细的令牌使用统计
    token_usage: Dict[str, Any] = field(default_factory=dict)
    cost_info: Dict[str, Any] = field(default_factory=dict)
    
    # 解析结果
    parsed_data: Dict[str, Any] = field(default_factory=dict)
    parsing_success: bool = True
    parsing_errors: List[str] = field(default_factory=list)
    
    # 成功/失败状态
    success: bool = True
    error_message: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式，用于轨迹保存"""
        return {
            'interaction_id': self.interaction_id,
            'timestamp': self.timestamp,
            'provider': self.provider,
            'model': self.model,
            'context': self.context,
            'prompt_length': self.prompt_length,
            'prompt_type': self.prompt_type,
            'response_length': self.response_length,
            'response_time': self.response_time,
            'token_usage': self.token_usage,  # 新增
            'cost_info': self.cost_info,      # 新增
            'success': self.success,
            'error_message': self.error_message,
            'input_metadata': self.input_metadata,
            'parsed_data': self.parsed_data,
            'parsing_success': self.parsing_success,
            'parsing_errors': self.parsing_errors
        }
    
    @classmethod
    def create_tool_selection_interaction(cls, prompt: str, task_description: str, 
                                        available_tools_count: int) -> 'LLMInteraction':
        """创建工具选择交互记录"""
        return cls(
            context="tool_selection",
            prompt=prompt,
            prompt_length=len(prompt),
            prompt_type="tool_selection",
            input_metadata={
                "task_description": task_description[:100] + "..." if len(task_description) > 100 else task_description,
                "available_tools_count": available_tools_count
            }
        )