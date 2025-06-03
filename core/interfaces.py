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

class ActionType(Enum):
    CODE_GENERATION = "code_generation"
    CODE_EXECUTION = "code_execution"
    BROWSER_ACTION = "browser_action"
    TOOL_CALL = "tool_call"

class ErrorType(Enum):
    TIMEOUT = "timeout"
    NETWORK_ERROR = "network_error"
    COMPILE_ERROR = "compile_error"
    RUNTIME_ERROR = "runtime_error"
    BROWSER_ERROR = "browser_error"
    SYSTEM_ERROR = "system_error"
    TOOL_ERROR = "tool_error"

@dataclass
class TaskSpec:
    """标准任务规范"""
    task_id: str
    task_type: TaskType
    description: str
    expected_tools: List[str]
    constraints: Dict[str, Any] = field(default_factory=dict)
    max_steps: int = 10
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
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式，用于日志和序列化"""
        return {
            'step_id': self.step_id,
            'action_type': self.action_type.value if hasattr(self.action_type, 'value') else str(self.action_type),
            'tool_input': self.action_params,  # 使用tool_input保持一致性
            'tool_output': self.observation,   # 使用tool_output保持一致性
            'success': self.success,
            'thinking': self.thinking,
            'execution_code': self.execution_code,
            'error_type': self.error_type.value if self.error_type else None,
            'error_message': self.error_message,
            'timestamp': self.timestamp,
            'duration': self.duration
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
    
    def to_dict(self) -> Dict:
        return {
            'task_id': self.task_id,  # 将task_id放在第一行
            'task_name': self.task_name,
            'task_description': self.task_description,
            'runtime_id': self.runtime_id,
            'success': self.success,
            'steps': [
                {
                    'step_id': s.step_id,
                    'action_type': s.action_type.value,
                    'tool_input': s.action_params,
                    'tool_output': s.observation,
                    'thinking': s.thinking,
                    'execution_code': s.execution_code,
                    'success': s.success,
                    'error_type': s.error_type.value if s.error_type else None,
                    'error_message': s.error_message,
                    'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(s.timestamp)),
                    'duration': s.duration
                } for s in self.steps
            ],
            'final_result': self.final_result,
            'error_type': self.error_type.value if self.error_type else None,
            'error_message': self.error_message,
            'total_duration': self.total_duration,
            'metadata': self.metadata,
            'created_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(self.created_at))
        }
    
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