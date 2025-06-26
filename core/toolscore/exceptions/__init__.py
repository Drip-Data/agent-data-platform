"""
异常处理模块
提供分层的异常处理机制，支持精确的错误分类和处理
"""

from .mcp_exceptions import (
    MCPError,
    MCPInstallationError,
    MCPConnectionError,
    MCPConfigurationError,
    EntryPointNotFoundError,
    DependencyInstallError,
    ServerStartupError,
    PortAllocationError,
    ProjectTypeDetectionError,
    SessionError,
    create_entry_point_error,
    create_dependency_error,
    create_startup_error,
    create_port_allocation_error,
    create_connection_error
)

__all__ = [
    'MCPError',
    'MCPInstallationError', 
    'MCPConnectionError',
    'MCPConfigurationError',
    'EntryPointNotFoundError',
    'DependencyInstallError',
    'ServerStartupError',
    'PortAllocationError',
    'ProjectTypeDetectionError',
    'SessionError',
    'create_entry_point_error',
    'create_dependency_error',
    'create_startup_error',
    'create_port_allocation_error',
    'create_connection_error'
]