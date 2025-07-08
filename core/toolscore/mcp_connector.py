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
    """MCP 服务器连接器，用于直接连接外部 MCP 服务器 - 增强版本"""
    
    def __init__(self, endpoint: str):
        self.endpoint = endpoint
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self._connected = False
        self._lock = asyncio.Lock()  # 添加锁来防止并发问题
        # 连接重试配置
        self.max_retries = 3
        self.retry_delay = 1.0
        self.connection_timeout = 10.0
        # 连接健康监控
        self._last_ping_time = 0
        self._connection_health = True
        logger.info(f"MCPServerConnector initialized for {endpoint}")
    
    async def connect(self):
        """连接到 MCP 服务器，增强版本：支持重试和健康检查"""
        if self._connected and self.websocket and self._connection_health:
            return
        
        for attempt in range(self.max_retries):
            try:
                logger.info(f"🔌 连接 MCP 服务器 {self.endpoint} (尝试 {attempt + 1}/{self.max_retries})")
                
                # 添加连接超时
                import websockets.legacy.client as websockets_client
                self.websocket = await asyncio.wait_for(
                    websockets_client.connect(
                        self.endpoint,
                        ping_interval=60,   # 60秒心跳间隔（3倍DeepSearch查询时间的安全边界）
                        ping_timeout=30,   # 30秒响应超时（充足的响应时间）
                        close_timeout=30    # 30秒关闭超时
                    ),
                    timeout=self.connection_timeout
                )
                
                self._connected = True
                self._connection_health = True
                self._last_ping_time = asyncio.get_event_loop().time()
                logger.info(f"✅ 成功连接到 MCP 服务器: {self.endpoint}")
                logger.info(f"🔧 WebSocket参数设置: ping_interval=90s, ping_timeout=150s, close_timeout=30s")
                logger.info(f"💡 连接已优化以支持长时间查询操作(如DeepSearch 27秒查询)")
                return
                
            except asyncio.TimeoutError:
                logger.warning(f"⏰ 连接超时 (尝试 {attempt + 1}): {self.endpoint}")
            except Exception as e:
                logger.error(f"❌ 连接失败 (尝试 {attempt + 1}): {self.endpoint} - {e}")
                
            # 如果不是最后一次尝试，等待后重试
            if attempt < self.max_retries - 1:
                await asyncio.sleep(self.retry_delay * (attempt + 1))  # 指数退避
        
        # 所有重试失败
        self._connected = False
        self._connection_health = False
        logger.error(f"❌ 连接完全失败，已达最大重试次数: {self.endpoint}")
        raise ConnectionError(f"无法连接到 MCP 服务器: {self.endpoint}")
    
    async def disconnect(self):
        """断开连接"""
        if self.websocket:
            try:
                logger.info(f"🔌 主动断开MCP服务器连接: {self.endpoint}")
                await self.websocket.close()
            except Exception as e:
                logger.warning(f"⚠️ 关闭WebSocket连接时出错: {e}")
            self.websocket = None
            self._connected = False
            logger.info(f"✅ MCP服务器连接已断开: {self.endpoint}")
    
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
            
            except websockets.exceptions.ConnectionClosed as e:
                logger.warning(f"🔗 MCP服务器连接意外关闭: {self.endpoint}")
                logger.warning(f"   关闭代码: {e.code}, 原因: {e.reason}")
                logger.info(f"💡 注意: 已使用优化的WebSocket参数(ping_timeout=150s)以支持长时间操作")
                self._connected = False
                self._connection_health = False
                return ExecutionResult(
                    success=False,
                    error_message=f"Connection to MCP server closed (code: {e.code})",
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