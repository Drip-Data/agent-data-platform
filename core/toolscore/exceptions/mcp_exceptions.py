"""
MCP相关异常定义
提供精确的错误分类，便于错误处理和调试
"""

from typing import Optional, Dict, Any


class MCPError(Exception):
    """MCP相关错误的基类"""
    
    def __init__(self, message: str, error_code: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.details = details or {}
    
    def __str__(self):
        result = self.message
        if self.error_code:
            result = f"[{self.error_code}] {result}"
        return result
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式，便于序列化"""
        return {
            "error_type": self.__class__.__name__,
            "message": self.message,
            "error_code": self.error_code,
            "details": self.details
        }


class MCPInstallationError(MCPError):
    """MCP服务器安装相关错误"""
    
    def __init__(self, message: str, server_id: Optional[str] = None, install_step: Optional[str] = None, **kwargs):
        super().__init__(message, **kwargs)
        self.server_id = server_id
        self.install_step = install_step
        if server_id:
            self.details['server_id'] = server_id
        if install_step:
            self.details['install_step'] = install_step


class MCPConnectionError(MCPError):
    """MCP连接相关错误"""
    
    def __init__(self, message: str, server_id: Optional[str] = None, port: Optional[int] = None, **kwargs):
        super().__init__(message, **kwargs)
        self.server_id = server_id
        self.port = port
        if server_id:
            self.details['server_id'] = server_id
        if port:
            self.details['port'] = port


class MCPConfigurationError(MCPError):
    """MCP配置相关错误"""
    
    def __init__(self, message: str, config_file: Optional[str] = None, config_key: Optional[str] = None, **kwargs):
        super().__init__(message, **kwargs)
        self.config_file = config_file
        self.config_key = config_key
        if config_file:
            self.details['config_file'] = config_file
        if config_key:
            self.details['config_key'] = config_key


class EntryPointNotFoundError(MCPInstallationError):
    """入口点未找到错误"""
    
    def __init__(self, message: str, project_path: Optional[str] = None, project_type: Optional[str] = None, **kwargs):
        super().__init__(message, install_step="entry_point_detection", **kwargs)
        self.project_path = project_path
        self.project_type = project_type
        if project_path:
            self.details['project_path'] = project_path
        if project_type:
            self.details['project_type'] = project_type


class DependencyInstallError(MCPInstallationError):
    """依赖安装错误"""
    
    def __init__(self, message: str, dependency: Optional[str] = None, command: Optional[str] = None, **kwargs):
        super().__init__(message, install_step="dependency_installation", **kwargs)
        self.dependency = dependency
        self.command = command
        if dependency:
            self.details['dependency'] = dependency
        if command:
            self.details['command'] = command


class ServerStartupError(MCPError):
    """服务器启动错误"""
    
    def __init__(self, message: str, server_id: Optional[str] = None, startup_command: Optional[str] = None, **kwargs):
        super().__init__(message, **kwargs)
        self.server_id = server_id
        self.startup_command = startup_command
        if server_id:
            self.details['server_id'] = server_id
        if startup_command:
            self.details['startup_command'] = startup_command


class PortAllocationError(MCPError):
    """端口分配错误"""
    
    def __init__(self, message: str, port_range: Optional[str] = None, attempted_ports: Optional[list] = None, **kwargs):
        super().__init__(message, **kwargs)
        self.port_range = port_range
        self.attempted_ports = attempted_ports or []
        if port_range:
            self.details['port_range'] = port_range
        if attempted_ports:
            self.details['attempted_ports'] = attempted_ports


class ProjectTypeDetectionError(MCPError):
    """项目类型检测错误"""
    
    def __init__(self, message: str, project_path: Optional[str] = None, indicators_found: Optional[list] = None, **kwargs):
        super().__init__(message, **kwargs)
        self.project_path = project_path
        self.indicators_found = indicators_found or []
        if project_path:
            self.details['project_path'] = project_path
        if indicators_found:
            self.details['indicators_found'] = indicators_found


class SessionError(MCPError):
    """MCP会话相关错误"""
    
    def __init__(self, message: str, session_id: Optional[str] = None, operation: Optional[str] = None, **kwargs):
        super().__init__(message, **kwargs)
        self.session_id = session_id
        self.operation = operation
        if session_id:
            self.details['session_id'] = session_id
        if operation:
            self.details['operation'] = operation


# 便捷的异常创建函数
def create_entry_point_error(project_path: str, project_type: str, searched_patterns: list = None) -> EntryPointNotFoundError:
    """创建入口点未找到错误"""
    message = f"无法找到{project_type}项目的入口点: {project_path}"
    if searched_patterns:
        message += f"，已搜索模式: {searched_patterns}"
    
    return EntryPointNotFoundError(
        message=message,
        project_path=project_path,
        project_type=project_type,
        error_code="ENTRY_POINT_NOT_FOUND",
        details={"searched_patterns": searched_patterns or []}
    )


def create_dependency_error(dependency: str, command: str, error_output: str = None) -> DependencyInstallError:
    """创建依赖安装错误"""
    message = f"依赖安装失败: {dependency}"
    if error_output:
        message += f"，错误输出: {error_output}"
    
    return DependencyInstallError(
        message=message,
        dependency=dependency,
        command=command,
        error_code="DEPENDENCY_INSTALL_FAILED",
        details={"error_output": error_output}
    )


def create_startup_error(server_id: str, command: str, error_output: str = None) -> ServerStartupError:
    """创建服务器启动错误"""
    message = f"服务器启动失败: {server_id}"
    if error_output:
        message += f"，错误输出: {error_output}"
    
    return ServerStartupError(
        message=message,
        server_id=server_id,
        startup_command=command,
        error_code="SERVER_STARTUP_FAILED",
        details={"error_output": error_output}
    )


def create_port_allocation_error(port_range: str, attempted_ports: list) -> PortAllocationError:
    """创建端口分配错误"""
    message = f"端口分配失败，范围: {port_range}，已尝试端口: {attempted_ports}"
    
    return PortAllocationError(
        message=message,
        port_range=port_range,
        attempted_ports=attempted_ports,
        error_code="PORT_ALLOCATION_FAILED"
    )


def create_connection_error(server_id: str, port: int, timeout: float = None) -> MCPConnectionError:
    """创建连接错误"""
    message = f"连接MCP服务器失败: {server_id}:{port}"
    if timeout:
        message += f"，超时: {timeout}s"
    
    return MCPConnectionError(
        message=message,
        server_id=server_id,
        port=port,
        error_code="CONNECTION_FAILED",
        details={"timeout": timeout}
    )