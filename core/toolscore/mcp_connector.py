"""
MCP 服务器连接器
用于直接连接和通信外部 MCP 服务器
"""

import asyncio
import json
import logging
import websockets
from typing import Dict, Any, Optional
import uuid

from .interfaces import ExecutionResult, ErrorType

logger = logging.getLogger(__name__)

class MCPServerConnector:
    """MCP 服务器连接器，用于直接连接外部 MCP 服务器"""
    
    def __init__(self, endpoint: str):
        self.endpoint = endpoint
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self._connected = False
        self._lock = asyncio.Lock()  # 添加锁来防止并发问题
        logger.info(f"MCPServerConnector initialized for {endpoint}")
    
    async def connect(self):
        """连接到 MCP 服务器"""
        if self._connected and self.websocket:
            return
        
        try:
            logger.info(f"Connecting to MCP server at {self.endpoint}...")
            logger.info(f"WebSocket库版本: {websockets.__version__}")
            
            # 添加更多调试信息
            import websockets.legacy.client as websockets_client
            self.websocket = await websockets_client.connect(
                self.endpoint,
                ping_interval=20,
                ping_timeout=10,
                close_timeout=10
            )
            self._connected = True
            logger.info(f"Successfully connected to MCP server at {self.endpoint}")
        except Exception as e:
            logger.error(f"Failed to connect to MCP server at {self.endpoint}: {e}")
            logger.error(f"错误类型: {type(e).__name__}")
            logger.error(f"错误详情: {str(e)}")
            import traceback
            logger.error(f"完整堆栈跟踪:\n{traceback.format_exc()}")
            self._connected = False
            raise
    
    async def disconnect(self):
        """断开连接"""
        if self.websocket:
            try:
                await self.websocket.close()
            except Exception as e:
                logger.warning(f"Error closing websocket: {e}")
            self.websocket = None
            self._connected = False
    
    async def execute_tool_action(self, tool_id: str, action: str, parameters: Dict[str, Any]) -> ExecutionResult:
        """执行工具动作"""
        async with self._lock:  # 使用锁防止并发访问
            if not self._connected:
                await self.connect()
            
            if not self.websocket:
                return ExecutionResult(
                    success=False,
                    error_message="Not connected to MCP server",
                    error_type=ErrorType.NETWORK_ERROR
                )
            
            request_id = str(uuid.uuid4())
            request = {
                "type": "execute_tool_action",
                "request_id": request_id,
                "tool_id": tool_id,
                "action": action,
                "parameters": parameters
            }
            
            try:
                # 发送请求
                await self.websocket.send(json.dumps(request))
                
                # 等待响应
                response_str = await self.websocket.recv()
                response = json.loads(response_str)
                
                # 解析响应
                if response.get("type") == "execute_tool_action_response":
                    result_data = response.get("result", {})
                    
                    if result_data.get("success", False):
                        return ExecutionResult(
                            success=True,
                            data=result_data.get("data"),
                            execution_time=result_data.get("execution_time", 0.0)
                        )
                    else:
                        # 处理错误
                        error_type = ErrorType.TOOL_ERROR
                        if result_data.get("error_type"):
                            try:
                                error_type = ErrorType(result_data["error_type"])
                            except (ValueError, KeyError):
                                error_type = ErrorType.TOOL_ERROR
                        
                        return ExecutionResult(
                            success=False,
                            error_message=result_data.get("error_message", result_data.get("error", "Unknown error")),
                            error_type=error_type
                        )
                else:
                    return ExecutionResult(
                        success=False,
                        error_message=f"Unexpected response type: {response.get('type')}",
                        error_type=ErrorType.SYSTEM_ERROR
                    )
            
            except websockets.exceptions.ConnectionClosed:
                logger.warning("Connection to MCP server closed")
                self._connected = False
                return ExecutionResult(
                    success=False,
                    error_message="Connection to MCP server closed",
                    error_type=ErrorType.NETWORK_ERROR
                )
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse response: {e}")
                return ExecutionResult(
                    success=False,
                    error_message=f"Invalid JSON response: {e}",
                    error_type=ErrorType.SYSTEM_ERROR
                )
            except Exception as e:
                logger.error(f"Error executing tool action: {e}")
                return ExecutionResult(
                    success=False,
                    error_message=str(e),
                    error_type=ErrorType.SYSTEM_ERROR
                )
    
    async def cleanup(self):
        """清理资源"""
        await self.disconnect()


class MCPServerRegistry:
    """MCP 服务器注册表，管理多个 MCP 服务器连接"""
    
    def __init__(self):
        self.connectors: Dict[str, MCPServerConnector] = {}
        logger.info("MCPServerRegistry initialized")
    
    def register_server(self, tool_id: str, endpoint: str):
        """注册 MCP 服务器"""
        if tool_id not in self.connectors:
            self.connectors[tool_id] = MCPServerConnector(endpoint)
            logger.info(f"Registered MCP server {tool_id} at {endpoint}")
    
    async def execute_tool(self, tool_id: str, action: str, parameters: Dict[str, Any]) -> ExecutionResult:
        """执行工具"""
        connector = self.connectors.get(tool_id)
        if not connector:
            return ExecutionResult(
                success=False,
                error_message=f"MCP server for tool {tool_id} not found",
                error_type=ErrorType.TOOL_ERROR
            )
        
        return await connector.execute_tool_action(tool_id, action, parameters)
    
    async def cleanup(self):
        """清理所有连接"""
        for connector in self.connectors.values():
            await connector.cleanup()
        self.connectors.clear() 