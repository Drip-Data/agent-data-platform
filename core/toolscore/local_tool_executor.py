import asyncio
import httpx # type: ignore
import json
import logging
import time
import websockets # type: ignore
from typing import Dict, Any, Optional, List, Union, Callable, Awaitable
from urllib.parse import urljoin
from core.toolscore.tool_registry import ToolRegistry
from core.interfaces import LocalToolSpec, LocalToolExecutorInterface


logger = logging.getLogger(__name__)

# ToolExecutorFunc type alias from interfaces.py might be:
# ToolExecutorFunc = Callable[[str, str, Dict[str, Any]], Awaitable[Dict[str, Any]]]
# Adjusted to: tool_id, action, parameters
ToolExecutorFunc = Callable[[str, str, Dict[str, Any]], Awaitable[Dict[str, Any]]]


class LocalToolExecutor(LocalToolExecutorInterface):
    """本地工具执行器：执行不同类型的本地工具"""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(LocalToolExecutor, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if hasattr(self, '_initialized') and self._initialized:
            return

        self.http_client = httpx.AsyncClient(timeout=60.0)
        self.registry = ToolRegistry() # Singleton instance
        self.executors: Dict[str, ToolExecutorFunc] = {
            "function": self._execute_function_tool,
            "http": self._execute_http_tool,
            "websocket": self._execute_websocket_tool
        }
        self.ws_connections: Dict[str, websockets.WebSocketClientProtocol] = {} # type: ignore
        self._initialized = True
        logger.info("本地工具执行器初始化完成")

    async def register_executor(self, tool_type: str, executor: ToolExecutorFunc): # type: ignore
        """注册自定义工具执行器"""
        # Note: The ToolExecutorFunc signature in the abstract class might be different.
        # Here, it's (tool_id, action, parameters).
        # If LocalToolExecutorInterface defines it as (tool_spec, action, params), adjust accordingly.
        self.executors[tool_type] = executor
        logger.info(f"注册工具执行器: {tool_type}")


    async def execute(self, tool_id: str, action: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """执行工具动作"""
        start_time = time.time()
        try:
            # Ensure registry has loaded its tools if it defers loading
            if hasattr(self.registry, 'load_tools_async') and not getattr(self.registry, '_tools_loaded', False):
                await self.registry.load_tools_async()


            tool_spec = await self.registry.get_tool(tool_id)
            if not tool_spec:
                return {"success": False, "error": f"工具不存在: {tool_id}", "execution_time": time.time() - start_time}

            tool_type = tool_spec.type
            if tool_type not in self.executors:
                return {"success": False, "error": f"不支持的工具类型: {tool_type}", "execution_time": time.time() - start_time}

            # Validate action against tool_spec.actions
            action_spec = next((a for a in tool_spec.actions if a["name"] == action), None)
            if not action_spec:
                valid_actions_str = ", ".join([a["name"] for a in tool_spec.actions])
                return {"success": False, "error": f"工具 {tool_id} 不支持动作 '{action}'. 支持的动作: {valid_actions_str}", "execution_time": time.time() - start_time}


            executor_func = self.executors[tool_type]
            # Pass tool_id, action, and parameters to the specific executor
            result = await executor_func(tool_id, action, parameters) # tool_spec could also be passed if needed

            if isinstance(result, dict):
                result["execution_time"] = time.time() - start_time
            return result
        except Exception as e:
            logger.error(f"执行工具失败 {tool_id}.{action}: {e}", exc_info=True)
            return {"success": False, "error": f"执行错误: {str(e)}", "execution_time": time.time() - start_time}

    async def _execute_function_tool(self, tool_id: str, action: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """执行函数类型工具"""
        # Directly use the registry's execute_tool method which handles function execution
        return await self.registry.execute_tool(tool_id, action, parameters)

    async def _execute_http_tool(self, tool_id: str, action: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """执行HTTP类型工具"""
        try:
            tool_spec = await self.registry.get_tool(tool_id) # Already fetched in execute, but good for standalone use
            if not tool_spec or not tool_spec.entry_point:
                return {"success": False, "error": f"HTTP工具 {tool_id} 未提供入口点或不存在"}

            # Construct URL based on a convention, e.g., entry_point is base URL of the tool server
            # The LocalToolServer (FastAPI example) creates routes like /tools/{tool_id}/{action}
            # So, if entry_point is "http://localhost:8081", final URL is "http://localhost:8081/tools/mytool/myaction"
            action_path = f"tools/{tool_id}/{action}" # This path is defined by FastAPIToolServer
            url = urljoin(tool_spec.entry_point, action_path)


            response = await self.http_client.post(url, json=parameters, timeout=60.0)
            response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
            return response.json()
        except httpx.TimeoutException:
            return {"success": False, "error": "HTTP请求超时"}
        except httpx.RequestError as e:
            return {"success": False, "error": f"HTTP请求错误: {str(e)}"}
        except httpx.HTTPStatusError as e:
            return {"success": False, "error": f"HTTP错误: {e.response.status_code}", "details": e.response.text}
        except json.JSONDecodeError:
            return {"success": False, "error": "无效的JSON响应"}
        except Exception as e:
            logger.error(f"执行HTTP工具失败 {tool_id}.{action}: {e}", exc_info=True)
            return {"success": False, "error": f"执行HTTP工具时发生内部错误: {str(e)}"}


    async def _execute_websocket_tool(self, tool_id: str, action: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """执行WebSocket类型工具"""
        connection_key = None # Initialize connection_key
        try:
            tool_spec = await self.registry.get_tool(tool_id)
            if not tool_spec or not tool_spec.entry_point:
                return {"success": False, "error": f"WebSocket工具 {tool_id} 未提供入口点或不存在"}

            entry_point = tool_spec.entry_point # This is the WebSocket server URL
            connection_key = entry_point # Use server URL as connection key

            connection: Optional[websockets.WebSocketClientProtocol] = self.ws_connections.get(connection_key) # type: ignore

            if not connection or not connection.open:
                try:
                    logger.info(f"正在连接到WebSocket服务器: {entry_point}")
                    connection = await websockets.connect(entry_point, timeout=10) # type: ignore
                    self.ws_connections[connection_key] = connection
                    logger.info(f"已连接到WebSocket: {entry_point}")
                except Exception as e_conn:
                    logger.error(f"WebSocket连接失败 {entry_point}: {e_conn}", exc_info=True)
                    if connection_key and connection_key in self.ws_connections: # Clean up if partially added
                        del self.ws_connections[connection_key]
                    return {"success": False, "error": f"WebSocket连接失败: {str(e_conn)}"}

            request_id = f"req_{tool_id}_{action}_{int(time.time() * 1000)}"
            request_payload = {
                "request_id": request_id,
                "tool_id": tool_id,
                "action": action,
                "parameters": parameters
            }

            await connection.send(json.dumps(request_payload)) # type: ignore

            # Wait for a response that matches the request_id
            # This requires the WebSocket server to echo request_id in its response
            response_timeout = 60.0 # seconds
            
            # Refined receive part:
            try:
                response_text = await asyncio.wait_for(connection.recv(), timeout=response_timeout) # type: ignore
                response = json.loads(str(response_text))
                if response.get("request_id") == request_id:
                    return response
                else:
                    # This could be a response for another concurrent request.
                    # This simple model doesn't handle multiplexing well.
                    # A more robust solution would involve a listener task per connection
                    # that dispatches messages to waiting requesters based on request_id.
                    logger.warning(f"WebSocket响应ID不匹配: Got {response.get('request_id')}, expected {request_id}. This might be a response for another request.")
                    # For now, we'll assume this is an error or a misdirected message for this simple model.
                    # In a real-world scenario, you'd need a way to handle this (e.g., keep listening or have a dedicated listener).
                    return {"success": False, "error": "WebSocket响应ID不匹配 (可能乱序或消息处理逻辑不完善)"}
            except asyncio.TimeoutError:
                logger.error(f"WebSocket接收响应超时 for {tool_id}.{action} (request_id: {request_id})")
                return {"success": False, "error": "WebSocket接收响应超时"}
            except websockets.exceptions.ConnectionClosed: # type: ignore
                logger.warning(f"WebSocket连接已关闭，当等待响应时: {entry_point}")
                if connection_key: self.ws_connections.pop(connection_key, None)
                return {"success": False, "error": "WebSocket连接已关闭"}


        except Exception as e:
            logger.error(f"执行WebSocket工具失败 {tool_id}.{action}: {e}", exc_info=True)
            # Clean up connection if it caused the error and is now invalid
            if connection_key and connection_key in self.ws_connections and not self.ws_connections[connection_key].open: # type: ignore
                self.ws_connections.pop(connection_key, None)
            return {"success": False, "error": f"执行WebSocket工具时发生内部错误: {str(e)}"}


    async def close(self):
        """关闭执行器，释放资源"""
        try:
            for key, connection in list(self.ws_connections.items()):
                try:
                    if connection.open: # type: ignore
                        await connection.close() # type: ignore
                except Exception as e_ws_close:
                    logger.warning(f"关闭WebSocket连接失败 {key}: {e_ws_close}")
            self.ws_connections.clear()

            await self.http_client.aclose()
            logger.info("本地工具执行器已关闭")
        except Exception as e:
            logger.error(f"关闭工具执行器失败: {e}", exc_info=True)