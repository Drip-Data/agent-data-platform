"""
工具适配器实现
提供Function Tool和MCP Server的统一执行接口
"""

import logging
import asyncio
import importlib
import time
import json
from typing import Dict, Any, Optional, Union
from abc import ABC, abstractmethod
from core.toolscore.mcp_client import MCPToolClient # 导入MCPToolClient

from .interfaces import (
    BaseToolAdapter, ExecutionResult, FunctionToolSpec, MCPServerSpec
)

logger = logging.getLogger(__name__)


class FunctionToolAdapter(BaseToolAdapter):
    """Function Tool适配器 - 支持内嵌到Runtime的工具"""
    
    def __init__(self, tool_spec: FunctionToolSpec):
        self.tool_spec = tool_spec
        self._tool_instance = None
        self._initialized = False
    
    async def _initialize_tool(self):
        """延迟初始化工具实例"""
        if self._initialized:
            return
        
        try:
            # 优先使用function_handler
            if self.tool_spec.function_handler:
                self._tool_instance = self.tool_spec.function_handler
                self._initialized = True
                logger.info(f"Initialized Function Tool with handler: {self.tool_spec.name}")
                return
            
            # 动态导入工具模块
            if self.tool_spec.module_path:
                module = importlib.import_module(self.tool_spec.module_path)
                
                if self.tool_spec.class_name:
                    # 实例化类
                    tool_class = getattr(module, self.tool_spec.class_name)
                    self._tool_instance = tool_class(**self.tool_spec.init_params)
                else:
                    # 直接使用模块中的工具实例
                    tool_name = self.tool_spec.name.lower()
                    self._tool_instance = getattr(module, f"get_{tool_name}_tool")()
            
            self._initialized = True
            logger.info(f"Initialized Function Tool: {self.tool_spec.name}")
            
        except Exception as e:
            logger.error(f"Failed to initialize Function Tool {self.tool_spec.name}: {e}")
            raise
    
    async def execute(self, tool_id: str, action: str, parameters: Dict[str, Any]) -> ExecutionResult:
        """执行Function Tool操作"""
        start_time = time.time()
        
        try:
            await self._initialize_tool()
            
            if not self._tool_instance:
                return ExecutionResult(
                    success=False,
                    error_type="InitializationError",
                    error_message="Tool instance not initialized"
                )
            
            # 如果是function_handler，直接调用
            if self.tool_spec.function_handler:
                if asyncio.iscoroutinefunction(self._tool_instance):
                    result = await self._tool_instance(action, parameters)
                else:
                    result = self._tool_instance(action, parameters)
            
            # 优先使用统一的execute接口
            elif hasattr(self._tool_instance, 'execute'):
                method = getattr(self._tool_instance, 'execute')
                
                if asyncio.iscoroutinefunction(method):
                    result = await method(action, parameters)
                else:
                    result = method(action, parameters)
            
            # 如果没有统一execute接口，尝试直接调用action方法
            elif hasattr(self._tool_instance, action):
                method = getattr(self._tool_instance, action)
                
                if asyncio.iscoroutinefunction(method):
                    result = await method(**parameters)
                else:
                    result = method(**parameters)
            
            else:
                return ExecutionResult(
                    success=False,
                    error_type="MethodNotFound",
                    error_message=f"Action '{action}' not supported by tool {self.tool_spec.name}"
                )
            
            execution_time = time.time() - start_time
            
            # 解析结果格式
            if isinstance(result, dict):
                success = result.get('success', True)
                data = result.get('data', result)
                error_type = result.get('error_type')
                error_message = result.get('error_message')
            else:
                success = True
                data = result
                error_type = None
                error_message = None
            
            return ExecutionResult(
                success=success,
                data=data,
                error_type=error_type,
                error_message=error_message,
                execution_time=execution_time,
                metadata={
                    "tool_type": "function",
                    "tool_id": tool_id,
                    "action": action
                }
            )
            
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"Function Tool execution failed: {e}")
            
            return ExecutionResult(
                success=False,
                error_type="ExecutionError",
                error_message=str(e),
                execution_time=execution_time,
                metadata={
                    "tool_type": "function",
                    "tool_id": tool_id,
                    "action": action
                }
            )
    
    async def health_check(self) -> bool:
        """健康检查"""
        try:
            await self._initialize_tool()
            return self._tool_instance is not None
        except Exception:
            return False
    
    async def cleanup(self):
        """清理资源"""
        if self._tool_instance and hasattr(self._tool_instance, 'cleanup'):
            try:
                if asyncio.iscoroutinefunction(self._tool_instance.cleanup):
                    await self._tool_instance.cleanup()
                else:
                    self._tool_instance.cleanup()
            except Exception as e:
                logger.error(f"Error during tool cleanup for {self.tool_spec.name}: {e}")
        
        self._tool_instance = None
        self._initialized = False


class MCPServerAdapter(BaseToolAdapter):
    """MCP Server适配器 - 支持远程MCP协议调用"""
    
    def __init__(self, server_spec: MCPServerSpec, mcp_client: Optional[MCPToolClient] = None):
        self.server_spec = server_spec
        self._mcp_client = mcp_client # 保存MCPToolClient实例
        self._connected = False
    
    async def _initialize_connection(self):
        """初始化MCP连接"""
        if self._connected:
            return
        
        try:
            # 这里应该根据MCP协议规范实现客户端连接
            # 使用MCPToolClient进行连接
            if not self._mcp_client:
                raise ValueError("MCPToolClient instance not provided to MCPServerAdapter.")
            
            # MCPToolClient的连接由其自身管理，这里只需确保它已初始化
            # 实际的连接逻辑在MCPToolClient内部
            self._connected = True # 假设MCPToolClient已连接或能自动连接
            logger.info(f"MCPToolClient will handle connection for MCP Server: {self.server_spec.name}")
                    
        except Exception as e:
            logger.error(f"Failed to connect to MCP Server {self.server_spec.name}: {e}")
            raise
    
    async def execute(self, tool_id: str, action: str, parameters: Dict[str, Any]) -> ExecutionResult:
        """执行MCP Server操作"""
        start_time = time.time()
        
        try:
            if not self._mcp_client:
                return ExecutionResult(
                    success=False,
                    error_type="ConnectionError",
                    error_message="MCPToolClient instance not provided to MCPServerAdapter."
                )
            
            # 使用MCPToolClient执行工具调用
            # MCPToolClient的execute_tool方法已经处理了WebSocket通信和结果解析
            result = await self._mcp_client.execute_tool(tool_id, action, parameters)
            
            # MCPToolClient返回的已经是ExecutionResult对象，直接返回即可
            return result
            
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"MCP Server execution failed for tool {tool_id} action {action}: {e}")
            
            return ExecutionResult(
                success=False,
                error_type="MCPExecutionError",
                error_message=str(e),
                execution_time=execution_time,
                metadata={
                    "tool_type": "mcp_server",
                    "tool_id": tool_id,
                    "action": action
                }
            )
    
    async def health_check(self) -> bool:
        """健康检查"""
        try:
            await self._initialize_connection()
            return self._connected
        except Exception:
            return False
    
    async def cleanup(self):
        """清理资源"""
        if self._mcp_client:
            try:
                await self._mcp_client.disconnect() # 调用MCPToolClient的disconnect方法
            except Exception as e:
                logger.error(f"Error during MCPToolClient disconnect for {self.server_spec.name}: {e}")
        self._connected = False