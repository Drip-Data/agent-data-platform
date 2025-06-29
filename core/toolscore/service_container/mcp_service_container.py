"""
MCP服务容器 - 统一的服务管理中心
实现用户构想的智能MCP服务管理架构
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta

from .models import ServiceConfig, ServiceType, ServiceStatus, ServiceSearchResult, InstallationResult
from .builtin_discovery import BuiltinServiceDiscovery
from .lightweight_installer import LightweightInstaller
from .service_monitor import ServiceMonitor
from .llm_interface import LLMServiceInterface

logger = logging.getLogger(__name__)


class MCPServiceContainer:
    """
    MCP服务容器 - 统一的服务管理中心
    
    功能特性:
    1. 统一管理内置和外部MCP服务
    2. 智能服务发现和安装
    3. 为LLM提供友好的服务接口
    4. 自动健康监控和故障恢复
    5. 高效的服务生命周期管理
    """
    
    def __init__(self, config_manager=None, mcp_servers_path: str = "mcp_servers"):
        self.config_manager = config_manager
        
        # 服务存储
        self.builtin_services: Dict[str, ServiceConfig] = {}
        self.external_services: Dict[str, ServiceConfig] = {}
        self.service_catalog: Dict[str, ServiceConfig] = {}  # 统一服务目录
        
        # 组件初始化
        self.builtin_discovery = BuiltinServiceDiscovery(mcp_servers_path)
        self.installer = LightweightInstaller()
        self.monitor = ServiceMonitor(self)
        self.llm_interface = LLMServiceInterface(self)
        
        # 状态管理
        self.is_initialized = False
        self.is_monitoring = False
        
        # 配置
        self.auto_start_builtin = True
        self.auto_monitor = True
        self.health_check_interval = 30
        
        logger.info("🏗️ MCP服务容器初始化完成")
    
    async def initialize(self) -> None:
        """初始化服务容器"""
        if self.is_initialized:
            logger.debug("⏭️ 服务容器已初始化")
            return
        
        logger.info("🚀 开始初始化MCP服务容器...")
        
        try:
            # 1. 发现内置服务
            await self._discover_builtin_services()
            
            # 2. 加载已安装的外部服务
            await self._load_external_services()
            
            # 3. 构建统一服务目录
            await self._build_service_catalog()
            
            # 4. 标记内置服务为启动中状态（实际启动由外部MCP服务器启动器处理）
            if self.auto_start_builtin:
                await self._mark_builtin_services_starting()
            
            # 5. 启动服务监控（如果启用）
            if self.auto_monitor:
                await self.monitor.start_monitoring()
                self.is_monitoring = True
            
            self.is_initialized = True
            logger.info("✅ MCP服务容器初始化完成")
            
        except Exception as e:
            logger.error(f"❌ MCP服务容器初始化失败: {e}")
            raise
    
    async def shutdown(self) -> None:
        """关闭服务容器"""
        logger.info("🛑 开始关闭MCP服务容器...")
        
        try:
            # 停止监控
            if self.is_monitoring:
                await self.monitor.stop_monitoring()
                self.is_monitoring = False
            
            # 停止所有运行中的服务
            await self._stop_all_services()
            
            logger.info("✅ MCP服务容器关闭完成")
            
        except Exception as e:
            logger.error(f"❌ MCP服务容器关闭失败: {e}")
    
    # ==================== 服务发现和管理 ====================
    
    async def _discover_builtin_services(self) -> None:
        """发现内置服务"""
        logger.info("🔍 发现内置MCP服务...")
        
        discovered = self.builtin_discovery.discover_all_services()
        self.builtin_services = discovered
        
        # 为发现的服务创建配置文件
        self.builtin_discovery.create_service_json_files()
        
        logger.info(f"✅ 发现 {len(discovered)} 个内置服务")
    
    async def _load_external_services(self) -> None:
        """加载已安装的外部服务"""
        logger.info("📂 加载已安装的外部服务...")
        
        installed_services = self.installer.list_installed_services()
        loaded_count = 0
        
        for service_id in installed_services:
            try:
                config = await self.installer._load_existing_config(
                    ServiceConfig(service_id=service_id, name="", description="")
                )
                if config:
                    self.external_services[service_id] = config
                    loaded_count += 1
            except Exception as e:
                logger.error(f"❌ 加载外部服务失败 {service_id}: {e}")
        
        logger.info(f"✅ 加载 {loaded_count} 个外部服务")
    
    async def _build_service_catalog(self) -> None:
        """构建统一服务目录"""
        logger.info("📋 构建统一服务目录...")
        
        self.service_catalog.clear()
        
        # 添加内置服务
        for service_id, config in self.builtin_services.items():
            self.service_catalog[service_id] = config
        
        # 添加外部服务
        for service_id, config in self.external_services.items():
            self.service_catalog[service_id] = config
        
        logger.info(f"✅ 服务目录构建完成，共 {len(self.service_catalog)} 个服务")
    
    async def _mark_builtin_services_starting(self) -> None:
        """标记内置服务为启动中状态（实际启动由外部处理）"""
        logger.info("📋 标记内置服务为启动中状态...")
        
        marked_count = 0
        for service_id, config in self.builtin_services.items():
            if config.auto_start:
                config.status = ServiceStatus.STARTING
                marked_count += 1
        
        logger.info(f"📋 已标记 {marked_count} 个内置服务为启动中状态")
    
    async def _auto_start_builtin_services(self) -> None:
        """自动启动内置服务（已弃用，由外部MCP服务器启动器处理）"""
        logger.info("🚀 自动启动内置服务...")
        
        started_count = 0
        for service_id, config in self.builtin_services.items():
            if config.auto_start:
                try:
                    success = await self.start_service(service_id)
                    if success:
                        started_count += 1
                except Exception as e:
                    logger.error(f"❌ 启动内置服务失败 {service_id}: {e}")
        
        logger.info(f"✅ 自动启动 {started_count} 个内置服务")
    
    async def update_builtin_service_status(self, server_name: str, process_id: int = None, status: ServiceStatus = None) -> bool:
        """更新内置服务状态（由外部MCP服务器启动器调用）"""
        try:
            # 查找对应的服务配置
            service_config = None
            for service_id, config in self.service_catalog.items():
                if (config.service_type == ServiceType.BUILTIN and 
                    (config.service_id == server_name or 
                     config.local_path and server_name in config.local_path)):
                    service_config = config
                    break
            
            if not service_config:
                logger.warning(f"⚠️ 未找到内置服务配置: {server_name}")
                return False
            
            # 更新进程ID
            if process_id:
                service_config.process_id = process_id
                logger.info(f"✅ 内置服务进程ID已更新: {service_config.name} (PID: {process_id})")
            
            # 更新状态
            if status:
                service_config.status = status
                if status == ServiceStatus.RUNNING:
                    service_config.health.is_healthy = True
                    service_config.health.last_check = datetime.now()
                logger.info(f"✅ 内置服务状态已更新: {service_config.name} -> {status.value}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 更新内置服务状态失败 {server_name}: {e}")
            return False
    
    # ==================== 服务生命周期管理 ====================
    
    async def start_service(self, service_id: str) -> bool:
        """启动服务"""
        config = self.service_catalog.get(service_id)
        if not config:
            logger.error(f"❌ 服务不存在: {service_id}")
            return False
        
        if config.status == ServiceStatus.RUNNING:
            logger.debug(f"⏭️ 服务已运行: {service_id}")
            return True
        
        logger.info(f"🚀 启动服务: {config.name}")
        
        try:
            # 更新状态为启动中
            config.status = ServiceStatus.STARTING
            
            # 根据服务类型选择启动方式
            if config.service_type == ServiceType.BUILTIN:
                success = await self._start_builtin_service(config)
            elif config.service_type == ServiceType.EXTERNAL:
                success = await self._start_external_service(config)
            elif config.service_type == ServiceType.DOCKER:
                success = await self._start_docker_service(config)
            else:
                logger.error(f"❌ 不支持的服务类型: {config.service_type}")
                success = False
            
            if success:
                config.status = ServiceStatus.RUNNING
                config.health.is_healthy = True
                config.health.last_check = datetime.now()
                logger.info(f"✅ 服务启动成功: {config.name}")
            else:
                config.status = ServiceStatus.ERROR
                logger.error(f"❌ 服务启动失败: {config.name}")
            
            return success
            
        except Exception as e:
            config.status = ServiceStatus.ERROR
            logger.error(f"❌ 启动服务异常 {service_id}: {e}")
            return False
    
    async def stop_service(self, service_id: str) -> bool:
        """停止服务"""
        config = self.service_catalog.get(service_id)
        if not config:
            logger.error(f"❌ 服务不存在: {service_id}")
            return False
        
        if config.status == ServiceStatus.STOPPED:
            logger.debug(f"⏭️ 服务已停止: {service_id}")
            return True
        
        logger.info(f"🛑 停止服务: {config.name}")
        
        try:
            # 根据服务类型选择停止方式
            success = await self._stop_service_by_type(config)
            
            if success:
                config.status = ServiceStatus.STOPPED
                config.health.is_healthy = False
                config.process_id = None
                config.container_id = None
                logger.info(f"✅ 服务停止成功: {config.name}")
            else:
                logger.error(f"❌ 服务停止失败: {config.name}")
            
            return success
            
        except Exception as e:
            logger.error(f"❌ 停止服务异常 {service_id}: {e}")
            return False
    
    async def restart_service(self, service_id: str) -> bool:
        """重启服务"""
        logger.info(f"🔄 重启服务: {service_id}")
        
        # 先停止，再启动
        await self.stop_service(service_id)
        await asyncio.sleep(2)  # 等待2秒
        return await self.start_service(service_id)
    
    async def _stop_all_services(self) -> None:
        """停止所有服务"""
        logger.info("🛑 停止所有服务...")
        
        running_services = [
            service_id for service_id, config in self.service_catalog.items()
            if config.status == ServiceStatus.RUNNING
        ]
        
        for service_id in running_services:
            await self.stop_service(service_id)
    
    # ==================== 服务安装和管理 ====================
    
    async def search_and_install_services(self, query: str, max_results: int = 5) -> ServiceSearchResult:
        """搜索并安装服务"""
        start_time = datetime.now()
        
        logger.info(f"🔍 搜索服务: {query}")
        
        try:
            # 首先检查已有服务
            available_services = await self._search_available_services(query)
            
            # 如果已有服务不足，搜索可安装的服务
            suggested_installs = []
            if len(available_services) < max_results:
                suggested_installs = await self._search_installable_services(query, max_results - len(available_services))
            
            search_time = (datetime.now() - start_time).total_seconds()
            
            return ServiceSearchResult(
                query=query,
                total_results=len(available_services) + len(suggested_installs),
                available_services=available_services,
                suggested_installs=suggested_installs,
                search_time_seconds=search_time
            )
            
        except Exception as e:
            logger.error(f"❌ 搜索服务失败: {e}")
            return ServiceSearchResult(
                query=query,
                total_results=0,
                search_time_seconds=(datetime.now() - start_time).total_seconds()
            )
    
    async def install_service(self, service_spec: Dict[str, Any]) -> InstallationResult:
        """安装外部服务"""
        logger.info(f"📦 安装服务: {service_spec.get('name', 'Unknown')}")
        
        try:
            # 使用轻量级安装器安装
            result = await self.installer.install_service(service_spec)
            
            if result.success and result.service_config:
                # 添加到外部服务列表
                service_id = result.service_config.service_id
                self.external_services[service_id] = result.service_config
                
                # 更新服务目录
                self.service_catalog[service_id] = result.service_config
                
                logger.info(f"✅ 服务安装成功: {result.service_config.name}")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ 安装服务异常: {e}")
            return InstallationResult(
                success=False,
                error_message=f"安装异常: {str(e)}"
            )
    
    async def uninstall_service(self, service_id: str) -> bool:
        """卸载服务"""
        config = self.external_services.get(service_id)
        if not config:
            logger.error(f"❌ 外部服务不存在: {service_id}")
            return False
        
        logger.info(f"🗑️ 卸载服务: {config.name}")
        
        try:
            # 先停止服务
            await self.stop_service(service_id)
            
            # 卸载文件
            success = await self.installer.uninstall_service(service_id)
            
            if success:
                # 从服务列表中移除
                self.external_services.pop(service_id, None)
                self.service_catalog.pop(service_id, None)
                
                logger.info(f"✅ 服务卸载成功: {config.name}")
            
            return success
            
        except Exception as e:
            logger.error(f"❌ 卸载服务异常: {e}")
            return False
    
    # ==================== LLM接口 ====================
    
    def get_available_services_for_llm(self) -> Dict[str, Any]:
        """为LLM提供可用服务清单"""
        return self.llm_interface.get_service_catalog_for_llm()
    
    def get_service_recommendations_for_llm(self, task_description: str) -> List[Dict[str, Any]]:
        """为LLM提供基于任务的服务推荐"""
        return self.llm_interface.recommend_services_for_task(task_description)
    
    async def call_service_for_llm(self, service_id: str, capability_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """为LLM提供统一的服务调用接口"""
        return await self.llm_interface.call_service_capability(service_id, capability_name, parameters)
    
    # ==================== 服务状态和监控 ====================
    
    def get_service_status(self, service_id: str) -> Optional[Dict[str, Any]]:
        """获取服务状态"""
        config = self.service_catalog.get(service_id)
        if not config:
            return None
        
        return config.to_dict()
    
    def get_all_services_status(self) -> Dict[str, Any]:
        """获取所有服务状态"""
        return {
            "total_services": len(self.service_catalog),
            "builtin_services": len(self.builtin_services),
            "external_services": len(self.external_services),
            "running_services": len([
                c for c in self.service_catalog.values() 
                if c.status == ServiceStatus.RUNNING
            ]),
            "healthy_services": len([
                c for c in self.service_catalog.values() 
                if c.health.is_healthy
            ]),
            "services": {
                service_id: config.to_dict()
                for service_id, config in self.service_catalog.items()
            },
            "last_updated": datetime.now().isoformat()
        }
    
    def get_container_statistics(self) -> Dict[str, Any]:
        """获取容器统计信息"""
        total_capabilities = sum(
            len(config.capabilities) 
            for config in self.service_catalog.values()
        )
        
        service_types = {}
        for config in self.service_catalog.values():
            service_type = config.service_type.value
            service_types[service_type] = service_types.get(service_type, 0) + 1
        
        return {
            "container_info": {
                "initialized": self.is_initialized,
                "monitoring_enabled": self.is_monitoring,
                "health_check_interval": self.health_check_interval
            },
            "service_statistics": {
                "total_services": len(self.service_catalog),
                "total_capabilities": total_capabilities,
                "service_types": service_types,
                "builtin_services": len(self.builtin_services),
                "external_services": len(self.external_services)
            },
            "status_distribution": {
                status.value: len([
                    c for c in self.service_catalog.values() 
                    if c.status == status
                ])
                for status in ServiceStatus
            }
        }
    
    # ==================== 私有辅助方法 ====================
    
    async def _search_available_services(self, query: str) -> List[ServiceConfig]:
        """搜索可用服务"""
        results = []
        query_lower = query.lower()
        
        for config in self.service_catalog.values():
            # 简单的关键词匹配
            if (query_lower in config.name.lower() or 
                query_lower in config.description.lower() or
                any(query_lower in tag.lower() for tag in config.tags)):
                results.append(config)
        
        return results
    
    async def _search_installable_services(self, query: str, max_results: int) -> List[Dict[str, Any]]:
        """搜索可安装的服务"""
        # 这里可以集成外部服务注册表的搜索
        # 暂时返回示例结果
        return []
    
    async def _start_builtin_service(self, config: ServiceConfig) -> bool:
        """启动内置服务"""
        # 内置服务由外部MCP服务器启动器管理
        # 这里我们需要从外部系统获取进程信息
        try:
            # 尝试从MCP服务器启动器获取进程信息
            from services.mcp_server_launcher import get_server_status, mcp_processes
            
            server_name = config.service_id
            status = get_server_status(server_name)
            
            if status and status.get('status') == 'running':
                # 从全局进程字典获取进程ID
                if server_name in mcp_processes:
                    process = mcp_processes[server_name]
                    if process and process.poll() is None:  # 进程仍在运行
                        config.process_id = process.pid
                        logger.info(f"✅ 内置服务进程ID已设置: {config.name} (PID: {process.pid})")
                        return True
            
            logger.warning(f"⚠️ 内置服务未找到运行进程: {config.name}")
            return False
            
        except Exception as e:
            logger.error(f"❌ 获取内置服务进程信息失败 {config.name}: {e}")
            return False
    
    async def _start_external_service(self, config: ServiceConfig) -> bool:
        """启动外部服务"""
        # 启动外部安装的服务
        return True
    
    async def _start_docker_service(self, config: ServiceConfig) -> bool:
        """启动Docker服务"""
        # 启动Docker容器服务
        return True
    
    async def _stop_service_by_type(self, config: ServiceConfig) -> bool:
        """根据类型停止服务"""
        # 根据服务类型选择相应的停止方法
        return True
    
    async def list_available_tools(self, server_id: Optional[str] = None) -> Dict[str, Any]:
        """列出可用工具 - 实现缺失的方法以修复available_actions为空的问题"""
        try:
            tools_info = {}
            
            # 如果指定了server_id，只返回该服务器的工具
            if server_id:
                config = self.service_catalog.get(server_id)
                if config and config.status == ServiceStatus.RUNNING:
                    tools_info[server_id] = self._get_service_tools(config)
            else:
                # 返回所有运行中服务的工具
                for service_id, config in self.service_catalog.items():
                    if config.status == ServiceStatus.RUNNING:
                        tools_info[service_id] = self._get_service_tools(config)
            
            return {
                "success": True,
                "servers": tools_info
            }
            
        except Exception as e:
            logger.error(f"❌ 列出工具失败: {e}")
            return {"success": False, "error": str(e)}
    
    def _get_service_tools(self, config: ServiceConfig) -> Dict[str, Any]:
        """获取服务的工具信息，包含available_actions"""
        tools = []
        
        # 根据服务配置构建工具信息
        for capability in config.capabilities:
            tool_name = capability.name if hasattr(capability, 'name') else str(capability)
            
            # 为不同服务提供具体的available_actions
            if config.service_id == "microsandbox":
                available_actions = ["microsandbox_execute", "microsandbox_install_package", 
                                   "microsandbox_list_sessions", "microsandbox_close_session"]
            elif config.service_id == "deepsearch_server":
                available_actions = ["research", "quick_research", "comprehensive_research"]
            elif config.service_id == "browser_use_server":
                available_actions = ["browser_go_to_url", "browser_click", "browser_input_text",
                                   "browser_get_screenshot", "browser_get_page_content"]
            elif config.service_id == "search_tool_server":
                available_actions = ["search_file_content", "find_definition", "search_files"]
            else:
                available_actions = [tool_name]
            
            tools.append({
                "name": tool_name,
                "available_actions": available_actions
            })
        
        return {"tools": tools}