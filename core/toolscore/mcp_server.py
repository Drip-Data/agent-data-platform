import asyncio
import json
import logging
import websockets.legacy.server as websockets_server
import websockets.legacy.client as websockets_client
from typing import Dict, Any, Callable, Optional, List, Union
from websockets.legacy.client import WebSocketClientProtocol
from websockets.legacy.server import WebSocketServerProtocol
from websockets.exceptions import ConnectionClosedOK, ConnectionClosedError, InvalidURI

from uuid import uuid4
import os

# 移除了本地调用路径，强制使用WebSocket

from .interfaces import ToolSpec, ToolType, RegistrationResult, ExecutionResult, ToolCapability, MCPServerSpec, FunctionToolSpec, ErrorType
from .unified_tool_library import UnifiedToolLibrary

logger = logging.getLogger(__name__)

class MCPServer:
    """
    MCP (Model Context Protocol) Server
    用于接收工具注册和工具调用请求
    """
    
    def __init__(self,
                 server_name: str,
                 server_id: str,
                 description: str,
                 capabilities: List[ToolCapability],
                 tool_type: ToolType,
                 endpoint: str, # 本MCP Server的WebSocket地址
                 toolscore_endpoint: Optional[str] = None, # UnifiedToolLibrary MCP Server的地址
                 bind_port: Optional[int] = None, # 新增：用于动态端口分配
                 server_started_event: Optional[asyncio.Event] = None # 新增：用于通知服务器启动完成
                 ):
        self.server_name = server_name
        self.server_id = server_id
        self.description = description
        self.capabilities = capabilities
        self.tool_type = tool_type
        self.endpoint = endpoint
        self.toolscore_endpoint = toolscore_endpoint
        self.bind_port = bind_port # 存储动态分配的端口
        self.server_started_event = server_started_event # 存储Event
        self.websocket_server = None
        self.tool_action_handler: Optional[Callable[[str, Dict[str, Any]], Any]] = None
        self.toolscore_client: Optional[WebSocketClientProtocol] = None # 使用 legacy WebSocket 类型
        self.toolscore_registration_task: Optional[asyncio.Task] = None
        self._is_healthy: bool = False # 新增：服务健康状态
        self._startup_error_message: Optional[str] = None # 新增：启动错误信息
        self._is_running: bool = False # 新增：运行状态标志

        # 如果是toolscore本身，则不连接toolscore_endpoint
        if self.server_name == "toolscore":
            self.unified_tool_library = UnifiedToolLibrary()
        else:
            self.unified_tool_library = None # 其他MCP Server不直接使用UnifiedToolLibrary实例

    def register_tool_action_handler(self, handler: Callable[[str, Dict[str, Any]], Any]):
        """注册处理工具动作的函数"""
        self.tool_action_handler = handler

    async def _handle_message(self, websocket: WebSocketServerProtocol, message: Union[str, bytes]): # 允许 str 或 bytes
        """处理接收到的WebSocket消息"""
        try:
            if isinstance(message, bytes):
                message = message.decode('utf-8') # 确保消息是字符串
            request = json.loads(message)
            request_type = request.get("type")
            request_id = request.get("request_id")

            if request_type == "register_tool" and self.server_name == "toolscore":
                # 只有toolscore才处理工具注册请求
                tool_spec_data = request.get("tool_spec")
                if tool_spec_data:
                    # 辅助函数：从字典创建 ToolCapability 列表
                    def _create_capabilities(caps_data: List[Dict[str, Any]]) -> List[ToolCapability]:
                        return [ToolCapability(**cap) for cap in caps_data]

                    tool_type_str = tool_spec_data.pop("tool_type", None) # 移除并获取 tool_type
                    capabilities_data = tool_spec_data.pop("capabilities", []) # 移除并获取 capabilities
                    capabilities = _create_capabilities(capabilities_data)

                    if tool_type_str == ToolType.FUNCTION.value:
                        tool_spec = FunctionToolSpec(capabilities=capabilities, tool_type=ToolType.FUNCTION, **tool_spec_data)
                        if self.unified_tool_library: # 确保实例存在
                            result = await self.unified_tool_library.register_function_tool(tool_spec)
                        else:
                            result = RegistrationResult(success=False, error="UnifiedToolLibrary not initialized for this server.")
                    elif tool_type_str == ToolType.MCP_SERVER.value:
                        tool_spec = MCPServerSpec(capabilities=capabilities, tool_type=ToolType.MCP_SERVER, **tool_spec_data)
                        if self.unified_tool_library: # 确保实例存在
                            result = await self.unified_tool_library.register_mcp_server(tool_spec)
                        else:
                            result = RegistrationResult(success=False, error="UnifiedToolLibrary not initialized for this server.")
                    else:
                        result = RegistrationResult(success=False, error=f"Unknown tool type: {tool_type_str}") # 使用 error 参数

                    response = {
                        "type": "register_tool_response",
                        "request_id": request_id,
                        "success": result.success,
                        "message": result.error # 使用 result.error
                    }
                else:
                    response = {
                        "type": "register_tool_response",
                        "request_id": request_id,
                        "success": False,
                        "message": "Missing tool_spec in registration request"
                    }
                await websocket.send(json.dumps(response))

            elif request_type == "request" and self.server_name == "toolscore":
                # 处理ToolScoreClient发送的请求类型消息
                action = request.get("action")
                
                if action == "get_available_tools":
                    # 处理获取可用工具列表请求
                    if self.unified_tool_library:
                        try:
                            all_tools = await self.unified_tool_library.get_all_tools()
                            tool_ids = [tool.tool_id for tool in all_tools]
                            
                            response = {
                                "type": "response",
                                "request_id": request_id,
                                "success": True,
                                "data": tool_ids
                            }
                        except Exception as e:
                            logger.error(f"Error getting available tools: {e}", exc_info=True)
                            response = {
                                "type": "response",
                                "request_id": request_id,
                                "success": False,
                                "error_message": str(e),
                                "data": []
                            }
                    else:
                        response = {
                            "type": "response",
                            "request_id": request_id,
                            "success": False,
                            "error_message": "UnifiedToolLibrary not initialized for this server.",
                            "data": []
                        }
                    await websocket.send(json.dumps(response))
                else:
                    # 处理其他action类型
                    response = {
                        "type": "response",
                        "request_id": request_id,
                        "success": False,
                        "error_message": f"Unknown action: {action}"
                    }
                    await websocket.send(json.dumps(response))

            elif request_type == "list_tools" and self.server_name == "toolscore":
                # 只有toolscore才处理工具列表请求
                if self.unified_tool_library:
                    try:
                        all_tools = await self.unified_tool_library.get_all_tools()
                        tools_data = []
                        for tool in all_tools:
                            tools_data.append({
                                "tool_id": tool.tool_id,
                                "name": tool.name,
                                "description": tool.description,
                                "tool_type": tool.tool_type.value,
                                "capabilities": [cap.to_dict() for cap in tool.capabilities]
                            })
                        
                        response = {
                            "type": "list_tools_response",
                            "request_id": request_id,
                            "success": True,
                            "tools": tools_data,
                            "total_count": len(tools_data)
                        }
                    except Exception as e:
                        logger.error(f"Error listing tools: {e}", exc_info=True)
                        response = {
                            "type": "list_tools_response",
                            "request_id": request_id,
                            "success": False,
                            "error": str(e),
                            "tools": [],
                            "total_count": 0
                        }
                else:
                    response = {
                        "type": "list_tools_response",
                        "request_id": request_id,
                        "success": False,
                        "error": "UnifiedToolLibrary not initialized for this server.",
                        "tools": [],
                        "total_count": 0
                    }
                await websocket.send(json.dumps(response))

            elif request_type == "execute_tool" and self.server_name == "toolscore":
                # 只有toolscore才处理工具执行请求并路由
                tool_id = request.get("tool_id")
                action = request.get("action")
                parameters = request.get("parameters")

                if self.unified_tool_library:
                    try:
                        # 获取工具规范
                        tool_spec = await self.unified_tool_library.get_tool_by_id(tool_id)
                        
                        if tool_spec and tool_spec.tool_type == ToolType.MCP_SERVER:
                            # 对于MCP_SERVER类型的工具，直接通过WebSocket转发到实际的MCP服务器
                            logger.info(f"Forwarding tool execution to MCP server for tool {tool_id}")
                            
                            # 生成转发请求ID
                            forward_request_id = str(uuid4())
                            forward_request = {
                                "type": "execute_tool_action",
                                "request_id": forward_request_id,
                                "tool_id": tool_id,
                                "action": action,
                                "parameters": parameters
                            }
                            
                            # 注意：这里需要维护到各个MCP服务器的连接
                            # 目前简化处理，通过UnifiedToolLibrary但绕过适配器
                            
                            # 实现真正的MCP服务器转发
                            forward_result = await self._forward_to_mcp_server(tool_id, action, parameters)
                            response = {
                                "type": "execute_tool_response",
                                "request_id": request_id,
                                "tool_id": tool_id,
                                "action": action,
                                "success": forward_result.get("success", False),
                                "result": forward_result.get("result"),
                                "error": forward_result.get("error"),
                                "error_type": forward_result.get("error_type", ErrorType.SYSTEM_ERROR.value)
                            }
                        else:
                            # 对于非MCP_SERVER工具（Function tools），使用UnifiedToolLibrary
                            execution_result: ExecutionResult = await self.unified_tool_library.execute_tool(tool_id, action, parameters)
                            response = {
                                "type": "execute_tool_response",
                                "request_id": request_id,
                                "tool_id": tool_id,
                                "action": action,
                                "success": execution_result.success,
                                "result": execution_result.data,
                                "error": execution_result.error_message,
                                "error_type": execution_result.error_type if execution_result.error_type else None
                            }
                    except Exception as e:
                        logger.error(f"Error executing tool {tool_id} via ToolScore: {e}", exc_info=True)
                        response = {
                            "type": "execute_tool_response",
                            "request_id": request_id,
                            "tool_id": tool_id,
                            "action": action,
                            "success": False,
                            "result": None,
                            "error": str(e),
                            "error_type": ErrorType.SYSTEM_ERROR.value
                        }
                else:
                    response = {
                        "type": "execute_tool_response",
                        "request_id": request_id,
                        "tool_id": tool_id,
                        "action": action,
                        "success": False,
                        "result": None,
                        "error": "UnifiedToolLibrary not initialized for this server.",
                        "error_type": ErrorType.SYSTEM_ERROR.value
                    }
                await websocket.send(json.dumps(response))

            elif request_type == "execute_tool_action":
                # 其他MCP Server处理自身的工具动作
                tool_id = request.get("tool_id")
                action = request.get("action")
                parameters = request.get("parameters")

                if self.tool_action_handler:
                    try:
                        action_result = await self.tool_action_handler(action, parameters)
                        response = {
                            "type": "execute_tool_action_response",
                            "request_id": request_id,
                            "tool_id": tool_id,
                            "action": action,
                            "result": action_result # 假设action_result是字典
                        }
                    except Exception as e:
                        logger.error(f"Error in tool action handler for {tool_id}/{action}: {e}", exc_info=True)
                        response = {
                            "type": "execute_tool_action_response",
                            "request_id": request_id,
                            "tool_id": tool_id,
                            "action": action,
                            "result": {"success": False, "error": str(e), "error_type": "ToolExecutionError"}
                        }
                else:
                    response = {
                        "type": "execute_tool_action_response",
                        "request_id": request_id,
                        "tool_id": tool_id,
                        "action": action,
                        "result": {"success": False, "error": "No action handler registered", "error_type": "ServerError"}
                    }
                await websocket.send(json.dumps(response))
            else:
                logger.warning(f"Unknown request type or server role mismatch: {request_type}")
                response = {
                    "type": "error",
                    "request_id": request_id,
                    "message": f"Unknown request type or server role mismatch: {request_type}"
                }
                await websocket.send(json.dumps(response))

        except json.JSONDecodeError:
            logger.error(f"Received invalid JSON: {message}")
            await websocket.send(json.dumps({"type": "error", "message": "Invalid JSON"}))
        except Exception as e:
            logger.error(f"Error handling message: {e}", exc_info=True)
            await websocket.send(json.dumps({"type": "error", "message": str(e)}))
                
    async def _forward_to_mcp_server(self, tool_id: str, action: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """转发请求到实际的MCP服务器"""
        try:
            
            # 从工具库中获取工具规范和端点信息
            if self.unified_tool_library:
                tool_spec = await self.unified_tool_library.get_tool_by_id(tool_id)
                logger.info(f"🔍 查找工具规范: {tool_id}, 找到: {tool_spec is not None}")
                if not tool_spec or tool_spec.tool_type != ToolType.MCP_SERVER:
                    return {
                        "success": False,
                        "error": f"MCP server not found or invalid type: {tool_id}",
                        "error_type": ErrorType.TOOL_ERROR.value
                    }
                
                # 确保tool_spec是MCPServerSpec类型，以便访问endpoint
                if not isinstance(tool_spec, MCPServerSpec):
                    return {
                        "success": False,
                        "error": f"Tool {tool_id} is not an MCPServerSpec type.",
                        "error_type": ErrorType.SYSTEM_ERROR.value
                    }

                # 获取实际的端点地址
                endpoint = tool_spec.endpoint
                logger.info(f"🔗 工具端点: {endpoint}")
                if not endpoint:
                    return {
                        "success": False,
                        "error": f"No endpoint configured for MCP server: {tool_id}",
                        "error_type": ErrorType.TOOL_ERROR.value
                    }
            else:
                return {
                    "success": False,
                    "error": "UnifiedToolLibrary not available",
                    "error_type": ErrorType.SYSTEM_ERROR.value
                }
            
            # 构建WebSocket请求到MCP服务器
            request_id = str(uuid4())
            payload = {
                "type": "execute_tool_action",
                "request_id": request_id,
                "tool_id": tool_id,
                "action": action,
                "parameters": parameters
            }
            
            # 移除重复的 import websockets
            try:
                logger.info(f"🔌 尝试连接到MCP服务器 {tool_id} at {endpoint}")
                # 使用ping_interval和ping_timeout来处理连接超时
                async with websockets_client.connect(endpoint, ping_interval=10, ping_timeout=30) as ws:
                    # 修复：这里不需要 self.toolscore_client = ws，因为这是转发到其他MCP服务器，而不是toolscore本身
                    logger.info(f"✅ 成功连接到 {endpoint}")
                    # 发送请求
                    await ws.send(json.dumps(payload))
                    logger.info(f"📤 已发送请求到 {tool_id}")
                    
                    # 等待响应
                    response_str = await asyncio.wait_for(ws.recv(), timeout=120.0) # 增加超时以支持长时间运行的工具
                    logger.info(f"📥 收到响应: {response_str[:200]}...")
                    response_data = json.loads(response_str)
                    
                    if response_data.get("request_id") == request_id:
                        result = response_data.get("result", {})
                        return {
                            "success": result.get("success", False),
                            "result": result.get("data") or result.get("result"),
                            "error": result.get("error"),
                            "error_type": result.get("error_type")
                        }
                    else:
                        return {
                            "success": False,
                            "result": None,
                            "error": f"Mismatched request ID in response",
                            "error_type": ErrorType.SYSTEM_ERROR.value
                        }
                        
            except ConnectionClosedError as e:
                logger.error(f"❌ 连接到 {tool_id} 时关闭: {str(e)}")
                return {
                    "success": False,
                    "result": None,
                    "error": f"Connection to {tool_id} closed: {str(e)}",
                    "error_type": ErrorType.NETWORK_ERROR.value
                }
            except asyncio.TimeoutError: # 捕获 asyncio.TimeoutError
                logger.error(f"❌ 连接到 {tool_id} 时超时")
                return {
                    "success": False,
                    "result": None,
                    "error": f"Connection to {tool_id} timed out",
                    "error_type": ErrorType.NETWORK_ERROR.value
                }
            except Exception as e:
                logger.error(f"❌ WebSocket连接错误: {str(e)}")
                return {
                    "success": False,
                    "result": None,
                    "error": f"WebSocket connection failed: {str(e)}",
                    "error_type": ErrorType.NETWORK_ERROR.value
                }
                        
        except Exception as e:
            logger.error(f"❌ 转发到MCP服务器 {tool_id} 时出错: {e}")
            return {
                "success": False,
                "result": None,
                "error": f"Failed to forward to MCP server: {str(e)}",
                "error_type": ErrorType.SYSTEM_ERROR.value
            }

    async def websocket_handler(self, websocket: WebSocketServerProtocol, path: str):
        """WebSocket连接处理函数"""
        logger.info(f"Client connected to {self.server_name} MCP Server at path {path}: {websocket.remote_address}")
        try:
            async for message in websocket:
                # _handle_message 现在接受 Union[str, bytes]，所以这里不需要额外的解码
                await self._handle_message(websocket, message)
        except ConnectionClosedOK:
            logger.info(f"Client disconnected from {self.server_name} MCP Server: {websocket.remote_address}")
        except Exception as e:
            logger.error(f"WebSocket error in {self.server_name} server: {e}", exc_info=True)

    async def _register_with_toolscore(self):
        """向UnifiedToolLibrary MCP Server注册本工具"""
        if not self.toolscore_endpoint or self.server_name == "toolscore":
            return # toolscore自己不需要向自己注册

        # 等待ToolScore服务器启动
        logger.info(f"Waiting 10 seconds for ToolScore server to fully start...")
        await asyncio.sleep(10)

        tool_spec = MCPServerSpec(
            tool_id=self.server_id,
            name=self.server_name,
            description=self.description,
            tool_type=self.tool_type,
            capabilities=self.capabilities,
            endpoint=self.endpoint,
            connection_params={} # 可以添加连接参数
        )
        
        while True:
            try:
                logger.info(f"[{self.server_name}] Attempting to connect to toolscore at {self.toolscore_endpoint} for registration...")
                async with websockets_client.connect(self.toolscore_endpoint, ping_interval=10, ping_timeout=20) as ws: # 添加 ping 参数
                    self.toolscore_client = ws
                    logger.info(f"[{self.server_name}] Connected to toolscore at {self.toolscore_endpoint}")
                    
                    request_id = str(uuid4())
                    register_request = {
                        "type": "register_tool",
                        "request_id": request_id,
                        "tool_spec": {
                            "tool_id": tool_spec.tool_id,
                            "name": tool_spec.name,
                            "description": tool_spec.description,
                            "tool_type": tool_spec.tool_type.value,
                            "capabilities": [cap.to_dict() for cap in tool_spec.capabilities],
                            "endpoint": tool_spec.endpoint,
                            "connection_params": tool_spec.connection_params
                        }
                    }
                    logger.info(f"[{self.server_name}] Sending registration request to toolscore: {json.dumps(register_request)}")
                    await ws.send(json.dumps(register_request))
                    
                    logger.info(f"[{self.server_name}] Waiting for registration response from toolscore...")
                    response_str = await asyncio.wait_for(ws.recv(), timeout=120.0) # 增加超时以支持长时间运行的工具
                    logger.info(f"[{self.server_name}] Received registration response: {response_str}")
                    response_data = json.loads(response_str)
                    
                    if response_data.get("type") == "register_tool_response" and response_data.get("request_id") == request_id:
                        if response_data.get("success"):
                            logger.info(f"[{self.server_name}] Successfully registered with toolscore.")
                            break # 注册成功，退出循环
                        else:
                            logger.error(f"[{self.server_name}] Failed to register with toolscore: {response_data.get('message')}")
                    else:
                        logger.error(f"[{self.server_name}] Unexpected response from toolscore: {response_data}")
                
            except InvalidURI:
                logger.error(f"[{self.server_name}] Invalid toolscore endpoint URI: {self.toolscore_endpoint}. Registration aborted.", exc_info=True)
                break # 无效URI，停止重试
            except (ConnectionClosedOK, ConnectionClosedError, ConnectionRefusedError) as e:
                logger.warning(f"[{self.server_name}] Connection to toolscore failed: {e}. Retrying in 5 seconds...")
            except asyncio.TimeoutError:
                logger.warning(f"[{self.server_name}] Timeout waiting for registration response from toolscore. Retrying in 5 seconds...")
            except Exception as e:
                logger.error(f"[{self.server_name}] Error during toolscore registration: {e}", exc_info=True)
            
            await asyncio.sleep(5) # 等待5秒后重试

    async def start(self):
        """启动MCP Server"""
        try:
            # 解析监听地址和端口
            _endpoint_without_scheme = self.endpoint.split('://', 1)[-1]
            host_part, port_part = _endpoint_without_scheme.split(':', 1)
            
            default_port = int(port_part.split('/')[0])
            port = self.bind_port if self.bind_port is not None else default_port
 
            env_bind_host_var = f"{self.server_name.upper()}_BIND_HOST"
            bind_host = os.getenv(env_bind_host_var, host_part or "0.0.0.0")
            
            env_port_var = f"{self.server_name.upper()}_PORT"
            port = int(os.getenv(env_port_var, str(port)))

            logger.info(f"Attempting to start {self.server_name} MCP Server on {bind_host}:{port}")
            
            self.websocket_server = await websockets_server.serve(
                self.websocket_handler,
                bind_host,
                port,
                ping_interval=30,
                ping_timeout=60
            )
            
            # 确保 UnifiedToolLibrary 在服务器成功绑定端口后初始化
            if self.server_name == "toolscore" and self.unified_tool_library:
                logger.info(f"[{self.server_name}] Initializing UnifiedToolLibrary...")
                await self.unified_tool_library.initialize()
                logger.info(f"[{self.server_name}] UnifiedToolLibrary initialized.")

            logger.info(f"{self.server_name} MCP Server started successfully on {bind_host}:{port} (Original endpoint: {self.endpoint}) with ping_interval=30, ping_timeout=60")
            
            # 服务器成功启动并初始化后设置事件，并标记为健康
            if self.server_started_event:
                self.server_started_event.set()
                logger.info(f"{self.server_name} MCP Server started event set.")
            self._is_healthy = True # 标记服务健康

            if self.toolscore_endpoint and self.server_name != "toolscore":
                self.toolscore_registration_task = asyncio.create_task(self._register_with_toolscore())

            await self.websocket_server.wait_closed()
        except OSError as e: # 明确捕获端口占用错误
            self._is_healthy = False
            self._startup_error_message = f"Port {port} already in use or address unavailable: {e}"
            logger.error(f"Failed to start {self.server_name} MCP Server due to port issue: {self._startup_error_message}", exc_info=True)
            raise # 重新抛出异常，以便上层调用者感知
        except Exception as e:
            self._is_healthy = False
            self._startup_error_message = f"An unexpected error occurred during startup: {e}"
            logger.error(f"Failed to start {self.server_name} MCP Server: {self._startup_error_message}", exc_info=True)
            raise

    async def stop(self):
        """停止MCP Server"""
        if self.toolscore_registration_task:
            self.toolscore_registration_task.cancel()
            try:
                await self.toolscore_registration_task
            except asyncio.CancelledError:
                pass
        
        if self.websocket_server:
            self.websocket_server.close()
            await self.websocket_server.wait_closed()
            logger.info(f"{self.server_name} MCP Server stopped.")
        
        if self.unified_tool_library and self.server_name == "toolscore":
            await self.unified_tool_library.cleanup()
            logger.info("UnifiedToolLibrary cleaned up for toolscore server.")

# Alias for backward compatibility with services.toolscore_service
ToolScoreMCPServer = MCPServer

async def main():
    """启动ToolScore MCP服务器和监控API"""
    import logging
    import os
    import json
    logging.basicConfig(level=logging.INFO)
    
    # 导入工具能力定义
    from .interfaces import ToolCapability, ToolType
    from .unified_tool_library import UnifiedToolLibrary
    from .monitoring_api import start_monitoring_api
    
    # 创建ToolScore MCP服务器
    capabilities = [
        ToolCapability(
            name="register_tool",
            description="注册新工具到工具库",
            parameters={
                "tool_spec": {
                    "type": "object",
                    "description": "工具规范",
                    "required": True
                }
            },
            examples=[{"tool_spec": {"tool_id": "example_tool", "name": "示例工具"}}]
        ),
        ToolCapability(
            name="list_tools",
            description="列出所有可用工具",
            parameters={},
            examples=[{}]
        ),
        ToolCapability(
            name="execute_tool",
            description="执行指定工具",
            parameters={
                "tool_id": {
                    "type": "string",
                    "description": "工具ID",
                    "required": True
                },
                "action": {
                    "type": "string", 
                    "description": "工具动作",
                    "required": True
                },
                "parameters": {
                    "type": "object",
                    "description": "动作参数",
                    "required": False
                }
            },
            examples=[{"tool_id": "python_executor_server", "action": "python_execute", "parameters": {"code": "print('hello')"}}]
        )
    ]
    
    # 创建工具库实例
    tool_library = UnifiedToolLibrary()
    
    # 初始化工具库（包括恢复持久化的MCP服务器）
    await tool_library.initialize()
    
    # 🔧 新增：从mcp_tools.json加载基础工具库
    mcp_tools_file = '/app/mcp_tools.json'
    if os.path.exists(mcp_tools_file):
        try:
            logger.info(f"📖 开始从 {mcp_tools_file} 加载基础工具库...")
            with open(mcp_tools_file, 'r', encoding='utf-8') as f:
                tools_data = json.load(f)
            
            # 🔧 修复：处理数组格式的JSON文件
            if isinstance(tools_data, list):
                logger.info(f"📋 检测到数组格式的工具文件，包含 {len(tools_data)} 个工具")
                loaded_count = 0
                for tool_info in tools_data:
                    try:
                        # 使用工具名称作为ID
                        tool_id = tool_info.get('name', '').lower().replace(' ', '_').replace('-', '_')
                        if not tool_id:
                            continue
                        
                        # 创建工具规范对象
                        from .interfaces import FunctionToolSpec
                        
                        # 构建工具能力
                        capabilities_list = []
                        if tool_info.get('tools'):
                            for tool_def in tool_info['tools']:
                                capability_params = {}
                                if tool_def.get('parameter'):
                                    # 转换parameter格式为标准格式
                                    params = tool_def['parameter']
                                    for param_name, param_desc in params.items():
                                        capability_params[param_name] = {
                                            "type": "string",
                                            "description": param_desc if isinstance(param_desc, str) else str(param_desc),
                                            "required": True
                                        }
                                
                                capabilities_list.append(ToolCapability(
                                    name=tool_def.get('name', 'unknown'),
                                    description=tool_def.get('description', 'No description'),
                                    parameters=capability_params,
                                    examples=[]
                                ))
                        
                        # 如果没有tools定义，创建一个通用能力
                        if not capabilities_list:
                            capabilities_list.append(ToolCapability(
                                name='default_action',
                                description=tool_info.get('description', 'General tool functionality'),
                                parameters={},
                                examples=[]
                            ))
                        
                        # 创建工具规范
                        tool_spec = FunctionToolSpec(
                            tool_id=tool_id,
                            name=tool_info.get('name', tool_id),
                            description=tool_info.get('description', 'Tool from mcp_tools.json'),
                            tool_type=ToolType.FUNCTION,
                            capabilities=capabilities_list,
                            module_path='',
                            class_name='',
                            enabled=True,
                            tags=[]
                        )
                        
                        # 注册工具到工具库
                        result = await tool_library.register_function_tool(tool_spec)
                        if result.success:
                            loaded_count += 1
                        else:
                            logger.warning(f"⚠️ 工具注册失败 {tool_id}: {result.error}")
                            
                    except Exception as e:
                        logger.error(f"❌ 处理工具 {tool_info.get('name', 'unknown')} 时出错: {e}")
                
                logger.info(f"✅ 从 mcp_tools.json 成功加载了 {loaded_count} 个工具")
                
            else:
                logger.error("❌ mcp_tools.json 格式不正确：期望数组格式")
                
        except Exception as e:
            logger.error(f"❌ 加载 mcp_tools.json 失败: {e}")
    else:
        logger.warning(f"⚠️ 未找到 mcp_tools.json 文件: {mcp_tools_file}")
    
    # 使用核心管理器进行自动注册 - 精简版本
    logger.info("🚀 开始自动注册预置MCP服务器...")
    
    # 通过核心管理器执行自动注册
    if hasattr(tool_library, 'core_manager') and tool_library.core_manager:
        auto_register_results = await tool_library.core_manager._auto_register_predefined_servers()
        logger.info(f"📊 自动注册完成: {auto_register_results.get('success_count', 0)} 成功, {auto_register_results.get('failed_count', 0)} 失败")
    else:
        logger.warning("⚠️ 核心管理器不可用，跳过自动注册")
    
    # 创建MCP服务器
    server = MCPServer(
        server_name="toolscore",
        server_id="toolscore-main-server", 
        description="统一工具注册与调用中心",
        capabilities=capabilities,
        tool_type=ToolType.MCP_SERVER,
        endpoint="ws://0.0.0.0:8080/websocket",
        toolscore_endpoint=None  # 自己就是toolscore
    )
    
    # 设置工具库
    server.unified_tool_library = tool_library
    
    # 启动HTTP监控API (在8090端口)
    logger.info("Starting ToolScore monitoring API on port 8090...")
    http_runner = await start_monitoring_api(tool_library, port=8090)
    
    # 启动WebSocket MCP服务器 (在8080端口)
    logger.info("Starting ToolScore MCP WebSocket server on port 8080...")
    await server.start()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())