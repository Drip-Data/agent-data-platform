"""
MCP会话管理模块
提供标准化的MCP协议会话管理功能
"""

from .session_handler import MCPSessionHandler

try:
    from .session_manager import MCPSessionManager
    from .connection_pool import MCPConnectionPool
    
    __all__ = [
        'MCPSessionManager',
        'MCPSessionHandler', 
        'MCPConnectionPool'
    ]
except ImportError:
    # 如果某些组件无法导入，只导入基础组件
    __all__ = [
        'MCPSessionHandler'
    ]