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
    error_type: Optional[ErrorType] = None
    error_message: Optional[str] = None
    timestamp: float = field(default_factory=time.time)
    duration: float = 0.0

@dataclass
class TrajectoryResult:
    """轨迹结果"""
    task_id: str
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
            'task_id': self.task_id,
            'runtime_id': self.runtime_id,
            'success': self.success,
            'steps': [
                {
                    'step_id': s.step_id,
                    'action_type': s.action_type.value,
                    'action_params': s.action_params,
                    'observation': s.observation,
                    'success': s.success,
                    'error_type': s.error_type.value if s.error_type else None,
                    'error_message': s.error_message,
                    'timestamp': s.timestamp,
                    'duration': s.duration
                } for s in self.steps
            ],
            'final_result': self.final_result,
            'error_type': self.error_type.value if self.error_type else None,
            'error_message': self.error_message,
            'total_duration': self.total_duration,
            'metadata': self.metadata,
            'created_at': self.created_at
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
            task_id=data['task_id'],
            runtime_id=data['runtime_id'],
            success=data['success'],
            steps=steps,
            final_result=data['final_result'],
            error_type=ErrorType(data['error_type']) if data.get('error_type') else None,
            error_message=data.get('error_message'),
            total_duration=data.get('total_duration', 0.0),
            metadata=data.get('metadata', {}),
            created_at=data.get('created_at', time.time())
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