"""
MCP服务容器数据模型
定义服务的标准化数据结构
"""

from typing import Dict, List, Any, Optional
from enum import Enum
from datetime import datetime

try:
    from dataclasses import dataclass, field
except ImportError:
    # Python 3.6 兼容性
    def dataclass(cls):
        return cls
    def field(default_factory=None, **kwargs):
        return default_factory() if default_factory else None


class ServiceType(Enum):
    """服务类型枚举"""
    BUILTIN = "builtin"          # 内置服务
    EXTERNAL = "external"        # 外部安装服务
    DOCKER = "docker"           # Docker容器服务
    LOCAL = "local"             # 本地文件服务


class ServiceStatus(Enum):
    """服务状态枚举"""
    STOPPED = "stopped"         # 已停止
    STARTING = "starting"       # 启动中
    RUNNING = "running"         # 运行中
    ERROR = "error"            # 错误状态
    UNKNOWN = "unknown"        # 未知状态


class InstallMethod(Enum):
    """安装方式枚举"""
    NONE = "none"              # 无需安装（内置）
    CONFIG_ONLY = "config_only" # 仅配置文件
    LIGHTWEIGHT = "lightweight" # 轻量级（仅下载必要文件）
    FULL_CLONE = "full_clone"   # 完整克隆
    DOCKER_PULL = "docker_pull" # Docker镜像拉取


@dataclass
class ServiceCapability:
    """服务能力定义"""
    name: str
    description: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    required_params: List[str] = field(default_factory=list)
    optional_params: List[str] = field(default_factory=list)
    examples: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class ServiceHealth:
    """服务健康状态"""
    is_healthy: bool = False
    last_check: Optional[datetime] = None
    error_message: Optional[str] = None
    response_time_ms: Optional[int] = None
    check_count: int = 0
    consecutive_failures: int = 0


@dataclass
class ServiceConfig:
    """服务配置"""
    # 基本信息
    service_id: str
    name: str
    description: str
    version: str = "1.0.0"
    
    # 服务类型和状态
    service_type: ServiceType = ServiceType.EXTERNAL
    status: ServiceStatus = ServiceStatus.STOPPED
    
    # 网络配置
    endpoint: Optional[str] = None
    host: str = "localhost"
    port: Optional[int] = None
    protocol: str = "websocket"  # websocket, http, tcp
    
    # 安装配置
    install_method: InstallMethod = InstallMethod.CONFIG_ONLY
    source_url: Optional[str] = None
    github_url: Optional[str] = None
    docker_image: Optional[str] = None
    local_path: Optional[str] = None
    
    # 启动配置
    entry_point: Optional[str] = None
    startup_command: Optional[List[str]] = None
    environment_vars: Dict[str, str] = field(default_factory=dict)
    working_directory: Optional[str] = None
    
    # 能力配置
    capabilities: List[ServiceCapability] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    
    # 运行时配置
    auto_start: bool = True
    auto_restart: bool = True
    max_restarts: int = 3
    restart_delay: int = 5
    health_check_interval: int = 30
    startup_timeout: int = 60
    
    # 元数据
    author: Optional[str] = None
    license: Optional[str] = None
    documentation_url: Optional[str] = None
    support_url: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    # 运行时状态
    process_id: Optional[int] = None
    container_id: Optional[str] = None
    actual_endpoint: Optional[str] = None
    health: ServiceHealth = field(default_factory=ServiceHealth)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "service_id": self.service_id,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "service_type": self.service_type.value,
            "status": self.status.value,
            "endpoint": self.actual_endpoint or self.endpoint,
            "capabilities": [
                {
                    "name": cap.name,
                    "description": cap.description,
                    "parameters": cap.parameters,
                    "required_params": cap.required_params,
                    "optional_params": cap.optional_params,
                    "examples": cap.examples
                }
                for cap in self.capabilities
            ],
            "tags": self.tags,
            "health": {
                "is_healthy": self.health.is_healthy,
                "last_check": self.health.last_check.isoformat() if self.health.last_check else None,
                "error_message": self.health.error_message,
                "response_time_ms": self.health.response_time_ms,
                "consecutive_failures": self.health.consecutive_failures
            },
            "metadata": {
                "author": self.author,
                "license": self.license,
                "documentation_url": self.documentation_url,
                "support_url": self.support_url,
                "created_at": self.created_at.isoformat() if self.created_at else None,
                "updated_at": self.updated_at.isoformat() if self.updated_at else None
            }
        }

    def to_llm_format(self) -> Dict[str, Any]:
        """转换为LLM友好的格式"""
        return {
            "id": self.service_id,
            "name": self.name,
            "description": self.description,
            "available": self.status == ServiceStatus.RUNNING and self.health.is_healthy,
            "capabilities": [
                {
                    "name": cap.name,
                    "description": cap.description,
                    "usage": f"调用 {cap.name}({', '.join(cap.required_params)})",
                    "examples": cap.examples[:2]  # 只显示前2个例子
                }
                for cap in self.capabilities
            ],
            "tags": self.tags,
            "response_time": f"{self.health.response_time_ms}ms" if self.health.response_time_ms else "未知"
        }


@dataclass 
class InstallationResult:
    """安装结果"""
    success: bool
    service_config: Optional[ServiceConfig] = None
    error_message: Optional[str] = None
    install_path: Optional[str] = None
    installation_time_seconds: Optional[float] = None
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ServiceSearchResult:
    """服务搜索结果"""
    query: str
    total_results: int
    available_services: List[ServiceConfig] = field(default_factory=list)
    suggested_installs: List[Dict[str, Any]] = field(default_factory=list)
    search_time_seconds: float = 0.0