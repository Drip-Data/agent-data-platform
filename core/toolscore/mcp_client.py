import asyncio
import json
import logging
import websockets.legacy.client as websockets_client
from typing import Dict, Any, List, Optional

from .interfaces import ToolSpec, ExecutionResult, RegistrationResult, ToolCapability, ToolType, MCPServerSpec, FunctionToolSpec, ErrorType

logger = logging.getLogger(__name__)

class MCPToolClient:
    """
    MCP工具客户端
    用于ReasoningRuntime连接到远程UnifiedToolLibrary (toolscore MCP Server)
    并通过WebSocket协议进行工具的发现和执行。
    """
    def __init__(self, toolscore_endpoint: str):
        self.toolscore_endpoint = toolscore_endpoint
        self.websocket: Optional[websockets_client.WebSocketClientProtocol] = None
        self._connected = False
        logger.info(f"MCPToolClient initialized for toolscore at {toolscore_endpoint}")

    async def connect(self):
        """连接到toolscore MCP Server"""
        if self._connected and self.websocket:
            logger.info("Already connected to toolscore.")
            return

        try:
            logger.info(f"Attempting to connect to toolscore at {self.toolscore_endpoint}...")
            self.websocket = await websockets_client.connect(self.toolscore_endpoint)
            self._connected = True
            logger.info(f"Successfully connected to toolscore at {self.toolscore_endpoint}")
        except Exception as e:
            logger.error(f"Failed to connect to toolscore at {self.toolscore_endpoint}: {e}")
            self._connected = False
            raise

    async def disconnect(self):
        """断开与toolscore MCP Server的连接"""
        if self.websocket:
            logger.info("Disconnecting from toolscore...")
            try:
                await self.websocket.close()
            except Exception as e:
                logger.warning(f"Error closing websocket: {e}")
            self.websocket = None
            self._connected = False
            logger.info("Disconnected from toolscore.")

    async def _send_request(self, request_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """发送请求到toolscore并等待响应"""
        if not self._connected or self.websocket is None:
            await self.connect() # 尝试重新连接

        assert self.websocket is not None # 确保websocket已连接

        import uuid
        request_id = str(uuid.uuid4())
        request = {
            "type": request_type,
            "request_id": request_id,
            **payload  # 将payload直接合并到请求中
        }
        try:
            await self.websocket.send(json.dumps(request))
            response_str = await self.websocket.recv()
            response = json.loads(response_str)
            if not response.get("success", False):
                error_msg = response.get("error") or response.get("message", "Unknown error")
                raise Exception(f"Toolscore error: {error_msg}")
            return response
        except websockets_client.ConnectionClosedOK:
            logger.warning("Connection to toolscore closed gracefully. Attempting to reconnect for next request.")
            self._connected = False
            await self.connect() # 尝试重新连接
            # 重新连接后再次发送请求
            if self._connected and self.websocket:
                return await self._send_request(request_type, payload)
            else:
                raise ConnectionError("Failed to reconnect to toolscore after graceful close.")
        except Exception as e:
            logger.error(f"Error sending request to toolscore or receiving response: {e}")
            raise

    async def get_all_tools(self) -> List[ToolSpec]:
        """获取所有可用工具"""
        response = await self._send_request("list_tools", {})
        tool_specs = []
        for tool_data in response.get("tools", []):
            # 根据工具类型创建相应的ToolSpec
            if tool_data.get("tool_type") == "mcp_server":
                from .interfaces import MCPServerSpec
                # 转换capabilities
                capabilities = []
                for cap_data in tool_data.get("capabilities", []):
                    capability = ToolCapability(
                        name=cap_data.get("name", ""),
                        description=cap_data.get("description", ""),
                        parameters=cap_data.get("parameters", {}),
                        examples=cap_data.get("examples", [])
                    )
                    capabilities.append(capability)
                
                tool_spec = MCPServerSpec(
                    tool_id=tool_data.get("tool_id", ""),
                    name=tool_data.get("name", ""),
                    description=tool_data.get("description", ""),
                    tool_type=ToolType.MCP_SERVER,
                    capabilities=capabilities,
                    tags=[],
                    endpoint="",
                    connection_params={}
                )
                tool_specs.append(tool_spec)
        return tool_specs

    async def get_tool_by_id(self, tool_id: str) -> Optional[ToolSpec]:
        """获取指定工具"""
        response = await self._send_request("get_tool_by_id", {"tool_id": tool_id})
        tool_data = response.get("tool")
        if tool_data:
            return ToolSpec(**tool_data)
        return None

    async def get_all_tools_description_for_agent(self) -> str:
        """获取所有工具的Agent可理解描述"""
        response = await self._send_request("get_all_tools_description_for_agent", {})
        return response.get("description", "")

    async def execute_tool(self, tool_id: str, action: str, parameters: Dict[str, Any]) -> ExecutionResult:
        """执行单个工具"""
        payload = {
            "tool_id": tool_id,
            "action": action,
            "parameters": parameters
        }
        try:
            response = await self._send_request("execute_tool", payload)
            # 解析响应格式：ToolScore返回的格式与ExecutionResult略有不同
            error_type = None
            if response.get("error_type"):
                try:
                    error_type = ErrorType(response["error_type"])
                except ValueError:
                    # 如果无法解析error_type，设为默认值
                    error_type = ErrorType.TOOL_ERROR
            
            return ExecutionResult(
                success=response.get("success", False),
                data=response.get("result"),  # ToolScore使用"result"而不是"data"
                error_type=error_type,
                error_message=response.get("error"),  # ToolScore使用"error"而不是"error_message"
                metadata=response.get("metadata", {}),
                execution_time=response.get("execution_time", 0.0)
            )
        except Exception as e:
            logger.error(f"Error executing tool {tool_id} action {action}: {e}")
            return ExecutionResult(
                success=False,
                data=None,
                error_type=ErrorType.TOOL_ERROR,
                error_message=str(e),
                metadata={}
            )

    async def get_library_stats(self) -> Dict[str, Any]:
        """获取工具库统计信息"""
        response = await self._send_request("get_library_stats", {})
        return response.get("stats", {})

    async def cleanup(self):
        """清理资源"""
        await self.disconnect()