"""
MCP服务容器模块
实现用户构想的智能MCP服务管理架构

主要特性:
1. 统一的服务管理容器
2. 分离内置和外部服务管理  
3. 轻量级智能安装机制
4. LLM友好的服务接口
5. 实时健康监控和故障恢复
"""

from .models import (
    ServiceConfig,
    ServiceType, 
    ServiceStatus,
    InstallMethod,
    ServiceCapability,
    ServiceHealth,
    InstallationResult,
    ServiceSearchResult
)

from .mcp_service_container import MCPServiceContainer
from .builtin_discovery import BuiltinServiceDiscovery
from .lightweight_installer import LightweightInstaller
from .service_monitor import ServiceMonitor
from .llm_interface import LLMServiceInterface

__all__ = [
    # 核心容器
    'MCPServiceContainer',
    
    # 数据模型
    'ServiceConfig',
    'ServiceType',
    'ServiceStatus', 
    'InstallMethod',
    'ServiceCapability',
    'ServiceHealth',
    'InstallationResult',
    'ServiceSearchResult',
    
    # 组件
    'BuiltinServiceDiscovery',
    'LightweightInstaller',
    'ServiceMonitor',
    'LLMServiceInterface'
]

# 版本信息
__version__ = "2.0.0"
__author__ = "Agent-Data-Platform Team"
__description__ = "智能MCP服务容器管理系统"