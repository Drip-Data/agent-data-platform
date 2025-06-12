"""
工具库核心接口定义
定义统一的工具规范、适配器接口和数据模型
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Union, Protocol
from enum import Enum
import json
from datetime import datetime


class ToolType(Enum):
    """工具类型枚举"""
    FUNCTION = "function"      # 嵌入式Python函数工具
    MCP_SERVER = "mcp_server"  # MCP服务器工具


class ErrorType(Enum):
    """错误类型枚举"""
    UNKNOWN_ERROR = "UnknownError"
    TOOL_ERROR = "ToolError"
    NETWORK_ERROR = "NetworkError"
    INVALID_INPUT = "InvalidInput"
    SYSTEM_ERROR = "SystemError"
    TIMEOUT_ERROR = "TimeoutError"
    NAVIGATION_ERROR = "NavigationError" # 浏览器导航错误
    CODE_EXECUTION_ERROR = "CodeExecutionError" # 代码执行错误


@dataclass
class ExecutionResult:
    """工具执行结果"""
    success: bool
    data: Any = None
    error_type: Optional[Union[str, 'ErrorType']] = None
    error_message: Optional[str] = None
    execution_time: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        # 安全处理error_type，支持字符串或ErrorType枚举
        error_type_value = None
        if self.error_type:
            if hasattr(self.error_type, 'value'):
                error_type_value = self.error_type.value
            else:
                error_type_value = str(self.error_type)
        
        return {
            "success": self.success,
            "data": self.data,
            "error_type": error_type_value,
            "error_message": self.error_message,
            "execution_time": self.execution_time,
            "metadata": self.metadata
        }


@dataclass
class ToolCapability:
    """工具能力描述"""
    name: str                           # 能力名称
    description: str                    # 能力描述
    parameters: Dict[str, Any]          # 参数规范
    examples: List[Dict[str, Any]] = field(default_factory=list)  # 使用示例
    category: str = "general"           # 能力类别（为将来分类预留）
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "examples": self.examples,
            "category": self.category
        }


@dataclass
class ToolSpec:
    """工具规范基类"""
    tool_id: str                        # 工具唯一标识
    name: str                          # 工具名称
    description: str                   # 工具描述
    tool_type: ToolType                # 工具类型
    capabilities: List[ToolCapability] # 工具能力列表
    tags: List[str] = field(default_factory=list)  # 标签（为将来分类预留）
    version: str = "1.0.0"
    enabled: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_id": self.tool_id,
            "name": self.name,
            "description": self.description,
            "tool_type": self.tool_type.value,
            "capabilities": [cap.to_dict() for cap in self.capabilities],
            "tags": self.tags,
            "version": self.version,
            "enabled": self.enabled,
            "metadata": self.metadata
        }


@dataclass
class FunctionToolSpec(ToolSpec):
    """Function Tool规范"""
    module_path: str = ""               # Python模块路径
    class_name: str = ""                # 类名
    init_params: Dict[str, Any] = field(default_factory=dict)  # 初始化参数
    function_handler: Optional[Any] = None  # 直接的函数处理器（可选）
    
    def __post_init__(self):
        if self.tool_type != ToolType.FUNCTION:
            self.tool_type = ToolType.FUNCTION


@dataclass 
class MCPServerSpec(ToolSpec):
    """MCP Server规范"""
    server_config: Dict[str, Any] = field(default_factory=dict)   # 服务器配置
    endpoint: str = ""                      # 服务端点
    connection_params: Dict[str, Any] = field(default_factory=dict)  # 连接参数
    
    def __post_init__(self):
        if self.tool_type != ToolType.MCP_SERVER:
            self.tool_type = ToolType.MCP_SERVER


class BaseToolAdapter(ABC):
    """工具适配器基类"""
    
    @abstractmethod
    async def execute(self, tool_id: str, action: str, parameters: Dict[str, Any]) -> ExecutionResult:
        """执行工具操作"""
        pass
    
    @abstractmethod
    async def health_check(self) -> bool:
        """健康检查"""
        pass
    
    @abstractmethod
    async def cleanup(self):
        """清理资源"""
        pass


class ToolDiscoveryInterface(Protocol):
    """工具发现接口"""
    
    async def get_all_tools(self) -> List[ToolSpec]:
        """获取所有工具"""
        ...
    
    async def get_tool_by_id(self, tool_id: str) -> Optional[ToolSpec]:
        """获取指定工具"""
        ...
    
    async def get_tool_description_for_agent(self, tool_id: str) -> str:
        """获取Agent可理解的工具描述"""
        ...


class ToolExecutionInterface(Protocol):
    """工具执行接口"""
    
    async def execute_tool(self, tool_id: str, action: str, parameters: Dict[str, Any]) -> ExecutionResult:
        """执行工具"""
        ...


@dataclass
class RegistrationResult:
    """注册结果"""
    success: bool
    tool_id: Optional[str] = None
    error: Optional[str] = None
    deployment_info: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "tool_id": self.tool_id,
            "error": self.error,
            "deployment_info": self.deployment_info
        } 

@dataclass
class InstallationResult:
    """安装结果"""
    success: bool
    server_id: Optional[str] = None
    endpoint: Optional[str] = None
    error_message: Optional[str] = None
    container_id: Optional[str] = None
    port: Optional[int] = None 