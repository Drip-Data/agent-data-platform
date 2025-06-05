import asyncio
import json
import logging
import websockets
from typing import Dict, Any, Callable, Optional, List # 导入 List
from uuid import uuid4

from core.interfaces import ErrorType # 从 core.interfaces 导入 ErrorType
from .interfaces import ToolSpec, ToolType, RegistrationResult, ExecutionResult, ToolCapability, MCPServerSpec, FunctionToolSpec # 导入 ToolCapability, MCPServerSpec, FunctionToolSpec
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

            elif request_type == "execute_tool" and self.server_name == "toolscore":
                # 只有toolscore才处理工具执行请求并路由
                tool_id = request.get("tool_id")
                action = request.get("action")
                parameters = request.get("parameters")

                if self.unified_tool_library:
                    try:
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
                        logger.error(f"Error executing tool {tool_id} via UnifiedToolLibrary: {e}", exc_info=True)
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

    async def websocket_handler(self, websocket: websockets.WebSocketServerProtocol, path: str):
        """WebSocket连接处理函数"""
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
                        "tool_spec": tool_spec.to_dict() # 假设ToolSpec有to_dict方法
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
    print("Entering main function...") # Added for debugging
    # 初始化 toolscore MCP Server
    toolscore_server = MCPServer(
        server_name="toolscore",
        server_id="toolscore-server-id", # 固定的ID
        description="Unified Tool Library MCP Server for agent platform",
        capabilities=[
            ToolCapability(name="tool_registration", description="Registers new tools from other MCP Servers", parameters={}),
            ToolCapability(name="tool_execution", description="Dispatches tool execution requests to registered MCP Servers", parameters={})
        ],
        tool_type=ToolType.MCP_SERVER,
        endpoint="ws://0.0.0.0:8080/websocket" # 监听所有接口
    )
    print("MCPServer instance created.") # Added for debugging
    
    # 启动服务器
    await toolscore_server.start()
    print("MCPServer start method awaited.") # Added for debugging

if __name__ == "__main__":
    print("Script is being run directly.") # Added for debugging
    # 配置日志
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                        force=True)
    print("Logging configured.") # Added for debugging
    asyncio.run(main())
    print("Asyncio event loop finished.") # Added for debugging