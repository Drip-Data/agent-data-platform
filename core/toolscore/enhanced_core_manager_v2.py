"""
增强核心管理器 v2.0
基于新的MCP服务容器架构实现统一的工具管理

这是新架构的核心集成层，实现:
1. 兼容原有接口，保证系统平滑迁移
2. 使用新的服务容器提供更强大的功能
3. 为LLM提供智能的服务发现和调用能力
4. 统一管理内置和外部MCP服务
"""

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Dict, List, Optional, Any

from .service_container import MCPServiceContainer, ServiceType, ServiceStatus
from .interfaces import ToolCapability, ToolType, MCPServerSpec
from .exceptions import MCPError

logger = logging.getLogger(__name__)


class EnhancedCoreManagerV2:
    """增强核心管理器 v2.0 - 基于服务容器架构"""
    
    def __init__(self, config_manager=None):
        self.config_manager = config_manager
        
        # 新架构核心组件
        self.service_container = MCPServiceContainer(config_manager)
        
        # 兼容性支持
        self._tool_cache = {}
        self._cache_lock = asyncio.Lock()
        
        # 统计信息
        self.stats = {
            "initialization_time": 0,
            "services_discovered": 0,
            "services_installed": 0,
            "tool_calls_made": 0,
            "last_activity": None
        }
        
        logger.info("🏗️ 增强核心管理器 v2.0 初始化完成")
    
    async def initialize(self) -> None:
        """初始化管理器"""
        start_time = time.time()
        
        logger.info("🚀 初始化增强核心管理器 v2.0...")
        
        try:
            # 初始化服务容器
            await self.service_container.initialize()
            
            # 更新统计信息
            self.stats["initialization_time"] = time.time() - start_time
            self.stats["services_discovered"] = len(self.service_container.service_catalog)
            self.stats["last_activity"] = time.time()
            
            logger.info("✅ 增强核心管理器 v2.0 初始化完成")
            
        except Exception as e:
            logger.error(f"❌ 增强核心管理器 v2.0 初始化失败: {e}")
            raise
    
    async def shutdown(self) -> None:
        """关闭管理器"""
        logger.info("🛑 关闭增强核心管理器 v2.0...")
        
        try:
            await self.service_container.shutdown()
            logger.info("✅ 增强核心管理器 v2.0 关闭完成")
        except Exception as e:
            logger.error(f"❌ 关闭失败: {e}")
    
    # ==================== 工具搜索和安装接口 (兼容原API) ====================
    
    async def search_and_install_tools(self, query: str, max_tools: int = 5) -> Dict[str, Any]:
        """
        搜索并安装工具 (兼容原接口)
        使用新的服务容器提供更智能的搜索和安装
        """
        self.stats["last_activity"] = time.time()
        
        logger.info(f"🔍 v2.0 搜索工具: {query}")
        
        try:
            # 使用服务容器搜索
            search_result = await self.service_container.search_and_install_services(query, max_tools)
            
            installed_tools = []
            
            # 如果有推荐的服务，尝试安装
            for suggestion in search_result.suggested_installs[:max_tools]:
                logger.info(f"📦 尝试安装推荐服务: {suggestion.get('name', 'Unknown')}")
                
                install_result = await self.service_container.install_service(suggestion)
                
                if install_result.success:
                    self.stats["services_installed"] += 1
                    
                    # 转换为兼容格式
                    tool_info = {
                        "tool_id": install_result.service_config.service_id,
                        "name": install_result.service_config.name,
                        "description": install_result.service_config.description,
                        "capabilities": [cap.name for cap in install_result.service_config.capabilities],
                        "endpoint": install_result.service_config.actual_endpoint or install_result.service_config.endpoint,
                        "status": "installed",
                        "install_time": install_result.installation_time_seconds
                    }
                    installed_tools.append(tool_info)
            
            return {
                "success": True,
                "message": f"搜索完成，找到 {search_result.total_results} 个结果",
                "installed_tools": installed_tools,
                "available_services": len(search_result.available_services),
                "search_time": search_result.search_time_seconds
            }
            
        except Exception as e:
            logger.error(f"❌ v2.0 搜索工具失败: {e}")
            return {
                "success": False,
                "message": "搜索失败",
                "installed_tools": [],
                "error_message": str(e)
            }
    
    async def call_tool(self, server_id: str, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        调用工具 (兼容原接口)
        使用新的服务容器提供统一的调用接口
        """
        self.stats["tool_calls_made"] += 1
        self.stats["last_activity"] = time.time()
        
        logger.info(f"🔧 v2.0 调用工具: {server_id}.{tool_name}")
        
        try:
            # 使用服务容器的LLM接口调用
            result = await self.service_container.call_service_for_llm(
                service_id=server_id,
                capability_name=tool_name,
                parameters=arguments
            )
            
            if result["success"]:
                return {
                    "success": True,
                    "result": result["result"],
                    "server_id": server_id,
                    "tool_name": tool_name,
                    "execution_time": result.get("execution_time")
                }
            else:
                return {
                    "success": False,
                    "error": result["error"],
                    "error_type": result.get("error_type", "UNKNOWN"),
                    "server_id": server_id,
                    "tool_name": tool_name
                }
                
        except Exception as e:
            logger.error(f"❌ v2.0 调用工具失败: {e}")
            return {
                "success": False,
                "error": f"调用异常: {str(e)}",
                "error_type": "EXECUTION_EXCEPTION",
                "server_id": server_id,
                "tool_name": tool_name
            }
    
    async def register_tool_immediately(self, server_spec: MCPServerSpec) -> bool:
        """
        立即注册工具 (兼容原接口)
        将传统的服务器规格转换为新的服务配置
        """
        logger.info(f"📝 v2.0 注册工具: {server_spec.name}")
        
        try:
            # 转换为新的服务规格格式
            service_spec = {
                "id": server_spec.tool_id,
                "name": server_spec.name,
                "description": server_spec.description,
                "capabilities": [
                    {
                        "name": cap.name,
                        "description": cap.description,
                        "parameters": cap.parameters,
                        "required_params": [
                            param for param, config in cap.parameters.items()
                            if config.get("required", False)
                        ],
                        "optional_params": [
                            param for param, config in cap.parameters.items()
                            if not config.get("required", False)
                        ]
                    }
                    for cap in server_spec.capabilities
                ],
                "endpoint": getattr(server_spec, 'endpoint', None),
                "tags": getattr(server_spec, 'tags', []),
                "service_type": "builtin"
            }
            
            # 使用服务容器安装
            result = await self.service_container.install_service(service_spec)
            
            if result.success:
                logger.info(f"✅ v2.0 工具注册成功: {server_spec.name}")
                return True
            else:
                logger.error(f"❌ v2.0 工具注册失败: {result.error_message}")
                return False
                
        except Exception as e:
            logger.error(f"❌ v2.0 注册工具异常: {e}")
            return False
    
    # ==================== 新的LLM智能接口 ====================
    
    def get_available_tools_for_llm(self) -> Dict[str, Any]:
        """为LLM提供可用工具清单 - 新功能"""
        return self.service_container.get_available_services_for_llm()
    
    def recommend_tools_for_task(self, task_description: str) -> List[Dict[str, Any]]:
        """为LLM提供基于任务的工具推荐 - 新功能"""
        return self.service_container.get_service_recommendations_for_llm(task_description)
    
    def get_service_capabilities_summary(self) -> Dict[str, Any]:
        """获取服务能力汇总 - 新功能"""
        return self.service_container.llm_interface.get_service_capabilities_summary()
    
    # ==================== 服务管理接口 ====================
    
    async def start_service(self, service_id: str) -> bool:
        """启动服务"""
        return await self.service_container.start_service(service_id)
    
    async def stop_service(self, service_id: str) -> bool:
        """停止服务"""
        return await self.service_container.stop_service(service_id)
    
    async def restart_service(self, service_id: str) -> bool:
        """重启服务"""
        return await self.service_container.restart_service(service_id)
    
    def get_service_status(self, service_id: str) -> Optional[Dict[str, Any]]:
        """获取服务状态"""
        return self.service_container.get_service_status(service_id)
    
    def list_all_services(self) -> Dict[str, Any]:
        """列出所有服务"""
        return self.service_container.get_all_services_status()
    
    # ==================== 统计和监控接口 ====================
    
    def get_stats(self) -> Dict[str, Any]:
        """获取管理器统计信息 (兼容原接口)"""
        container_stats = self.service_container.get_container_statistics()
        
        return {
            "manager_version": "2.0.0",
            "architecture": "service_container",
            
            # 兼容原统计格式
            "total_servers": container_stats["service_statistics"]["total_services"],
            "running_servers": len([
                c for c in self.service_container.service_catalog.values()
                if c.status == ServiceStatus.RUNNING
            ]),
            "healthy_servers": len([
                c for c in self.service_container.service_catalog.values()
                if c.health.is_healthy
            ]),
            
            # 新的统计信息
            "v2_stats": {
                **self.stats,
                "container_stats": container_stats,
                "monitoring_stats": self.service_container.monitor.get_monitoring_statistics()
            }
        }
    
    def get_enhanced_stats(self) -> Dict[str, Any]:
        """获取增强统计信息 - 新功能"""
        return {
            "manager_info": {
                "version": "2.0.0",
                "architecture": "service_container",
                "initialization_time": self.stats["initialization_time"],
                "uptime_seconds": time.time() - (self.stats["last_activity"] or time.time())
            },
            "service_container": self.service_container.get_container_statistics(),
            "performance": {
                "services_discovered": self.stats["services_discovered"],
                "services_installed": self.stats["services_installed"],
                "tool_calls_made": self.stats["tool_calls_made"],
                "last_activity": self.stats["last_activity"]
            },
            "health_monitoring": self.service_container.monitor.get_monitoring_statistics()
        }
    
    # ==================== 内部方法 ====================
    
    def _is_container_healthy(self) -> bool:
        """检查服务容器健康状态"""
        try:
            if not self.service_container.is_initialized:
                return False
            
            # 检查是否有健康的服务
            healthy_services = [
                c for c in self.service_container.service_catalog.values()
                if c.health.is_healthy
            ]
            
            return len(healthy_services) > 0
            
        except Exception:
            return False
    
    async def _update_tool_cache(self, tool_id: str, tool_data: Dict[str, Any]):
        """更新工具缓存 (兼容性方法)"""
        async with self._cache_lock:
            self._tool_cache[tool_id] = tool_data