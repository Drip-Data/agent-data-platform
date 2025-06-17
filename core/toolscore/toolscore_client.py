import logging
import asyncio
import json
from typing import Dict, Any, List, Optional
import websockets.legacy.client as websockets
from websockets.legacy.client import WebSocketClientProtocol # 导入具体的类型
from websockets.exceptions import ConnectionClosedOK, ConnectionClosedError

from core.interfaces import TaskSpec, TaskType
from core.config_manager import ConfigManager

logger = logging.getLogger(__name__)

class ToolScoreClient:
    """与ToolScore服务交互的客户端"""

    def __init__(self, config_manager: ConfigManager):
        self.config_manager = config_manager
        ports_config = self.config_manager.get_ports_config()
        
        # HTTP 端口用于旧的 ToolScoreClient 模拟，现在将用于实际的 HTTP API
        self.toolscore_http_port = ports_config['mcp_servers']['toolscore_http']['port']
        self.tool_service_url = f"http://localhost:{self.toolscore_http_port}"
        
        # MCP WebSocket 端口用于实际的 MCP 通信
        self.toolscore_mcp_port = ports_config['mcp_servers']['toolscore_mcp']['port']
        self.toolscore_mcp_endpoint = f"ws://localhost:{self.toolscore_mcp_port}/websocket"
        
        self.websocket_client: Optional[WebSocketClientProtocol] = None # 明确类型提示
        self.connection_lock = asyncio.Lock() # 用于保护WebSocket连接
        
        logger.info(f"✅ ToolScoreClient 配置加载完成 - HTTP URL: {self.tool_service_url}, MCP Endpoint: {self.toolscore_mcp_endpoint}")

    async def _connect_to_toolscore_mcp(self) -> WebSocketClientProtocol: # 明确返回类型
        """建立并管理WebSocket连接"""
        async with self.connection_lock:
            if self.websocket_client and not self.websocket_client.closed:
                return self.websocket_client
            
            logger.info(f"尝试连接到 ToolScore MCP 服务: {self.toolscore_mcp_endpoint}")
            try:
                self.websocket_client = await websockets.connect(self.toolscore_mcp_endpoint)
                logger.info("成功连接到 ToolScore MCP 服务")
                return self.websocket_client
            except Exception as e:
                logger.error(f"连接 ToolScore MCP 服务失败: {e}")
                self.websocket_client = None
                raise

    async def _send_request(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """发送请求到ToolScore MCP服务并等待响应"""
        async with self.connection_lock:
            # 确保连接已建立
            if not self.websocket_client or self.websocket_client.closed:
                await self._connect_to_toolscore_mcp()
            
            # 再次检查以确保websocket_client不为None
            assert self.websocket_client is not None, "WebSocket客户端未连接。" # 添加断言

            try:
                await self.websocket_client.send(json.dumps(message))
                response = await self.websocket_client.recv()
                return json.loads(response)
            except ConnectionClosedOK:
                logger.warning("ToolScore MCP 连接已正常关闭，尝试重新连接并重试请求。")
                self.websocket_client = None # 清除旧的连接
                await self._connect_to_toolscore_mcp() # 重新连接
                assert self.websocket_client is not None, "WebSocket客户端重新连接失败。" # 添加断言
                await self.websocket_client.send(json.dumps(message))
                response = await self.websocket_client.recv()
                return json.loads(response)
            except ConnectionClosedError as e:
                logger.error(f"ToolScore MCP 连接异常关闭: {e}，尝试重新连接。")
                self.websocket_client = None # 清除旧的连接
                await self._connect_to_toolscore_mcp() # 重新连接
                assert self.websocket_client is not None, "WebSocket客户端重新连接失败。" # 添加断言
                await self.websocket_client.send(json.dumps(message))
                response = await self.websocket_client.recv()
                return json.loads(response)
            except Exception as e:
                logger.error(f"发送或接收ToolScore MCP消息失败: {e}", exc_info=True)
                raise

    async def wait_for_ready(self, timeout: int = 30) -> bool:
        """等待ToolScore服务就绪"""
        logger.info(f"等待ToolScore服务就绪... (超时: {timeout}秒)")
        try:
            await asyncio.wait_for(self._connect_to_toolscore_mcp(), timeout=timeout)
            logger.info("ToolScore服务已就绪")
            return True
        except asyncio.TimeoutError:
            logger.error(f"等待ToolScore服务超时 ({timeout}秒)")
            return False
        except Exception as e:
            logger.error(f"检查ToolScore服务就绪状态失败: {e}")
            return False

    async def get_available_tools(self) -> List[str]:
        """获取可用工具列表"""
        logger.info("请求可用工具列表...")
        message = {
            "type": "request",
            "action": "get_available_tools"
        }
        try:
            response = await self._send_request(message)
            if response.get("success"):
                return response.get("data", [])
            else:
                logger.error(f"获取可用工具失败: {response.get('error_message', '未知错误')}")
                return []
        except Exception as e:
            logger.error(f"获取可用工具时发生通信错误: {e}")
            return []

    async def request_tool_capability(self, capability_name: Optional[str] = None, requirements: Optional[Dict] = None,
                                     task_description: Optional[str] = None, required_capabilities: Optional[List[str]] = None,
                                     auto_install: bool = False) -> Dict:
        """请求工具能力"""
        if task_description and required_capabilities:
            capability_name = ", ".join(required_capabilities) if required_capabilities else task_description
        
        logger.info(f"请求工具能力: {capability_name}, 要求: {requirements}, 自动安装: {auto_install}")
        
        message = {
            "type": "request",
            "action": "request_tool_capability",
            "parameters": {
                "capability_name": capability_name,
                "requirements": requirements,
                "task_description": task_description,
                "required_capabilities": required_capabilities,
                "auto_install": auto_install
            }
        }
        try:
            response = await self._send_request(message)
            if response.get("success"):
                return response.get("data", {})
            else:
                logger.error(f"请求工具能力失败: {response.get('error_message', '未知错误')}")
                return {"success": False, "error": response.get('error_message', '未知错误')}
        except Exception as e:
            logger.error(f"请求工具能力时发生通信错误: {e}")
            return {"success": False, "error": f"通信错误: {e}"}

    async def execute_tool(self, tool_id: str, action: str, parameters: Optional[Dict] = None) -> Dict:
        """执行工具操作"""
        logger.info(f"执行工具: {tool_id}/{action}, 参数: {parameters}")
        
        message = {
            "type": "request",
            "action": "execute_tool",
            "parameters": {
                "tool_id": tool_id,
                "action": action,
                "parameters": parameters
            }
        }
        try:
            response = await self._send_request(message)
            if response.get("success"):
                return response.get("data", {})
            else:
                logger.error(f"执行工具失败: {response.get('error_message', '未知错误')}")
                return {"success": False, "error": response.get('error_message', '未知错误')}
        except Exception as e:
            logger.error(f"执行工具时发生通信错误: {e}")
            return {"success": False, "error": f"通信错误: {e}"}

    async def intelligent_recommend(self, task: TaskSpec) -> Dict:
        """智能工具推荐 - 通过ToolScore服务获取"""
        logger.debug(f"请求ToolScore服务推荐工具给任务类型: {task.task_type.value}")
        message = {
            "type": "request",
            "action": "intelligent_recommend",
            "parameters": {
                "task_type": task.task_type.value,
                "task_description": task.description,
                "task_context": task.context
            }
        }
        try:
            response = await self._send_request(message)
            if response.get("success"):
                return response.get("data", {})
            else:
                logger.error(f"智能推荐工具失败: {response.get('error_message', '未知错误')}")
                return {"recommended_tools": [], "confidence": 0.0, "reason": "推荐失败", "strategy": "service_error"}
        except Exception as e:
            logger.error(f"智能推荐工具时发生通信错误: {e}")
            return {"recommended_tools": [], "confidence": 0.0, "reason": f"通信错误: {e}", "strategy": "communication_error"}