"""
统一工具库
纯粹的工具管理平台，为执行环境中的自主Agent提供工具注册、发现、描述和调用服务
"""

import logging
import asyncio
import time
from typing import Dict, Any, List, Optional

from .interfaces import (
    ToolSpec, FunctionToolSpec, MCPServerSpec,
    ExecutionResult, RegistrationResult, ToolType
)
from .tool_registry import ToolRegistry
# from .description_engine import DescriptionEngine  # 精简版本中已移除
# from .unified_dispatcher import UnifiedDispatcher  # 精简版本中已移除
from .core_manager import CoreManager

logger = logging.getLogger(__name__)


class UnifiedToolLibrary:
    """
    统一工具库 - API网关
    
    职责分离原则：
    - 工具库专注工具管理，Agent专注智能决策
    - 纯服务化：仅提供工具管理和查询API，不做智能推荐
    - 无硬编码规则：不使用关键词匹配等硬编码逻辑
    """
    
    def __init__(self, mcp_client: Optional[Any] = None, redis_url: str = "redis://redis:6379"):
        # 使用新的核心管理器整合分散功能
        self.core_manager = CoreManager(redis_url)
        
        # 初始化核心组件
        self.tool_registry = ToolRegistry()
        # self.description_engine = DescriptionEngine(self.tool_registry)  # 精简版本中已移除
        # self.dispatcher = UnifiedDispatcher(self.tool_registry, mcp_client)  # 精简版本中已移除
        self.mcp_client = mcp_client
        
        # 动态MCP管理器（延迟初始化）
        self.dynamic_mcp_manager = None
        
        # 新增组件 - 使用核心管理器的功能
        self.cache_manager = self.core_manager  # 使用核心管理器的缓存功能
        self.real_time_registry = self.core_manager  # 使用核心管理器的实时注册功能
        
        # 简化的工具组件
        self.tool_gap_detector = None
        self.mcp_search_tool = None
        
        self._initialized = False
        logger.info("Unified Tool Library initialized - 使用核心管理器整合模式")
    
    async def initialize(self):
        """初始化工具库"""
        if self._initialized:
            return
        
        try:
            # 初始化核心管理器（包含缓存、实时注册、容器管理等）
            await self.core_manager.initialize()
            
            # 初始化各组件
            await self.tool_registry.initialize()
            # await self.description_engine.initialize()  # 精简版本中已移除
            # await self.dispatcher.initialize()  # 精简版本中已移除
            
            # 初始化工具缺口检测器（简化版本）
            from .tool_gap_detector import SmartToolGapDetector
            self.tool_gap_detector = SmartToolGapDetector(
                llm_client=None,  # 解耦LLM客户端
                cache_manager=self.cache_manager  # 使用核心管理器的缓存功能
            )
            
            # 初始化动态MCP管理器
            from .dynamic_mcp_manager import DynamicMCPManager
            self.dynamic_mcp_manager = DynamicMCPManager(self)
            await self.dynamic_mcp_manager.initialize()
            
            # 初始化MCP搜索工具
            from .mcp_search_tool import MCPSearchTool
            self.mcp_search_tool = MCPSearchTool(
                tool_gap_detector=self.tool_gap_detector,
                dynamic_mcp_manager=self.dynamic_mcp_manager
            )
            
            logger.info("Tool library initialization completed - 核心管理器模式")
            self._initialized = True
        except Exception as e:
            logger.error(f"Failed to initialize tool library: {e}")
            raise
    
    # ============ 工具注册API ============
    
    async def register_function_tool(self, tool_spec: FunctionToolSpec) -> RegistrationResult:
        """注册Function Tool"""
        return await self.tool_registry.register_function_tool(tool_spec)
    
    async def register_mcp_server(self, server_spec: MCPServerSpec) -> RegistrationResult:
        """注册MCP Server"""
        return await self.tool_registry.register_mcp_server(server_spec)

    async def register_external_mcp_server(self, server_spec: MCPServerSpec) -> RegistrationResult:
        """
        注册外部MCP服务器。
        此接口用于手动注册已在外部运行或管理的MCP服务器。
        它将服务器规范直接添加到工具注册中心。
        """
        logger.info(f"Registering external MCP server: {server_spec.name} (ID: {server_spec.tool_id})")
        
        # 可以在此处添加额外的验证逻辑，例如检查endpoint的可达性
        if not server_spec.endpoint:
            return RegistrationResult(success=False, error="MCP Server endpoint is required.")
        
        # 确保tool_type是MCP_SERVER
        server_spec.tool_type = ToolType.MCP_SERVER
        
        # 调用底层的工具注册中心进行注册
        registration_result = await self.tool_registry.register_mcp_server(server_spec)
        
        if registration_result.success:
            logger.info(f"Successfully registered external MCP server: {server_spec.name}")
        else:
            logger.error(f"Failed to register external MCP server {server_spec.name}: {registration_result.error}")
            
        return registration_result
    
    async def unregister_tool(self, tool_id: str) -> RegistrationResult:
        """注销工具"""
        try:
            success = await self.tool_registry.unregister_tool(tool_id)
            
            if success:
                logger.info(f"✅ 工具已从注册表中注销: {tool_id}")
                return RegistrationResult(success=True, tool_id=tool_id)
            else:
                logger.error(f"❌ 工具注销失败: {tool_id}")
                return RegistrationResult(success=False, tool_id=tool_id, error="Tool not found or unregistration failed")
                
        except Exception as e:
            logger.error(f"❌ 工具注销异常: {tool_id} - {e}")
            return RegistrationResult(success=False, tool_id=tool_id, error=str(e))
    
    # ============ 动态MCP管理API ============
    
    async def search_and_install_mcp_server(self, query: str, capability_tags: Optional[List[str]] = None) -> Dict[str, Any]:
        """搜索并安装MCP服务器"""
        if not self.dynamic_mcp_manager:
            return {
                "success": False,
                "error": "Dynamic MCP manager not initialized"
            }
        
        try:
            # 搜索候选服务器
            candidates = await self.dynamic_mcp_manager.search_mcp_servers(query, capability_tags or [])
            
            if not candidates:
                return {
                    "success": False,
                    "error": "No suitable MCP servers found",
                    "candidates_count": 0
                }
            
            # 安装最佳候选者
            best_candidate = candidates[0]
            install_result = await self.dynamic_mcp_manager.install_mcp_server(best_candidate)
            
            if install_result.success:
                # 注册到工具库
                registration_result = await self.dynamic_mcp_manager.register_installed_server(
                    best_candidate, install_result
                )
                
                return {
                    "success": registration_result.success,
                    "server_name": best_candidate.name,
                    "server_id": install_result.server_id,
                    "capabilities": best_candidate.capabilities,
                    "endpoint": install_result.endpoint,
                    "error": registration_result.error if not registration_result.success else None
                }
            else:
                return {
                    "success": False,
                    "error": install_result.error_message,
                    "server_name": best_candidate.name
                }
        
        except Exception as e:
            logger.error(f"Failed to search and install MCP server: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def get_dynamic_mcp_stats(self) -> Dict[str, Any]:
        """获取动态MCP管理器统计信息"""
        if not self.dynamic_mcp_manager:
            return {"error": "Dynamic MCP manager not initialized"}
        
        try:
            installed_servers = await self.dynamic_mcp_manager.get_installed_servers()
            health_status = await self.dynamic_mcp_manager.health_check_installed_servers()
            
                        if hasattr(self.dynamic_mcp_manager, 'core_manager') and self.dynamic_mcp_manager._storage_initialized:
                storage_stats = {
                    "storage_type": "core_manager",
                    "initialized": True
                }
            else:
                storage_stats = {"error": "Persistent storage not initialized"}
            
            return {
                "installed_servers_count": len(installed_servers),
                "installed_servers": {k: {"endpoint": v.endpoint, "success": v.success} for k, v in installed_servers.items()},
                "health_status": health_status,
                "storage_stats": storage_stats
            }
        except Exception as e:
            logger.error(f"Failed to get dynamic MCP stats: {e}")
            return {"error": str(e)}
    
    # ============ 工具查询API ============
    
    async def get_all_tools(self) -> List[ToolSpec]:
        """获取所有可用工具"""
        all_tools = []
        
        # 总是获取本地注册的工具（包括Function Tools）
        local_tools = await self.tool_registry.get_all_tools()
        all_tools.extend(local_tools)
        
        # 如果有MCP客户端，还要获取远程工具并合并
        if self.mcp_client:
            try:
                # 调用MCP客户端获取远程工具
                remote_tools = await self.mcp_client.get_all_tools()
                
                # 去重合并：避免相同tool_id的工具重复
                existing_tool_ids = {tool.tool_id for tool in all_tools}
                for remote_tool in remote_tools:
                    if remote_tool.tool_id not in existing_tool_ids:
                        all_tools.append(remote_tool)
                        
                logger.debug(f"Merged {len(local_tools)} local tools and {len(remote_tools)} remote tools")
            except Exception as e:
                logger.error(f"Failed to get tools from MCP client: {e}")
                # 继续使用本地工具，不抛出异常
        
        return all_tools
    
    async def get_tools_by_type(self, tool_type: ToolType) -> List[ToolSpec]:
        """按类型获取工具"""
        return await self.tool_registry.get_tools_by_type(tool_type)
    
    async def get_tool_by_id(self, tool_id: str) -> Optional[ToolSpec]:
        """获取指定工具"""
        return await self.tool_registry.get_tool_spec(tool_id)
    
    async def search_tools_by_tags(self, tags: List[str]) -> List[ToolSpec]:
        """按标签搜索工具（为将来扩展预留）"""
        return await self.tool_registry.search_tools_by_tags(tags)
    
    # ============ 工具描述API ============
    
    async def get_tool_description_for_agent(self, tool_id: str) -> str:
        """获取Agent可理解的工具描述"""
        # 精简版本：直接返回基本工具描述
        tool = await self.get_tool_by_id(tool_id)
        if tool:
            return f"**{tool.name}**: {tool.description}"
        return f"工具 {tool_id} 未找到"
    
    async def get_all_tools_description_for_agent(self) -> str:
        """获取所有工具的Agent可理解描述"""
        # 如果有MCP客户端，直接从工具列表生成描述
        if self.mcp_client:
            try:
                tools = await self.get_all_tools()
                if not tools:
                    return "暂无可用工具"
                
                descriptions = []
                for tool in tools:
                    capabilities_desc = "\n".join([
                        f"  - {cap.name}: {cap.description}"
                        f"\n    参数: {self._format_parameters(cap.parameters)}"
                        f"\n    示例: {cap.examples[0] if cap.examples else 'N/A'}"
                        for cap in tool.capabilities
                    ])
                    
                    desc = f"""
                            工具: {tool.name} (ID: {tool.tool_id})
                            类型: {tool.tool_type.value}
                            描述: {tool.description}

                            可用功能:
                            {capabilities_desc}

                            使用场景: 当需要{tool.description.lower()}时使用此工具
                            """
                    descriptions.append(desc)
                
                header = "\n" + "="*80 + "\n可用工具列表:\n" + "="*80
                footer = "\n" + "="*80
                return header + "\n" + "\n".join(descriptions) + footer
            except Exception as e:
                logger.error(f"Failed to generate tools description from MCP: {e}")
                return "生成工具描述失败"
        else:
            # 精简版本：直接生成工具描述
            return await self._generate_simple_tools_description()
    
    async def _generate_simple_tools_description(self) -> str:
        """生成简单的工具描述（精简版本）"""
        try:
            tools = await self.get_all_tools()
            if not tools:
                return "当前没有可用工具"
            
            descriptions = []
            for tool in tools:
                if tool.enabled:
                    descriptions.append(f"**{tool.name}** ({tool.tool_id}): {tool.description}")
            
            if not descriptions:
                return "当前没有启用的工具"
            
            return f"可用工具列表:\n" + "\n".join(descriptions)
        except Exception as e:
            logger.error(f"生成工具描述失败: {e}")
            return "工具描述生成失败"

    def _format_parameters(self, parameters: Dict[str, Any]) -> str:
        """格式化参数信息"""
        if not parameters:
            return "无"
        
        param_strs = []
        for param_name, param_info in parameters.items():
            if isinstance(param_info, dict):
                param_type = param_info.get("type", "any")
                required = "必填" if param_info.get("required", False) else "可选"
                param_strs.append(f"{param_name}({param_type}, {required})")
            else:
                param_strs.append(param_name)
        
        return ", ".join(param_strs)
    
    async def get_tool_usage_examples(self, tool_id: str) -> List[Dict[str, Any]]:
        """获取工具使用示例"""
        # 精简版本：返回简单的示例说明
        tool = await self.get_tool_by_id(tool_id)
        if tool:
            return f"请参考 {tool.name} 的文档说明"
        return "未找到工具使用示例"
    
    # ============ 工具执行API ============
    
    async def execute_tool(self, tool_id: str, action: str, parameters: Dict[str, Any]) -> ExecutionResult:
        """执行单个工具（精简版本）"""
        try:
            # 获取工具规格
            tool = await self.get_tool_by_id(tool_id)
            if not tool:
                return ExecutionResult(
                    success=False,
                    error_message=f"工具 {tool_id} 未找到",
                    error_type=ErrorType.TOOL_NOT_FOUND
                )
            
            # 根据工具类型执行
            if tool.tool_type == ToolType.MCP_SERVER and self.mcp_client:
                # MCP服务器工具通过MCP客户端执行
                return await self.mcp_client.call_tool(tool_id, action, parameters)
            else:
                # Function工具直接执行（简化实现）
                return ExecutionResult(
                    success=False,
                    error_message="精简版本暂不支持Function工具执行",
                    error_type=ErrorType.EXECUTION_ERROR
                )
                
        except Exception as e:
            logger.error(f"工具执行失败: {e}")
            return ExecutionResult(
                success=False,
                error_message=str(e),
                error_type=ErrorType.EXECUTION_ERROR
            )
    
    async def batch_execute_tools(self, tool_calls: List[Dict[str, Any]]) -> List[ExecutionResult]:
        """批量执行工具（精简版本）"""
        results = []
        for call in tool_calls:
            result = await self.execute_tool(
                call.get("tool_id", ""),
                call.get("action", ""),
                call.get("parameters", {})
            )
            results.append(result)
        return results
    
    async def get_tool_health_status(self, tool_id: str) -> Dict[str, Any]:
        """获取工具健康状态（精简版本）"""
        tool = await self.get_tool_by_id(tool_id)
        if tool:
            return {
                "tool_id": tool_id,
                "status": "healthy" if tool.enabled else "disabled",
                "last_check": time.time()
            }
        return {
            "tool_id": tool_id,
            "status": "not_found",
            "last_check": time.time()
        }
    
    # ============ 管理接口 ============
    
    async def get_library_stats(self) -> Dict[str, Any]:
        """获取工具库统计信息"""
        registry_stats = await self.tool_registry.get_registry_stats()
        # dispatcher_stats = await self.dispatcher.get_dispatcher_stats()  # 精简版本中已移除
        
        stats = {
            "registry": registry_stats,
            # "dispatcher": dispatcher_stats,  # 精简版本中已移除
            "initialized": self._initialized
        }
        
        # 添加动态MCP管理器统计信息
        if self.dynamic_mcp_manager:
            stats["dynamic_mcp"] = await self.get_dynamic_mcp_stats()
        
        return stats
    
    async def cleanup(self):
        """清理资源"""
        try:
            # 清理动态MCP管理器
            if self.dynamic_mcp_manager:
                await self.dynamic_mcp_manager.cleanup()
                logger.info("Dynamic MCP manager cleaned up")
            
            # 清理缓存管理器
            if self.cache_manager:
                await self.cache_manager.cleanup()
                logger.info("Cache manager cleaned up")
            
            # await self.dispatcher.cleanup_all_adapters()  # 精简版本中已移除
            logger.info("Tool library cleanup completed")
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
    
    # ============ 便利方法 ============
    
    async def quick_register_database_server(self) -> RegistrationResult:
        """快速注册数据库MCP Server"""
        from .interfaces import ToolCapability
        
        # 定义数据库服务器的能力
        capabilities = [
            ToolCapability(
                name="query",
                description="执行数据库查询",
                parameters={
                    "sql": {
                        "type": "string",
                        "description": "SQL查询语句",
                        "required": True
                    },
                    "database": {
                        "type": "string",
                        "description": "数据库名称",
                        "required": False
                    }
                },
                examples=[
                    {"sql": "SELECT * FROM users LIMIT 10"},
                    {"sql": "SELECT COUNT(*) FROM orders", "database": "main"}
                ]
            )
        ]
        
        # 创建MCP Server规范
        db_spec = MCPServerSpec(
            tool_id="database_server",
            name="数据库服务器",
            description="提供数据库查询和操作功能",
            tool_type=ToolType.MCP_SERVER,
            capabilities=capabilities,
            tags=["database", "sql", "query"],  # 使用简单标签系统
            endpoint="ws://localhost:8080/mcp",
            connection_params={"timeout": 30, "retry_count": 3}
        )
        
        return await self.register_mcp_server(db_spec)
    
    # ============ 上下文管理器支持 ============
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        await self.cleanup()