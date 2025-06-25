"""
配置管理模块
提供MCP工具配置的验证、管理和扩展功能
"""

try:
    from .config_validator import MCPConfigValidator
    from .schemas import ToolConfigSchema, ServerConfigSchema, StartupCheckSchema
    
    __all__ = [
        'MCPConfigValidator',
        'ToolConfigSchema',
        'ServerConfigSchema',
        'StartupCheckSchema'
    ]
except ImportError:
    # 如果pydantic不可用，提供基础实现
    class MCPConfigValidator:
        def validate_tool_config(self, config): return config
        def validate_server_config(self, config): return config
        
    class ToolConfigSchema(dict): pass
    class ServerConfigSchema(dict): pass
    class StartupCheckSchema(dict): pass
    
    __all__ = [
        'MCPConfigValidator',
        'ToolConfigSchema',
        'ServerConfigSchema',
        'StartupCheckSchema'
    ]