"""
统一工具库
纯粹的工具管理平台，为执行环境中的自主Agent提供工具注册、发现、描述和调用服务
"""

import logging
import asyncio
from typing import Dict, Any, List, Optional

from .interfaces import (
    ToolSpec, FunctionToolSpec, MCPServerSpec,
    ExecutionResult, RegistrationResult, ToolType
)
from .tool_registry import ToolRegistry
from .description_engine import DescriptionEngine
from .unified_dispatcher import UnifiedDispatcher

logger = logging.getLogger(__name__)


class UnifiedToolLibrary:
    """
    统一工具库 - API网关
    
    职责分离原则：
    - 工具库专注工具管理，Agent专注智能决策
    - 纯服务化：仅提供工具管理和查询API，不做智能推荐
    - 无硬编码规则：不使用关键词匹配等硬编码逻辑
    """
    
    def __init__(self, mcp_client: Optional[Any] = None): # 添加mcp_client参数
        # 初始化核心组件
        self.tool_registry = ToolRegistry()
        self.description_engine = DescriptionEngine(self.tool_registry)
        self.dispatcher = UnifiedDispatcher(self.tool_registry, mcp_client) # 将mcp_client传递给UnifiedDispatcher
        self.mcp_client = mcp_client  # 保存MCP客户端引用
        
        # 动态MCP管理器（延迟初始化）
        self.dynamic_mcp_manager = None
        
        self._initialized = False
        logger.info("Unified Tool Library initialized - Pure service mode")
    
    async def initialize(self):
        """初始化工具库"""
        if self._initialized:
            return
        
        try:
            # 初始化各组件
            await self.tool_registry.initialize()
            await self.description_engine.initialize()
            await self.dispatcher.initialize()
            
            # 初始化动态MCP管理器
            from .dynamic_mcp_manager import DynamicMCPManager
            self.dynamic_mcp_manager = DynamicMCPManager(self)
            await self.dynamic_mcp_manager.initialize()
            
            logger.info("Tool library initialization completed")
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

    async def register_external_mcp_server(self, server_info: Dict[str, Any]) -> RegistrationResult:
        """通过统一信息注册外部MCP服务器"""
        required_fields = ["name", "endpoint", "capabilities"]
        for field in required_fields:
            if field not in server_info:
                return RegistrationResult(success=False, error=f"Missing field: {field}")

        capabilities = []
        for cap in server_info.get("capabilities", []):
            if isinstance(cap, ToolCapability):
                capabilities.append(cap)
            elif isinstance(cap, dict) and "name" in cap:
                capabilities.append(
                    ToolCapability(
                        name=cap.get("name", ""),
                        description=cap.get("description", ""),
                        parameters=cap.get("parameters", {}),
                        examples=cap.get("examples", []),
                    )
                )
            else:
                return RegistrationResult(success=False, error="Invalid capability format")

        tool_id = server_info.get("tool_id") or server_info["name"].lower().replace(" ", "_")

        server_spec = MCPServerSpec(
            tool_id=tool_id,
            name=server_info["name"],
            description=server_info.get("description", ""),
            tool_type=ToolType.MCP_SERVER,
            capabilities=capabilities,
            tags=server_info.get("tags", []),
            endpoint=server_info["endpoint"],
            connection_params=server_info.get("connection_params", {}),
            server_config=server_info.get("server_config", {}),
        )

        result = await self.register_mcp_server(server_spec)

        if result.success and self.dynamic_mcp_manager and self.dynamic_mcp_manager._storage_initialized:
            try:
                install_data = {
                    "success": True,
                    "server_id": tool_id,
                    "endpoint": server_info["endpoint"],
                    "container_id": None,
                    "port": None,
                }
                await self.dynamic_mcp_manager.persistent_storage.save_mcp_server(server_spec, install_data)
            except Exception as e:
                logger.warning(f"Failed to persist external MCP server {server_spec.name}: {e}")

        return result
    
    async def unregister_tool(self, tool_id: str) -> bool:
        """注销工具"""
        return await self.tool_registry.unregister_tool(tool_id)
    
    # ============ 动态MCP管理API ============
    
    async def search_and_install_mcp_server(self, query: str, capability_tags: List[str] = None) -> Dict[str, Any]:
        """搜索并安装MCP服务器"""
        if not self.dynamic_mcp_manager:
            return {
                "success": False,
                "error": "Dynamic MCP manager not initialized"
            }
        
        try:
            # 搜索候选服务器
            candidates = await self.dynamic_mcp_manager.search_mcp_servers(query, capability_tags)
            
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
            
            if hasattr(self.dynamic_mcp_manager, 'persistent_storage') and self.dynamic_mcp_manager._storage_initialized:
                storage_stats = await self.dynamic_mcp_manager.persistent_storage.get_storage_stats()
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
        return await self.description_engine.generate_tool_description_for_agent(tool_id)
    
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
            # 没有MCP客户端，使用description_engine
            return await self.description_engine.generate_all_tools_description_for_agent()
    
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
        return await self.description_engine.get_tool_usage_examples(tool_id)
    
    # ============ 工具执行API ============
    
    async def execute_tool(self, tool_id: str, action: str, parameters: Dict[str, Any]) -> ExecutionResult:
        """执行单个工具"""
        return await self.dispatcher.execute_tool(tool_id, action, parameters)
    
    async def batch_execute_tools(self, tool_calls: List[Dict[str, Any]]) -> List[ExecutionResult]:
        """批量执行工具"""
        return await self.dispatcher.batch_execute_tools(tool_calls)
    
    async def get_tool_health_status(self, tool_id: str) -> Dict[str, Any]:
        """获取工具健康状态"""
        return await self.dispatcher.get_tool_health_status(tool_id)
    
    # ============ 管理接口 ============
    
    async def get_library_stats(self) -> Dict[str, Any]:
        """获取工具库统计信息"""
        registry_stats = await self.tool_registry.get_registry_stats()
        dispatcher_stats = await self.dispatcher.get_dispatcher_stats()
        
        stats = {
            "registry": registry_stats,
            "dispatcher": dispatcher_stats,
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
            
            await self.dispatcher.cleanup_all_adapters()
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