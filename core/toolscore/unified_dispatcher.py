"""
统一工具调度器
根据工具类型和规范，选择合适的适配器进行执行
"""

import logging
import asyncio
from typing import Dict, Any, Optional, List
import time

from .interfaces import ExecutionResult, ToolType
from .tool_registry import ToolRegistry
from .adapters import FunctionToolAdapter, MCPServerAdapter
from core.toolscore.mcp_client import MCPToolClient # 导入MCPToolClient

logger = logging.getLogger(__name__)


class UnifiedDispatcher:
    """统一工具调度器"""
    
    def __init__(self, tool_registry: ToolRegistry, mcp_client: Optional[MCPToolClient] = None):
        self.tool_registry = tool_registry
        self.mcp_client = mcp_client # 保存mcp_client
        
    async def initialize(self):
        """初始化调度器"""
        logger.info("Unified dispatcher initialized")
        
    async def execute_tool(self, tool_id: str, action: str, parameters: Dict[str, Any]) -> ExecutionResult:
        """执行工具调用"""
        start_time = time.time()
        
        try:
            # 首先尝试从本地注册表获取工具规范
            tool_spec = await self.tool_registry.get_tool_spec(tool_id)
            
            if tool_spec:
                # 本地有该工具，直接执行
                logger.info(f"Executing local tool {tool_spec.name} (ID: {tool_id}) action: {action}")
                
                # 检查工具是否启用
                if not tool_spec.enabled:
                    return ExecutionResult(
                        success=False,
                        error_type="ToolDisabled",
                        error_message=f"Tool {tool_spec.name} is disabled"
                    )
                
                # 创建适配器并执行
                adapter = await self._create_adapter(tool_id, tool_spec)
                if not adapter:
                    return ExecutionResult(
                        success=False,
                        error_type="AdapterError",
                        error_message=f"Failed to create adapter for tool {tool_spec.name}"
                    )
                
                # 执行工具调用
                result = await adapter.execute(tool_id, action, parameters)
                
                # 更新工具指标
                await self.tool_registry.update_tool_metrics(
                    tool_id, result.success, result.execution_time
                )
                
                # 清理适配器
                await adapter.cleanup()
                
                return result
                
            elif self.mcp_client:
                # 本地没有该工具，尝试通过MCP客户端执行
                logger.info(f"Tool {tool_id} not found locally, trying MCP client for action: {action}")
                try:
                    result = await self.mcp_client.execute_tool(tool_id, action, parameters)
                    return result
                except Exception as e:
                    logger.error(f"MCP client execution failed: {e}")
                    return ExecutionResult(
                        success=False,
                        error_type="MCPClientError",
                        error_message=f"MCP client execution failed: {str(e)}",
                        execution_time=time.time() - start_time,
                        metadata={"tool_id": tool_id, "action": action}
                    )
            else:
                # 既没有本地工具，也没有MCP客户端
                return ExecutionResult(
                    success=False,
                    error_type="ToolNotFound",
                    error_message=f"Tool with ID {tool_id} not found in local registry or MCP client"
                )
            
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"Tool execution failed: {e}")
            
            return ExecutionResult(
                success=False,
                error_type="DispatcherError",
                error_message=str(e),
                execution_time=execution_time,
                metadata={"tool_id": tool_id, "action": action}
            )
    
    async def _create_adapter(self, tool_id: str, tool_spec) -> Optional[Any]:
        """创建工具适配器"""
        try:
            if tool_spec.tool_type == ToolType.FUNCTION:
                adapter = FunctionToolAdapter(tool_spec)
            elif tool_spec.tool_type == ToolType.MCP_SERVER:
                adapter = MCPServerAdapter(tool_spec, self.mcp_client) # 传递mcp_client
            else:
                logger.error(f"Unsupported tool type: {tool_spec.tool_type}")
                return None
            
            logger.info(f"Created adapter for tool {tool_spec.name} (type: {tool_spec.tool_type.value})")
            return adapter
            
        except Exception as e:
            logger.error(f"Failed to create adapter for tool {tool_spec.name}: {e}")
            return None
    
    async def batch_execute_tools(self, tool_calls: List[Dict[str, Any]]) -> List[ExecutionResult]:
        """批量执行工具调用"""
        tasks = []
        
        for call in tool_calls:
            tool_id = call.get('tool_id')
            action = call.get('action')
            parameters = call.get('parameters', {})
            
            if tool_id and action:
                tasks.append(self.execute_tool(tool_id, action, parameters))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 将所有结果（包括异常）封装为ExecutionResult
        processed_results: List[ExecutionResult] = []
        for res in results:
            if isinstance(res, ExecutionResult):
                processed_results.append(res)
            elif isinstance(res, Exception):
                processed_results.append(ExecutionResult(
                    success=False,
                    error_type="BatchExecutionError",
                    error_message=str(res),
                    metadata={"original_exception": str(type(res).__name__)}
                ))
            else:
                # 处理 unexpected types, though asyncio.gather with return_exceptions=True should return only results or exceptions
                processed_results.append(ExecutionResult(
                    success=False,
                    error_type="UnexpectedResultType",
                    error_message=f"Unexpected result type in batch execution: {type(res)}",
                    metadata={"raw_result": str(res)}
                ))
        return processed_results
    
    async def get_tool_health_status(self, tool_id: str) -> Dict[str, Any]:
        """获取工具健康状态"""
        tool_spec = await self.tool_registry.get_tool_spec(tool_id)
        if not tool_spec:
            return {"healthy": False, "error": "Tool not found"}
        
        try:
            # 直接创建适配器进行健康检查
            adapter = await self._create_adapter(tool_id, tool_spec)
            if adapter:
                healthy = await adapter.health_check()
                await adapter.cleanup() # 健康检查后清理适配器
                return {
                    "healthy": healthy,
                    "tool_name": tool_spec.name,
                    "tool_type": tool_spec.tool_type.value,
                    "enabled": tool_spec.enabled
                }
            else:
                return {"healthy": False, "error": "Failed to create adapter"}
                
        except Exception as e:
            return {"healthy": False, "error": str(e)}
    
    async def cleanup_all_adapters(self):
        """清理所有适配器 (现在是空操作，因为适配器不再缓存)"""
        logger.info("All adapters cleaned up (no-op as adapters are not cached)")
    
    async def get_dispatcher_stats(self) -> Dict[str, Any]:
        """获取调度器统计信息"""
        # 不再有活动适配器和缓存统计
        return {
            "active_adapters": 0,
            "adapter_types": {},
            "cache_ttl": 0
        }