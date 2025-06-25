"""
配置数据模式定义
使用Pydantic提供类型安全的配置验证
"""

from typing import Optional, List, Dict, Any, Union
from enum import Enum

try:
    # Try Pydantic v2 first
    from pydantic import BaseModel, Field, field_validator, model_validator
    PYDANTIC_V2 = True
except ImportError:
    try:
        # Fall back to Pydantic v1
        from pydantic import BaseModel, Field, validator, root_validator
        PYDANTIC_V2 = False
    except ImportError:
        # No pydantic available, create basic stubs
        class BaseModel(dict):
            def __init__(self, **data):
                super().__init__(data)
        
        def Field(default=None, **kwargs):
            return default
            
        def validator(field_name, **kwargs):
            def decorator(func):
                return func
            return decorator
            
        def root_validator(**kwargs):
            def decorator(func):
                return func
            return decorator
            
        PYDANTIC_V2 = False


class ProjectTypeEnum(str, Enum):
    """项目类型枚举"""
    PYTHON = "python"
    NODEJS = "nodejs"
    TYPESCRIPT = "typescript"
    RUST = "rust"
    GO = "go"


class StartupCheckTypeEnum(str, Enum):
    """启动检查类型枚举"""
    PORT = "port"
    LOG = "log"
    HTTP = "http"
    WEBSOCKET = "websocket"


class StartupCheckSchema(BaseModel):
    """启动检查配置"""
    type: StartupCheckTypeEnum = Field(..., description="检查类型")
    port: Optional[int] = Field(None, description="端口号")
    pattern: Optional[str] = Field(None, description="日志模式")
    url: Optional[str] = Field(None, description="HTTP检查URL")
    timeout: int = Field(10, description="超时时间（秒）", ge=1, le=300)
    
    if PYDANTIC_V2:
        @model_validator(mode='before')
        @classmethod
        def validate_check_config(cls, values):
            """验证检查配置的完整性"""
            if isinstance(values, dict):
                check_type = values.get('type')
                
                if check_type == StartupCheckTypeEnum.PORT:
                    if not values.get('port'):
                        raise ValueError("端口检查需要指定port参数")
                elif check_type == StartupCheckTypeEnum.LOG:
                    if not values.get('pattern'):
                        raise ValueError("日志检查需要指定pattern参数")
                elif check_type == StartupCheckTypeEnum.HTTP:
                    if not values.get('url'):
                        raise ValueError("HTTP检查需要指定url参数")
            
            return values
    else:
        @root_validator(skip_on_failure=True)
        def validate_check_config(cls, values):
            """验证检查配置的完整性"""
            check_type = values.get('type')
            
            if check_type == StartupCheckTypeEnum.PORT:
                if not values.get('port'):
                    raise ValueError("端口检查需要指定port参数")
            elif check_type == StartupCheckTypeEnum.LOG:
                if not values.get('pattern'):
                    raise ValueError("日志检查需要指定pattern参数")
            elif check_type == StartupCheckTypeEnum.HTTP:
                if not values.get('url'):
                    raise ValueError("HTTP检查需要指定url参数")
            
            return values


class DependencySchema(BaseModel):
    """依赖配置"""
    system: Optional[List[str]] = Field(None, description="系统依赖")
    python: Optional[List[str]] = Field(None, description="Python依赖")
    nodejs: Optional[List[str]] = Field(None, description="Node.js依赖")
    custom: Optional[List[str]] = Field(None, description="自定义安装命令")


class ToolConfigSchema(BaseModel):
    """MCP工具配置模式"""
    id: str = Field(..., description="工具唯一标识符", min_length=1, max_length=100)
    name: str = Field(..., description="工具名称", min_length=1, max_length=200)
    description: str = Field(..., description="工具描述", min_length=1)
    github_url: str = Field(..., description="GitHub仓库URL")
    project_type: ProjectTypeEnum = Field(..., description="项目类型")
    entry_point: Optional[str] = Field(None, description="入口点文件")
    version: Optional[str] = Field(None, description="版本号")
    
    # 启动配置
    startup_check: Optional[StartupCheckSchema] = Field(None, description="启动检查配置")
    args: Optional[List[str]] = Field(None, description="启动参数")
    env: Optional[Dict[str, str]] = Field(None, description="环境变量")
    
    # 依赖配置
    dependencies: Optional[DependencySchema] = Field(None, description="依赖配置")
    install_commands: Optional[List[str]] = Field(None, description="自定义安装命令")
    
    # 元数据
    tags: Optional[List[str]] = Field(None, description="标签")
    author: Optional[str] = Field(None, description="作者")
    popularity_score: Optional[int] = Field(None, description="流行度评分", ge=0, le=100)
    security_score: Optional[int] = Field(None, description="安全评分", ge=0, le=100)
    
    # 兼容性配置
    min_python_version: Optional[str] = Field(None, description="最低Python版本")
    min_node_version: Optional[str] = Field(None, description="最低Node.js版本")
    os_support: Optional[List[str]] = Field(None, description="支持的操作系统")
    
    if PYDANTIC_V2:
        @field_validator('github_url')
        @classmethod
        def validate_github_url(cls, v):
            """验证GitHub URL格式"""
            if not v.startswith(('https://github.com/', 'git@github.com:')):
                raise ValueError('必须是有效的GitHub URL')
            return v
        
        @field_validator('tags')
        @classmethod
        def validate_tags(cls, v):
            """验证标签"""
            if v and len(v) > 10:
                raise ValueError('标签数量不能超过10个')
            return v
        
        @model_validator(mode='before')
        @classmethod
        def validate_project_dependencies(cls, values):
            """验证项目类型与依赖的一致性"""
            if isinstance(values, dict):
                project_type = values.get('project_type')
                dependencies = values.get('dependencies')
                
                if dependencies and project_type:
                    if hasattr(dependencies, 'nodejs') and project_type == ProjectTypeEnum.PYTHON and dependencies.nodejs:
                        raise ValueError('Python项目不应该有Node.js依赖')
                    elif hasattr(dependencies, 'python') and project_type == ProjectTypeEnum.NODEJS and dependencies.python:
                        raise ValueError('Node.js项目不应该有Python依赖')
            
            return values
    else:
        @validator('github_url')
        def validate_github_url(cls, v):
            """验证GitHub URL格式"""
            if not v.startswith(('https://github.com/', 'git@github.com:')):
                raise ValueError('必须是有效的GitHub URL')
            return v
        
        @validator('tags')
        def validate_tags(cls, v):
            """验证标签"""
            if v and len(v) > 10:
                raise ValueError('标签数量不能超过10个')
            return v
        
        @root_validator(skip_on_failure=True)
        def validate_project_dependencies(cls, values):
            """验证项目类型与依赖的一致性"""
            project_type = values.get('project_type')
            dependencies = values.get('dependencies')
            
            if dependencies and project_type:
                if project_type == ProjectTypeEnum.PYTHON and dependencies.nodejs:
                    raise ValueError('Python项目不应该有Node.js依赖')
                elif project_type == ProjectTypeEnum.NODEJS and dependencies.python:
                    raise ValueError('Node.js项目不应该有Python依赖')
            
            return values


class ServerConfigSchema(BaseModel):
    """MCP服务器运行时配置"""
    id: str = Field(..., description="服务器唯一标识符")
    name: str = Field(..., description="服务器名称")
    path: str = Field(..., description="服务器文件路径")
    project_type: ProjectTypeEnum = Field(..., description="项目类型")
    entry_point: str = Field(..., description="入口点")
    
    # 运行时配置
    port: Optional[int] = Field(None, description="服务端口", ge=1024, le=65535)
    host: str = Field("localhost", description="服务主机")
    args: Optional[List[str]] = Field(None, description="启动参数")
    env: Optional[Dict[str, str]] = Field(None, description="环境变量")
    
    # 进程管理
    auto_restart: bool = Field(True, description="自动重启")
    max_restarts: int = Field(3, description="最大重启次数", ge=0, le=10)
    restart_delay: float = Field(1.0, description="重启延迟（秒）", ge=0.1, le=60.0)
    
    # 健康检查
    health_check: Optional[StartupCheckSchema] = Field(None, description="健康检查配置")
    startup_timeout: int = Field(30, description="启动超时（秒）", ge=5, le=300)
    
    # 元数据
    created_at: Optional[str] = Field(None, description="创建时间")
    last_started: Optional[str] = Field(None, description="最后启动时间")
    status: Optional[str] = Field("stopped", description="当前状态")


class ToolRegistrySchema(BaseModel):
    """工具注册表配置"""
    version: str = Field("1.0", description="配置版本")
    description: Optional[str] = Field(None, description="注册表描述")
    tools: List[ToolConfigSchema] = Field(..., description="工具列表")
    
    # 注册表元数据
    name: Optional[str] = Field(None, description="注册表名称")
    maintainer: Optional[str] = Field(None, description="维护者")
    last_updated: Optional[str] = Field(None, description="最后更新时间")
    registry_url: Optional[str] = Field(None, description="注册表URL")
    
    if PYDANTIC_V2:
        @field_validator('tools')
        @classmethod
        def validate_unique_tool_ids(cls, v):
            """验证工具ID的唯一性"""
            ids = [tool.id for tool in v]
            if len(ids) != len(set(ids)):
                raise ValueError('工具ID必须唯一')
            return v
        
        @field_validator('version')
        @classmethod
        def validate_version_format(cls, v):
            """验证版本号格式"""
            import re
            if not re.match(r'^\d+\.\d+(\.\d+)?$', v):
                raise ValueError('版本号格式不正确，应为x.y或x.y.z')
            return v
    else:
        @validator('tools')
        def validate_unique_tool_ids(cls, v):
            """验证工具ID的唯一性"""
            ids = [tool.id for tool in v]
            if len(ids) != len(set(ids)):
                raise ValueError('工具ID必须唯一')
            return v
        
        @validator('version')
        def validate_version_format(cls, v):
            """验证版本号格式"""
            import re
            if not re.match(r'^\d+\.\d+(\.\d+)?$', v):
                raise ValueError('版本号格式不正确，应为x.y或x.y.z')
            return v


class MCPConfigSchema(BaseModel):
    """完整的MCP配置"""
    # 全局配置
    global_settings: Optional[Dict[str, Any]] = Field(None, description="全局设置")
    
    # 工具注册表
    tool_registry: Optional[ToolRegistrySchema] = Field(None, description="工具注册表")
    
    # 服务器配置
    servers: Optional[List[ServerConfigSchema]] = Field(None, description="服务器配置列表")
    
    # 网络配置
    network: Optional[Dict[str, Any]] = Field(None, description="网络配置")
    
    # 安全配置
    security: Optional[Dict[str, Any]] = Field(None, description="安全配置")


# 配置更新模式（用于部分更新）
class ToolConfigUpdateSchema(BaseModel):
    """工具配置更新模式"""
    name: Optional[str] = None
    description: Optional[str] = None
    entry_point: Optional[str] = None
    args: Optional[List[str]] = None
    env: Optional[Dict[str, str]] = None
    tags: Optional[List[str]] = None
    popularity_score: Optional[int] = Field(None, ge=0, le=100)
    security_score: Optional[int] = Field(None, ge=0, le=100)


class ServerConfigUpdateSchema(BaseModel):
    """服务器配置更新模式"""
    name: Optional[str] = None
    port: Optional[int] = Field(None, ge=1024, le=65535)
    host: Optional[str] = None
    args: Optional[List[str]] = None
    env: Optional[Dict[str, str]] = None
    auto_restart: Optional[bool] = None
    max_restarts: Optional[int] = Field(None, ge=0, le=10)
    restart_delay: Optional[float] = Field(None, ge=0.1, le=60.0)