import asyncio
import json
import logging
import websockets
from typing import Dict, Any, Callable, Optional, List # 导入 List
from uuid import uuid4

from .interfaces import ToolSpec, ToolType, RegistrationResult, ExecutionResult, ToolCapability, MCPServerSpec, FunctionToolSpec, ErrorType # 导入 ToolCapability, MCPServerSpec, FunctionToolSpec, ErrorType
from .unified_tool_library import UnifiedToolLibrary # 导入UnifiedToolLibrary，用于注册工具

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
                 toolscore_endpoint: Optional[str] = None # UnifiedToolLibrary MCP Server的地址
                 ):
        self.server_name = server_name
        self.server_id = server_id
        self.description = description
        self.capabilities = capabilities
        self.tool_type = tool_type
        self.endpoint = endpoint
        self.toolscore_endpoint = toolscore_endpoint
        self.websocket_server = None
        self.tool_action_handler: Optional[Callable[[str, Dict[str, Any]], Any]] = None
        self.toolscore_client: Optional[websockets.WebSocketClientProtocol] = None
        self.toolscore_registration_task: Optional[asyncio.Task] = None

        # 如果是toolscore本身，则不连接toolscore_endpoint
        if self.server_name == "toolscore":
            self.unified_tool_library = UnifiedToolLibrary()
        else:
            self.unified_tool_library = None # 其他MCP Server不直接使用UnifiedToolLibrary实例

    def register_tool_action_handler(self, handler: Callable[[str, Dict[str, Any]], Any]):
        """注册处理工具动作的函数"""
        self.tool_action_handler = handler

    async def _handle_message(self, websocket: websockets.WebSocketServerProtocol, message: str):
        """处理接收到的WebSocket消息"""
        try:
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
            # 映射工具ID到服务器WebSocket端点
            server_endpoint_map = {
                "python-executor-mcp-server": "ws://python-executor-server:8081/mcp",
                "browser-navigator-mcp-server": "ws://browser-navigator-server:8082/mcp"
            }
            
            endpoint = server_endpoint_map.get(tool_id)
            if not endpoint:
                return {
                    "success": False,
                    "error": f"Unknown MCP server: {tool_id}",
                    "error_type": ErrorType.TOOL_ERROR.value
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
            
            import websockets
            try:
                # 使用ping_interval和ping_timeout来处理连接超时
                async with websockets.connect(endpoint, ping_interval=10, ping_timeout=30) as ws:
                    # 发送请求
                    await ws.send(json.dumps(payload))
                    
                    # 等待响应
                    response_str = await ws.recv()
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
                        
            except websockets.exceptions.ConnectionClosedError as e:
                return {
                    "success": False,
                    "result": None,
                    "error": f"Connection to {tool_id} closed: {str(e)}",
                    "error_type": ErrorType.CONNECTION_ERROR.value
                }
                        
        except Exception as e:
            logger.error(f"Error forwarding to MCP server {tool_id}: {e}")
            return {
                "success": False,
                "result": None,
                "error": f"Failed to forward to MCP server: {str(e)}",
                "error_type": ErrorType.SYSTEM_ERROR.value
            }

    async def websocket_handler(self, websocket: websockets.WebSocketServerProtocol):
        """WebSocket连接处理函数"""
        # 注意：在新版websockets中，ServerConnection对象没有path属性
        # 如果需要路径信息，可以通过其他方式获取
        logger.info(f"Client connected to {self.server_name} MCP Server: {websocket.remote_address}")
        try:
            async for message in websocket:
                await self._handle_message(websocket, message)
        except websockets.exceptions.ConnectionClosedOK:
            logger.info(f"Client disconnected from {self.server_name} MCP Server: {websocket.remote_address}")
        except Exception as e:
            logger.error(f"WebSocket error in {self.server_name} server: {e}", exc_info=True)

    async def _register_with_toolscore(self):
        """向UnifiedToolLibrary MCP Server注册本工具"""
        if not self.toolscore_endpoint or self.server_name == "toolscore":
            return # toolscore自己不需要向自己注册

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
                logger.info(f"Attempting to connect to toolscore at {self.toolscore_endpoint} for registration...")
                async with websockets.connect(self.toolscore_endpoint) as ws:
                    self.toolscore_client = ws
                    logger.info(f"Connected to toolscore at {self.toolscore_endpoint}")
                    
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
                    await ws.send(json.dumps(register_request))
                    
                    response = await ws.recv()
                    response_data = json.loads(response)
                    
                    if response_data.get("type") == "register_tool_response" and response_data.get("request_id") == request_id:
                        if response_data.get("success"):
                            logger.info(f"Successfully registered {self.server_name} with toolscore.")
                            break # 注册成功，退出循环
                        else:
                            logger.error(f"Failed to register {self.server_name} with toolscore: {response_data.get('message')}")
                    else:
                        logger.error(f"Unexpected response from toolscore: {response_data}")
                
            except (websockets.exceptions.ConnectionClosedOK, websockets.exceptions.ConnectionClosedError, ConnectionRefusedError) as e:
                logger.warning(f"Connection to toolscore failed: {e}. Retrying in 5 seconds...")
            except Exception as e:
                logger.error(f"Error during toolscore registration: {e}", exc_info=True)
            
            await asyncio.sleep(5) # 等待5秒后重试

    async def start(self):
        """启动MCP Server"""
        try:
            if self.server_name == "toolscore" and self.unified_tool_library:
                await self.unified_tool_library.initialize()
                logger.info("UnifiedToolLibrary initialized for toolscore server.")

            port = int(self.endpoint.split(':')[-1].split('/')[0])
            logger.info(f"Attempting to start {self.server_name} MCP Server on 0.0.0.0:{port}")
            self.websocket_server = await websockets.serve(self.websocket_handler, "0.0.0.0", port)
            logger.info(f"{self.server_name} MCP Server started successfully on {self.endpoint}")

            if self.toolscore_endpoint and self.server_name != "toolscore":
                self.toolscore_registration_task = asyncio.create_task(self._register_with_toolscore())

            # Keep the server running indefinitely
            await self.websocket_server.wait_closed()
        except Exception as e:
            logger.error(f"Failed to start {self.server_name} MCP Server: {e}", exc_info=True)
            # Re-raise the exception to indicate startup failure
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

async def main():
    """启动ToolScore MCP服务器和监控API"""
    import logging
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