"""
MCP 服务器连接器
用于直接连接和通信外部 MCP 服务器
"""

import asyncio
import json
import logging
import aiohttp
import aiohttp.client_ws
import websockets
from typing import Dict, Any, Optional
import uuid

from core.toolscore.interfaces.toolscore_interfaces import ExecutionResult, ErrorType

logger = logging.getLogger(__name__)

class MCPServerConnector:
    """MCP 服务器连接器，用于直接连接外部 MCP 服务器"""
    
    def __init__(self, endpoint: str):
        self.endpoint = endpoint
        self.session: Optional[aiohttp.ClientSession] = None
        self.websocket: Optional[aiohttp.client_ws.ClientWebSocketResponse] = None
        self._connected = False
        logger.info(f"MCPServerConnector initialized for {endpoint}")
    
    async def connect(self):
        """连接到 MCP 服务器"""
        if self._connected and self.websocket and not self.websocket.closed:
            return
        
        try:
            logger.info(f"Connecting to MCP server at {self.endpoint}...")
            if self.session is None or self.session.closed:
                self.session = aiohttp.ClientSession()
            
            self.websocket = await self.session.ws_connect(self.endpoint)
            self._connected = True
            logger.info(f"Successfully connected to MCP server at {self.endpoint}")
        except Exception as e:
            logger.error(f"Failed to connect to MCP server at {self.endpoint}: {e}")
            self._connected = False
            if self.session and not self.session.closed:
                await self.session.close()
            raise
    
    async def disconnect(self):
        """断开连接"""
        if self.websocket and not self.websocket.closed:
            try:
                await self.websocket.close()
            except Exception as e:
                logger.warning(f"Error closing websocket: {e}")
            self.websocket = None
        if self.session and not self.session.closed:
            try:
                await self.session.close()
            except Exception as e:
                logger.warning(f"Error closing aiohttp session: {e}")
            self.session = None
        self._connected = False
    
    async def execute_tool_action(self, tool_id: str, action: str, parameters: Dict[str, Any]) -> ExecutionResult:
        """执行工具动作"""
        if not self._connected or (self.websocket and self.websocket.closed):
            await self.connect()
        
        if not self.websocket or self.websocket.closed:
            return ExecutionResult(
                success=False,
                error_message="Not connected to MCP server or connection closed",
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
            await self.websocket.send_str(json.dumps(request))
            
            # 等待响应
            response_str = await self.websocket.receive_str()
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
                        error_message=result_data.get("error", "Unknown error"),
                        error_type=error_type
                    )
            else:
                return ExecutionResult(
                    success=False,
                    error_message=f"Unexpected response type: {response.get('type')}",
                    error_type=ErrorType.SYSTEM_ERROR
                )
        
        except aiohttp.client_exceptions.ClientConnectionError as e:
            logger.warning(f"Connection to MCP server lost: {e}")
            self._connected = False
            return ExecutionResult(
                success=False,
                error_message=f"Connection to MCP server lost: {e}",
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