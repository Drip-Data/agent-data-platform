from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict, field
from typing import List, Dict, Any, Optional, Union
from enum import Enum
import time
import json
import uuid


class TaskExecutionConstants:
    """🔧 根本修复：任务执行相关常量 - 消除硬编码"""
    
    # 状态消息常量
    NO_ACTION_PERFORMED = "No action was performed or no result was returned."
    TASK_COMPLETED_NO_ANSWER = "任务执行完成，但未找到明确的最终答案"
    EXECUTION_FAILED = "执行失败"
    TOOL_EXECUTION_FAILED = "工具执行失败"
    THOUGHT_ONLY_RESPONSE = "思考过程"
    EXECUTION_RESULT_PREFIX = "执行结果"
    
    # 成功指示词 - 用于智能判定
    SUCCESS_INDICATORS = [
        "任务已", "任务完成", "已完成", "成功完成", "完成", 
        "successful", "completed", "done", "结果正确", "计算正确", 
        "执行成功", "验证通过", "满足要求", "答案是", "结果为"
    ]
    
    # 失败指示词 - 用于智能判定  
    FAILURE_INDICATORS = [
        "失败", "错误", "未完成", "incomplete", "failed", 
        "error", "问题", "无法", "timeout", "超时", "exception",
        "traceback", "cannot", "unable to", "failed to execute"
    ]
    
    # XML标签常量
    XML_TAGS = {
        'RESULT': 'result',
        'ANSWER': 'answer', 
        'THINK': 'think',
        'EXECUTE_TOOLS': 'execute_tools',
        'OBSERVATION': 'observation',
        'CONCLUSION': 'conclusion'
    }
    
    # 🔧 新增：工具结果格式化常量 - 增强搜索结果显示
    TOOL_RESULT_LIMITS = {
        'MAX_SEARCH_RESULTS': 8,           # 搜索结果最大显示数量（增加到8个）
        'MAX_FILE_RESULTS': 10,            # 文件搜索结果最大显示数量
        'MAX_SNIPPET_LENGTH': 500,         # 文本片段最大长度（增加到500）
        'MAX_CONTENT_LENGTH': 2000,        # 内容最大显示长度（增加到2000）
        'MAX_BROWSER_CONTENT': 3000,       # 浏览器内容专用限制（新增）
        'MIN_MEANINGFUL_CONTENT': 10       # 有意义内容最小长度
    }
    
    # 🔧 新增：LLM响应处理常量 - 解决输出截断问题
    RESPONSE_HANDLING = {
        'DEFAULT_MAX_TOKENS': 32768,       # 默认最大token数 
        'COMPLEX_TASK_MAX_TOKENS': 65536,  # 复杂任务最大token数
        'RETRY_MAX_TOKENS': 98304,         # 重试时最大token数 (3x default)
        'MIN_COMPLETE_RESPONSE': 100,      # 最小完整响应长度
        'TRUNCATION_INDICATORS': [         # 截断指示符
            'test_multiply',
            '```python\ndef',
            '<answer',
            'Final Answer',
            'def test_'
        ],
        'COMPLEX_TASK_KEYWORDS': [         # 需要更高token限制的任务类型
            'automated_testing_pipeline',
            'complex_analysis',
            'code_generation', 
            'detailed_report',
            'comprehensive_solution'
        ]
    }
    
    # 工具结果格式化前缀
    TOOL_FORMAT_PREFIXES = {
        'SEARCH_QUERY': '搜索查询',
        'SEARCH_SUMMARY': '搜索摘要', 
        'SEARCH_RESULTS': '找到 {} 个相关结果',
        'FILE_SEARCH': '文件搜索',
        'FILE_RESULTS': '找到 {} 个匹配文件',
        'BROWSER_ACTION': '浏览器操作',
        'PAGE_URL': '页面地址',
        'PAGE_CONTENT': '页面内容',
        'OPERATION_RESULT': '操作结果',
        'ERROR_INFO': '错误信息',
        'CODE_EXECUTION': '代码执行完成，无输出内容'
    }
    
    # 🔧 Priority 4 新增：多工具协同常量
    MULTI_TOOL_COORDINATION = {
        'TOOL_DEPENDENCIES': {
            'search_then_analyze': ['deepsearch', 'microsandbox'],
            'browse_then_extract': ['browser_use', 'search_tool'],
            'code_with_search': ['microsandbox', 'deepsearch']
        },
        'COORDINATION_TIMEOUTS': {
            'sequential_execution': 300,  # 5分钟
            'parallel_analysis': 180,     # 3分钟
            'data_integration': 120       # 2分钟
        },
        'RESULT_INTEGRATION': {
            'min_meaningful_tools': 2,
            'max_tool_failures': 1,
            'quality_threshold': 0.7
        }
    }
    
    # 错误类型消息模板
    ERROR_TEMPLATES = {
        'network_error': "网络连接失败: {details}",
        'timeout_error': "操作超时: {timeout}秒",
        'parameter_error': "参数错误: {parameter_name}",
        'tool_not_found': "工具未找到: {tool_id}",
        'execution_timeout': "执行超时: {duration}秒",
        'invalid_response': "无效的响应格式: {format_error}"
    }


class ErrorMessageConstants:
    """🔧 根本修复：错误消息常量 - 提供结构化错误处理"""
    
    # 网络相关错误
    NETWORK_CONNECTION_FAILED = "网络连接失败"
    NETWORK_TIMEOUT = "网络请求超时"
    NETWORK_UNREACHABLE = "网络不可达"
    
    # 工具执行错误
    TOOL_NOT_AVAILABLE = "工具不可用"
    TOOL_EXECUTION_TIMEOUT = "工具执行超时"
    TOOL_PARAMETER_ERROR = "工具参数错误"
    TOOL_RESPONSE_ERROR = "工具响应错误"
    
    # 系统错误
    SYSTEM_RESOURCE_EXHAUSTED = "系统资源耗尽"
    SYSTEM_CONFIGURATION_ERROR = "系统配置错误"
    SYSTEM_SERVICE_UNAVAILABLE = "系统服务不可用"
    
    # LLM相关错误
    LLM_RESPONSE_INVALID = "LLM响应格式无效"
    LLM_TOKEN_LIMIT_EXCEEDED = "LLM令牌限制超出"
    LLM_API_ERROR = "LLM API错误"
    
    @classmethod
    def format_error_message(cls, error_type: str, **kwargs) -> str:
        """格式化错误消息"""
        template = TaskExecutionConstants.ERROR_TEMPLATES.get(
            error_type, 
            f"未知错误类型: {error_type}"
        )
        try:
            return template.format(**kwargs)
        except KeyError as e:
            return f"{error_type}: 消息格式化失败，缺少参数 {e}"

class TaskType(Enum):
    CODE = "code"
    WEB = "web"
    REASONING = "reasoning"
    RESEARCH = "research"  # 添加研究任务类型
    # GENERAL = "general"  # 添加通用任务类型

class ActionType(Enum):
    # 🔧 优化：扩展的语义化动作类型
    CODE_GENERATION = "code_generation"
    CODE_EXECUTION = "code_execution"
    BROWSER_ACTION = "browser_action"
    TOOL_CALL = "tool_call"
    
    # 新增：细分的动作类型
    RESEARCH_QUERY = "research_query"         # 研究查询
    DATA_RETRIEVAL = "data_retrieval"         # 数据检索
    FILE_OPERATION = "file_operation"         # 文件操作
    NETWORK_REQUEST = "network_request"       # 网络请求
    VALIDATION_CHECK = "validation_check"     # 验证检查
    ERROR_RECOVERY = "error_recovery"         # 错误恢复
    TASK_PLANNING = "task_planning"           # 任务规划
    RESULT_SYNTHESIS = "result_synthesis"     # 结果综合
    USER_INTERACTION = "user_interaction"     # 用户交互
    SYSTEM_CONFIG = "system_config"           # 系统配置
    RESOURCE_MANAGEMENT = "resource_management" # 资源管理
    KNOWLEDGE_EXTRACTION = "knowledge_extraction" # 知识提取
    ANALYSIS_PROCESSING = "analysis_processing"   # 分析处理

class ActionTypeClassifier:
    """🔧 优化：动作类型分类器
    
    根据工具和动作自动确定合适的语义化动作类型
    """
    
    @staticmethod
    def classify_action(tool_id: str, action: str, parameters: Dict[str, Any] = None) -> ActionType:
        """根据工具ID和动作自动分类动作类型"""
        tool_id = tool_id.lower()
        action = action.lower()
        
        # 研究和搜索相关
        if any(keyword in tool_id for keyword in ['search', 'research', 'deepsearch']):
            if 'comprehensive' in action or 'detailed' in action:
                return ActionType.KNOWLEDGE_EXTRACTION
            else:
                return ActionType.RESEARCH_QUERY
        
        # 代码相关
        if any(keyword in tool_id for keyword in ['python', 'executor', 'code', 'microsandbox']):
            if 'execute' in action:
                return ActionType.CODE_EXECUTION
            else:
                return ActionType.CODE_GENERATION
        
        # 浏览器相关
        if any(keyword in tool_id for keyword in ['browser', 'navigator', 'web']):
            return ActionType.BROWSER_ACTION
        
        # 文件相关
        if any(keyword in tool_id for keyword in ['file', 'document', 'storage']):
            return ActionType.FILE_OPERATION
        
        # 网络相关
        if any(keyword in tool_id for keyword in ['http', 'api', 'request', 'fetch']):
            return ActionType.NETWORK_REQUEST
        
        # 数据库相关
        if any(keyword in tool_id for keyword in ['database', 'db', 'sql']):
            return ActionType.DATA_RETRIEVAL
        
        # 验证和检查相关
        if any(keyword in action for keyword in ['validate', 'check', 'verify']):
            return ActionType.VALIDATION_CHECK
        
        # 错误恢复相关
        if any(keyword in action for keyword in ['retry', 'recover', 'fix', 'repair']):
            return ActionType.ERROR_RECOVERY
        
        # 规划相关
        if any(keyword in action for keyword in ['plan', 'strategy', 'organize']):
            return ActionType.TASK_PLANNING
        
        # 分析相关
        if any(keyword in action for keyword in ['analyze', 'process', 'compute', 'calculate']):
            return ActionType.ANALYSIS_PROCESSING
        
        # 综合相关
        if any(keyword in action for keyword in ['synthesize', 'merge', 'combine', 'summary']):
            return ActionType.RESULT_SYNTHESIS
        
        # 默认返回工具调用
        return ActionType.TOOL_CALL
    
    @staticmethod
    def get_action_description(action_type: ActionType) -> str:
        """获取动作类型的中文描述"""
        descriptions = {
            ActionType.CODE_GENERATION: "代码生成",
            ActionType.CODE_EXECUTION: "代码执行",
            ActionType.BROWSER_ACTION: "浏览器操作",
            ActionType.TOOL_CALL: "工具调用",
            ActionType.RESEARCH_QUERY: "研究查询",
            ActionType.DATA_RETRIEVAL: "数据检索",
            ActionType.FILE_OPERATION: "文件操作",
            ActionType.NETWORK_REQUEST: "网络请求",
            ActionType.VALIDATION_CHECK: "验证检查",
            ActionType.ERROR_RECOVERY: "错误恢复",
            ActionType.TASK_PLANNING: "任务规划",
            ActionType.RESULT_SYNTHESIS: "结果综合",
            ActionType.USER_INTERACTION: "用户交互",
            ActionType.SYSTEM_CONFIG: "系统配置",
            ActionType.RESOURCE_MANAGEMENT: "资源管理",
            ActionType.KNOWLEDGE_EXTRACTION: "知识提取",
            ActionType.ANALYSIS_PROCESSING: "分析处理"
        }
        return descriptions.get(action_type, action_type.value)

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
    PARAMETER_ERROR = "parameter_error"
    CONFIGURATION_ERROR = "configuration_error"
    API_ERROR = "api_error"
    INTERNAL_ERROR = "internal_error"
    VALIDATION_ERROR = "validation_error"

class ErrorSeverity(Enum):
    """错误严重性级别"""
    LOW = "low"           # 轻微错误，不影响任务继续
    MEDIUM = "medium"     # 中等错误，需要恢复措施
    HIGH = "high"         # 严重错误，可能导致任务失败
    CRITICAL = "critical" # 致命错误，必须终止任务

class ErrorCategory(Enum):
    """错误分类"""
    USER_INPUT = "user_input"           # 用户输入相关错误
    TOOL_OPERATION = "tool_operation"   # 工具操作错误
    NETWORK_ISSUE = "network_issue"     # 网络问题
    RESOURCE_LIMIT = "resource_limit"   # 资源限制
    SYSTEM_FAILURE = "system_failure"   # 系统故障
    CONFIGURATION = "configuration"     # 配置问题
    DATA_PROCESSING = "data_processing" # 数据处理错误

@dataclass
class StructuredError:
    """🔧 优化：结构化错误对象
    
    提供更详细的错误信息，便于轨迹分析和错误恢复
    """
    error_type: ErrorType
    severity: ErrorSeverity
    category: ErrorCategory
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    suggested_actions: List[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)
    context: Dict[str, Any] = field(default_factory=dict)
    retry_count: int = 0
    is_recoverable: bool = True
    error_code: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "error_type": self.error_type.value,
            "severity": self.severity.value,
            "category": self.category.value,
            "message": self.message,
            "details": self.details,
            "suggested_actions": self.suggested_actions,
            "timestamp": self.timestamp,
            "context": self.context,
            "retry_count": self.retry_count,
            "is_recoverable": self.is_recoverable,
            "error_code": self.error_code
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'StructuredError':
        """从字典创建结构化错误对象"""
        return cls(
            error_type=ErrorType(data["error_type"]),
            severity=ErrorSeverity(data["severity"]),
            category=ErrorCategory(data["category"]),
            message=data["message"],
            details=data.get("details", {}),
            suggested_actions=data.get("suggested_actions", []),
            timestamp=data.get("timestamp", time.time()),
            context=data.get("context", {}),
            retry_count=data.get("retry_count", 0),
            is_recoverable=data.get("is_recoverable", True),
            error_code=data.get("error_code")
        )
    
    @classmethod
    def create_parameter_error(cls, message: str, parameter_name: str = None, 
                             expected_type: str = None, received_value: Any = None) -> 'StructuredError':
        """创建参数错误"""
        details = {}
        if parameter_name:
            details["parameter_name"] = parameter_name
        if expected_type:
            details["expected_type"] = expected_type
        if received_value is not None:
            details["received_value"] = str(received_value)[:100]  # 限制长度
        
        return cls(
            error_type=ErrorType.PARAMETER_ERROR,
            severity=ErrorSeverity.MEDIUM,
            category=ErrorCategory.USER_INPUT,
            message=message,
            details=details,
            suggested_actions=[
                "检查参数名称和类型",
                "参考API文档确认正确的参数格式"
            ]
        )
    
    @classmethod
    def create_network_error(cls, message: str, url: str = None, 
                           status_code: int = None, timeout: float = None) -> 'StructuredError':
        """创建网络错误"""
        details = {}
        if url:
            details["url"] = url
        if status_code:
            details["status_code"] = status_code
        if timeout:
            details["timeout"] = timeout
        
        return cls(
            error_type=ErrorType.NETWORK_ERROR,
            severity=ErrorSeverity.HIGH,
            category=ErrorCategory.NETWORK_ISSUE,
            message=message,
            details=details,
            suggested_actions=[
                "检查网络连接",
                "验证目标服务是否可用",
                "考虑增加超时时间或重试"
            ]
        )
    
    @classmethod
    def create_tool_error(cls, message: str, tool_id: str = None, 
                        action: str = None, parameters: Dict[str, Any] = None) -> 'StructuredError':
        """创建工具错误"""
        details = {}
        if tool_id:
            details["tool_id"] = tool_id
        if action:
            details["action"] = action
        if parameters:
            # 过滤敏感信息
            safe_params = {k: "***" if "key" in k.lower() or "token" in k.lower() 
                          else str(v)[:100] for k, v in parameters.items()}
            details["parameters"] = safe_params
        
        return cls(
            error_type=ErrorType.TOOL_ERROR,
            severity=ErrorSeverity.MEDIUM,
            category=ErrorCategory.TOOL_OPERATION,
            message=message,
            details=details,
            suggested_actions=[
                "验证工具配置和可用性",
                "检查参数格式和值",
                "尝试使用替代工具"
            ]
        )

@dataclass
class TaskSpec:
    """标准任务规范"""
    task_id: str
    task_type: TaskType
    description: str
    context: Optional[str] = None # 新增：任务的上下文信息
    expected_tools: List[str] = field(default_factory=list)
    constraints: Dict[str, Any] = field(default_factory=dict)
    max_steps: int = 25 #最多执行25步
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
    
    # 🔧 优化：结构化错误对象支持
    structured_error: Optional[StructuredError] = None
    
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
            # 🔧 优化：结构化错误对象
            'structured_error': self.structured_error.to_dict() if self.structured_error else None,
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
    
    # 🔧 优化：结构化错误对象支持
    structured_error: Optional[StructuredError] = None
    
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
            # 🔧 优化：结构化错误对象
            'structured_error': self.structured_error.to_dict() if self.structured_error else None,
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