"""
MCP会话处理器
借鉴MCP Agent的标准化会话管理，提供类型安全的MCP协议支持
"""

import asyncio
import json
import logging
from typing import Optional, Dict, Any, List
from uuid import uuid4
from datetime import datetime

from ..exceptions import SessionError, MCPConnectionError

logger = logging.getLogger(__name__)


class MCPSessionHandler:
    """
    MCP会话处理器
    借鉴MCP Agent的Session设计，提供标准化的MCP协议支持
    """
    
    def __init__(self, server_id: str, connection_config: Dict[str, Any]):
        self.server_id = server_id
        self.session_id = str(uuid4())
        self.connection_config = connection_config
        
        # 连接状态
        self.is_connected = False
        self.is_initialized = False
        self.connection = None
        
        # 会话信息
        self.client_info = {
            "name": "agent-data-platform",
            "version": "1.0.0"
        }
        self.server_info = None
        self.capabilities = {}
        
        # 错误处理
        self.last_error = None
        self.retry_count = 0
        self.max_retries = 3
        
        # 统计信息
        self.created_at = datetime.now()
        self.last_activity = None
        self.request_count = 0
        
    async def connect(self) -> bool:
        """
        建立与MCP服务器的连接
        
        Returns:
            连接是否成功
        """
        try:
            if self.is_connected:
                logger.info(f"📡 会话 {self.session_id} 已连接到 {self.server_id}")
                return True
            
            # 根据连接类型建立连接
            connection_type = self.connection_config.get('type', 'websocket')
            
            if connection_type == 'websocket':
                await self._connect_websocket()
            elif connection_type == 'http':
                await self._connect_http()
            else:
                raise SessionError(
                    f"不支持的连接类型: {connection_type}",
                    session_id=self.session_id,
                    operation="connect"
                )
            
            self.is_connected = True
            self.last_activity = datetime.now()
            logger.info(f"✅ 成功连接到 MCP 服务器: {self.server_id}")
            return True
            
        except Exception as e:
            self.last_error = str(e)
            self.is_connected = False
            logger.error(f"❌ 连接 MCP 服务器失败: {self.server_id}, 错误: {e}")
            raise MCPConnectionError(
                f"连接服务器失败: {e}",
                server_id=self.server_id,
                port=self.connection_config.get('port')
            )
    
    async def initialize(self) -> Dict[str, Any]:
        """
        初始化MCP会话
        发送初始化请求并处理响应
        
        Returns:
            服务器初始化响应
        """
        try:
            if not self.is_connected:
                await self.connect()
            
            if self.is_initialized:
                logger.info(f"🔄 会话 {self.session_id} 已初始化")
                return self.server_info
            
            # 构建初始化请求
            init_request = {
                "jsonrpc": "2.0",
                "id": self.session_id,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "clientInfo": self.client_info,
                    "capabilities": {
                        "tools": True,
                        "resources": True,
                        "prompts": True
                    }
                }
            }
            
            # 发送初始化请求
            response = await self._send_request(init_request)
            
            if response and 'result' in response:
                self.server_info = response['result']
                self.capabilities = self.server_info.get('capabilities', {})
                self.is_initialized = True
                
                # 发送初始化完成通知
                await self._send_notification({
                    "jsonrpc": "2.0",
                    "method": "notifications/initialized"
                })
                
                logger.info(f"✅ MCP 会话初始化成功: {self.server_id}")
                return self.server_info
            else:
                raise SessionError(
                    "初始化响应格式错误",
                    session_id=self.session_id,
                    operation="initialize"
                )
                
        except Exception as e:
            self.last_error = str(e)
            self.is_initialized = False
            logger.error(f"❌ MCP 会话初始化失败: {e}")
            raise SessionError(
                f"会话初始化失败: {e}",
                session_id=self.session_id,
                operation="initialize"
            )
    
    async def ping(self) -> bool:
        """
        发送ping请求检查连接状态
        
        Returns:
            连接是否正常
        """
        try:
            if not self.is_connected:
                return False
            
            ping_request = {
                "jsonrpc": "2.0",
                "id": str(uuid4()),
                "method": "ping"
            }
            
            response = await self._send_request(ping_request, timeout=5.0)
            self.last_activity = datetime.now()
            
            return response is not None
            
        except Exception as e:
            logger.warning(f"⚠️ Ping 失败: {e}")
            return False
    
    async def list_tools(self) -> List[Dict[str, Any]]:
        """
        获取服务器支持的工具列表
        
        Returns:
            工具列表
        """
        try:
            if not self.is_initialized:
                await self.initialize()
            
            tools_request = {
                "jsonrpc": "2.0",
                "id": str(uuid4()),
                "method": "tools/list"
            }
            
            response = await self._send_request(tools_request)
            
            if response and 'result' in response:
                tools = response['result'].get('tools', [])
                logger.info(f"📋 获取到 {len(tools)} 个工具")
                return tools
            else:
                logger.warning("⚠️ 工具列表响应格式错误")
                return []
                
        except Exception as e:
            logger.error(f"❌ 获取工具列表失败: {e}")
            raise SessionError(
                f"获取工具列表失败: {e}",
                session_id=self.session_id,
                operation="list_tools"
            )
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        调用指定的工具
        
        Args:
            tool_name: 工具名称
            arguments: 工具参数
            
        Returns:
            工具执行结果
        """
        try:
            if not self.is_initialized:
                await self.initialize()
            
            tool_request = {
                "jsonrpc": "2.0",
                "id": str(uuid4()),
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": arguments
                }
            }
            
            logger.info(f"🔧 调用工具: {tool_name}")
            response = await self._send_request(tool_request)
            self.request_count += 1
            
            if response and 'result' in response:
                logger.info(f"✅ 工具调用成功: {tool_name}")
                return response['result']
            else:
                raise SessionError(
                    f"工具调用响应格式错误: {tool_name}",
                    session_id=self.session_id,
                    operation="call_tool"
                )
                
        except Exception as e:
            logger.error(f"❌ 工具调用失败: {tool_name}, 错误: {e}")
            raise SessionError(
                f"工具调用失败: {e}",
                session_id=self.session_id,
                operation="call_tool",
                details={"tool_name": tool_name, "arguments": arguments}
            )
    
    async def disconnect(self):
        """断开连接并清理资源"""
        try:
            if self.connection:
                if hasattr(self.connection, 'close'):
                    await self.connection.close()
                elif hasattr(self.connection, 'disconnect'):
                    await self.connection.disconnect()
            
            self.is_connected = False
            self.is_initialized = False
            self.connection = None
            
            logger.info(f"🔌 已断开 MCP 会话: {self.server_id}")
            
        except Exception as e:
            logger.warning(f"⚠️ 断开连接时出现错误: {e}")
    
    async def _connect_websocket(self):
        """建立WebSocket连接"""
        import websockets
        
        host = self.connection_config.get('host', 'localhost')
        port = self.connection_config.get('port', 8080)
        uri = f"ws://{host}:{port}"
        
        logger.info(f"🌐 正在连接 WebSocket: {uri}")
        
        try:
            self.connection = await websockets.connect(uri)
            logger.info(f"✅ WebSocket 连接成功: {uri}")
        except Exception as e:
            raise MCPConnectionError(
                f"WebSocket连接失败: {e}",
                server_id=self.server_id,
                port=port
            )
    
    async def _connect_http(self):
        """建立HTTP连接"""
        import httpx
        
        host = self.connection_config.get('host', 'localhost')
        port = self.connection_config.get('port', 8080)
        base_url = f"http://{host}:{port}"
        
        logger.info(f"🌐 正在连接 HTTP: {base_url}")
        
        try:
            self.connection = httpx.AsyncClient(base_url=base_url)
            
            # 测试连接
            response = await self.connection.get("/health")
            if response.status_code != 200:
                raise Exception(f"服务器响应错误: {response.status_code}")
                
            logger.info(f"✅ HTTP 连接成功: {base_url}")
        except Exception as e:
            raise MCPConnectionError(
                f"HTTP连接失败: {e}",
                server_id=self.server_id,
                port=port
            )
    
    async def _send_request(self, request: Dict[str, Any], timeout: float = 30.0) -> Optional[Dict[str, Any]]:
        """发送请求并等待响应"""
        try:
            if not self.connection:
                raise SessionError("连接未建立", session_id=self.session_id)
            
            if hasattr(self.connection, 'send'):
                # WebSocket连接
                await self.connection.send(json.dumps(request))
                
                # 等待响应
                response_data = await asyncio.wait_for(
                    self.connection.recv(), 
                    timeout=timeout
                )
                return json.loads(response_data)
                
            elif hasattr(self.connection, 'post'):
                # HTTP连接
                response = await self.connection.post(
                    "/rpc",
                    json=request,
                    timeout=timeout
                )
                return response.json()
            
            else:
                raise SessionError("不支持的连接类型", session_id=self.session_id)
                
        except asyncio.TimeoutError:
            raise SessionError(
                f"请求超时: {timeout}s",
                session_id=self.session_id,
                operation="send_request"
            )
        except Exception as e:
            raise SessionError(
                f"发送请求失败: {e}",
                session_id=self.session_id,
                operation="send_request"
            )
    
    async def _send_notification(self, notification: Dict[str, Any]):
        """发送通知（不需要响应）"""
        try:
            if not self.connection:
                raise SessionError("连接未建立", session_id=self.session_id)
            
            if hasattr(self.connection, 'send'):
                # WebSocket连接
                await self.connection.send(json.dumps(notification))
            elif hasattr(self.connection, 'post'):
                # HTTP连接
                await self.connection.post("/notification", json=notification)
                
        except Exception as e:
            logger.warning(f"⚠️ 发送通知失败: {e}")
    
    def get_session_info(self) -> Dict[str, Any]:
        """获取会话信息"""
        return {
            "session_id": self.session_id,
            "server_id": self.server_id,
            "is_connected": self.is_connected,
            "is_initialized": self.is_initialized,
            "created_at": self.created_at.isoformat(),
            "last_activity": self.last_activity.isoformat() if self.last_activity else None,
            "request_count": self.request_count,
            "server_info": self.server_info,
            "capabilities": self.capabilities,
            "last_error": self.last_error
        }
    
    def __str__(self):
        return f"MCPSession(server={self.server_id}, connected={self.is_connected})"