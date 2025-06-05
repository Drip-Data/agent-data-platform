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
    
    async def unregister_tool(self, tool_id: str) -> bool:
        """注销工具"""
        return await self.tool_registry.unregister_tool(tool_id)
    
    # ============ 工具查询API ============
    
    async def get_all_tools(self) -> List[ToolSpec]:
        """获取所有可用工具"""
        return await self.tool_registry.get_all_tools()
    
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
        return await self.description_engine.generate_all_tools_description_for_agent()
    
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
        
        return {
            "registry": registry_stats,
            "dispatcher": dispatcher_stats,
            "initialized": self._initialized
        }
    
    async def cleanup(self):
        """清理资源"""
        try:
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