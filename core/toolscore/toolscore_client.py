"""
增强的ToolScore客户端
集成增强的DynamicMCPManager和智能工具管理功能
"""

import logging
import asyncio
import json
from typing import Dict, Any, List, Optional
import websockets.legacy.client as websockets
from websockets.legacy.client import WebSocketClientProtocol
from websockets.exceptions import ConnectionClosedOK, ConnectionClosedError

from core.interfaces import TaskSpec, TaskType
from core.config_manager import ConfigManager
from .core_manager import CoreManager

logger = logging.getLogger(__name__)


class ToolScoreClient:
    """增强的ToolScore客户端，集成智能工具搜索和安装功能"""

    def __init__(self, config_manager: ConfigManager):
        self.config_manager = config_manager
        ports_config = self.config_manager.get_ports_config()
        
        # HTTP 端口用于REST API
        self.toolscore_http_port = ports_config['mcp_servers']['toolscore_http']['port']
        self.tool_service_url = f"http://localhost:{self.toolscore_http_port}"
        
        # MCP WebSocket 端口用于MCP通信
        self.toolscore_mcp_port = ports_config['mcp_servers']['toolscore_mcp']['port']
        self.toolscore_mcp_endpoint = f"ws://localhost:{self.toolscore_mcp_port}/websocket"
        
        self.websocket_client: Optional[WebSocketClientProtocol] = None
        self.connection_lock = asyncio.Lock()
        
        # 初始化增强的核心管理器
        self.core_manager = None
        self._initialization_lock = asyncio.Lock()
        
        logger.info("✅ 增强的ToolScoreClient初始化完成")
    
    async def _ensure_core_manager(self):
        """确保核心管理器已初始化"""
        if self.core_manager is None:
            async with self._initialization_lock:
                if self.core_manager is None:
                    logger.info("🚀 初始化增强的核心管理器...")
                    self.core_manager = CoreManager(config_manager=self.config_manager)
                    await self.core_manager.initialize()
                    logger.info("✅ 增强的核心管理器初始化完成")
    
    async def _connect_to_toolscore_mcp(self):
        """连接到ToolScore MCP服务"""
        if self.websocket_client and not self.websocket_client.closed:
            return
        
        try:
            logger.info(f"连接到ToolScore MCP: {self.toolscore_mcp_endpoint}")
            self.websocket_client = await websockets.connect(self.toolscore_mcp_endpoint)
            logger.info("✅ ToolScore MCP连接成功")
        except Exception as e:
            logger.error(f"❌ 连接ToolScore MCP失败: {e}")
            self.websocket_client = None
            raise
    
    async def _send_request(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """发送请求到ToolScore MCP服务并等待响应"""
        async with self.connection_lock:
            # 确保连接已建立
            if not self.websocket_client or self.websocket_client.closed:
                await self._connect_to_toolscore_mcp()
            
            assert self.websocket_client is not None, "WebSocket客户端未连接"
            
            try:
                await self.websocket_client.send(json.dumps(message))
                response = await self.websocket_client.recv()
                return json.loads(response)
            except (ConnectionClosedOK, ConnectionClosedError) as e:
                logger.warning(f"ToolScore MCP连接关闭: {e}, 尝试重新连接")
                self.websocket_client = None
                await self._connect_to_toolscore_mcp()
                assert self.websocket_client is not None, "WebSocket客户端重新连接失败"
                await self.websocket_client.send(json.dumps(message))
                response = await self.websocket_client.recv()
                return json.loads(response)
            except Exception as e:
                logger.error(f"❌ 发送或接收ToolScore MCP消息失败: {e}")
                raise
    
    async def wait_for_ready(self, timeout: int = 30) -> bool:
        """等待ToolScore服务就绪"""
        logger.info(f"等待增强的ToolScore服务就绪... (超时: {timeout}秒)")
        try:
            # 确保核心管理器已初始化
            await self._ensure_core_manager()
            
            # 尝试连接MCP服务
            await asyncio.wait_for(self._connect_to_toolscore_mcp(), timeout=timeout)
            logger.info("✅ 增强的ToolScore服务已就绪")
            return True
        except asyncio.TimeoutError:
            logger.error(f"❌ 等待ToolScore服务超时 ({timeout}秒)")
            return False
        except Exception as e:
            logger.error(f"❌ 检查ToolScore服务就绪状态失败: {e}")
            return False
    
    async def get_available_tools(self) -> List[str]:
        """获取可用工具列表（增强版本）"""
        try:
            await self._ensure_core_manager()
            
            # 使用增强的核心管理器获取工具列表
            tools_result = await self.core_manager.list_available_tools()
            
            if tools_result.get("success"):
                tool_names = []
                servers = tools_result.get("servers", {})
                for server_id, server_info in servers.items():
                    tools = server_info.get("tools", [])
                    for tool in tools:
                        tool_names.append(f"{server_id}.{tool.get('name', 'unknown')}")
                
                logger.info(f"🔧 获取到 {len(tool_names)} 个可用工具")
                return tool_names
            else:
                logger.warning("⚠️ 获取工具列表失败，尝试传统方式")
                # 回退到传统方式
                return await self._get_available_tools_fallback()
                
        except Exception as e:
            logger.error(f"❌ 获取可用工具列表失败: {e}")
            # 回退到传统方式
            return await self._get_available_tools_fallback()
    
    async def _get_available_tools_fallback(self) -> List[str]:
        """传统方式获取工具列表（回退机制）"""
        try:
            message = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/list"
            }
            response = await self._send_request(message)
            
            if response.get("result"):
                tools = response["result"].get("tools", [])
                return [tool.get("name", "") for tool in tools if tool.get("name")]
            return []
        except Exception as e:
            logger.error(f"❌ 传统方式获取工具列表也失败: {e}")
            return []
    
    async def execute_task(self, task_spec: TaskSpec) -> Dict[str, Any]:
        """执行任务（增强版本）"""
        try:
            await self._ensure_core_manager()
            
            logger.info(f"🎯 执行增强任务: {task_spec.task_description[:100]}...")
            
            # 如果任务需要工具搜索和安装
            if task_spec.task_type == TaskType.TOOL_SEARCH:
                return await self._execute_tool_search_task(task_spec)
            
            # 对于其他类型的任务，尝试智能工具调用
            return await self._execute_intelligent_task(task_spec)
            
        except Exception as e:
            logger.error(f"❌ 执行增强任务失败: {e}")
            # 回退到传统执行方式
            return await self._execute_task_fallback(task_spec)
    
    async def _execute_tool_search_task(self, task_spec: TaskSpec) -> Dict[str, Any]:
        """执行工具搜索任务"""
        try:
            # 使用增强的工具搜索和安装功能
            result = await self.core_manager.search_and_install_tools(
                query=task_spec.task_description,
                max_tools=3
            )
            
            if result["success"]:
                return {
                    "success": True,
                    "result": {
                        "installed_tools": result["installed_tools"],
                        "message": result["message"]
                    },
                    "task_type": task_spec.task_type.value,
                    "execution_method": "enhanced_search"
                }
            else:
                return {
                    "success": False,
                    "error": result["error_message"],
                    "task_type": task_spec.task_type.value,
                    "execution_method": "enhanced_search"
                }
                
        except Exception as e:
            logger.error(f"❌ 工具搜索任务执行失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "task_type": task_spec.task_type.value,
                "execution_method": "enhanced_search"
            }
    
    async def _execute_intelligent_task(self, task_spec: TaskSpec) -> Dict[str, Any]:
        """执行智能任务"""
        try:
            # 首先尝试分析任务需要什么工具
            task_keywords = self._extract_task_keywords(task_spec.task_description)
            
            # 如果识别出需要特定功能，尝试搜索相关工具
            if task_keywords:
                search_query = " ".join(task_keywords)
                logger.info(f"🔍 基于任务关键词搜索工具: {search_query}")
                
                search_result = await self.core_manager.search_and_install_tools(
                    query=search_query,
                    max_tools=2
                )
                
                if search_result["success"] and search_result["installed_tools"]:
                    # 尝试使用新安装的工具执行任务
                    for tool_info in search_result["installed_tools"]:
                        tool_id = tool_info.get("tool_id")
                        available_tools = tool_info.get("available_tools", [])
                        
                        if available_tools:
                            # 尝试调用第一个可用工具
                            tool_name = available_tools[0].get("name")
                            if tool_name:
                                result = await self.core_manager.call_tool(
                                    server_id=tool_id,
                                    tool_name=tool_name,
                                    arguments={"query": task_spec.task_description}
                                )
                                
                                if result.get("success"):
                                    return {
                                        "success": True,
                                        "result": result["result"],
                                        "task_type": task_spec.task_type.value,
                                        "execution_method": "intelligent_tool_call",
                                        "used_tool": f"{tool_id}.{tool_name}"
                                    }
            
            # 如果智能工具调用失败，回退到传统方式
            return await self._execute_task_fallback(task_spec)
            
        except Exception as e:
            logger.error(f"❌ 智能任务执行失败: {e}")
            return await self._execute_task_fallback(task_spec)
    
    def _extract_task_keywords(self, task_description: str) -> List[str]:
        """从任务描述中提取关键词"""
        keywords = []
        
        # 简单的关键词映射
        keyword_mapping = {
            "search": ["search", "find", "look", "查找", "搜索"],
            "browser": ["browse", "web", "website", "浏览", "网页"],
            "file": ["file", "document", "文件", "文档"],
            "data": ["data", "analyze", "数据", "分析"],
            "image": ["image", "picture", "photo", "图片", "图像"],
            "text": ["text", "write", "文本", "写作"]
        }
        
        task_lower = task_description.lower()
        
        for category, terms in keyword_mapping.items():
            if any(term in task_lower for term in terms):
                keywords.append(category)
        
        return keywords
    
    async def _execute_task_fallback(self, task_spec: TaskSpec) -> Dict[str, Any]:
        """传统方式执行任务（回退机制）"""
        try:
            message = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "execute_task",
                    "arguments": {
                        "task_description": task_spec.task_description,
                        "task_type": task_spec.task_type.value,
                        "expected_output": task_spec.expected_output,
                        "context": task_spec.context
                    }
                }
            }
            
            response = await self._send_request(message)
            
            if response.get("result"):
                return {
                    "success": True,
                    "result": response["result"],
                    "task_type": task_spec.task_type.value,
                    "execution_method": "fallback"
                }
            else:
                return {
                    "success": False,
                    "error": response.get("error", "未知错误"),
                    "task_type": task_spec.task_type.value,
                    "execution_method": "fallback"
                }
                
        except Exception as e:
            logger.error(f"❌ 传统方式执行任务也失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "task_type": task_spec.task_type.value,
                "execution_method": "fallback"
            }
    
    async def search_tools(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        """搜索工具（增强版本）"""
        try:
            await self._ensure_core_manager()
            
            logger.info(f"🔍 搜索工具: {query}")
            
            # 使用增强的搜索功能
            result = await self.core_manager.search_and_install_tools(query, max_results)
            
            if result["success"]:
                return result["installed_tools"]
            else:
                logger.warning(f"⚠️ 增强搜索失败: {result['error_message']}")
                return []
                
        except Exception as e:
            logger.error(f"❌ 搜索工具失败: {e}")
            return []
    
    async def get_system_status(self) -> Dict[str, Any]:
        """获取系统状态（增强版本）"""
        try:
            await self._ensure_core_manager()
            
            # 获取增强的系统状态
            enhanced_status = await self.core_manager.get_enhanced_status()
            
            return {
                "service_status": "running" if self.core_manager.is_running else "stopped",
                "enhanced_features": True,
                "detailed_status": enhanced_status
            }
            
        except Exception as e:
            logger.error(f"❌ 获取系统状态失败: {e}")
            return {
                "service_status": "error",
                "enhanced_features": False,
                "error": str(e)
            }
    
    async def close(self):
        """关闭客户端连接"""
        try:
            if self.websocket_client:
                await self.websocket_client.close()
                self.websocket_client = None
            
            if self.core_manager:
                await self.core_manager.stop()
                
            logger.info("✅ 增强的ToolScoreClient已关闭")
            
        except Exception as e:
            logger.error(f"❌ 关闭ToolScoreClient时出错: {e}")
    
    # 保持与原有接口的兼容性
    async def get_tool_description(self, tool_name: str) -> str:
        """获取工具描述"""
        try:
            # 实现工具描述获取逻辑
            return f"Tool: {tool_name}"
        except Exception:
            return f"Tool: {tool_name} (description unavailable)"