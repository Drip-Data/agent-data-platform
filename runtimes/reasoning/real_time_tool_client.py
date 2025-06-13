"""
实时工具客户端 - Enhanced Reasoning Runtime专用
通过WebSocket监听工具变更，立即响应新工具可用性
"""

import asyncio
import json
import logging
import websockets
import time
from typing import Dict, Any, List, Callable, Optional

logger = logging.getLogger(__name__)

class RealTimeToolClient:
    """实时工具客户端 - 立即感知新工具的可用性"""
    
    def __init__(self, toolscore_endpoint: str):
        self.endpoint = toolscore_endpoint.rstrip('/')
        self.websocket = None
        self.available_tools_cache = {}  # 本地工具缓存
        self.tool_update_callbacks = []  # 工具更新回调函数
        self.pending_tool_requests = {}  # 等待工具安装的任务
        self.is_connected = False
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 10
        self.reconnect_delay = 5  # 秒
        
    async def connect_real_time_updates(self):
        """连接到ToolScore的实时更新流"""
        # 处理WebSocket端点
        if self.endpoint.startswith('ws://') or self.endpoint.startswith('wss://'):
            websocket_url = f"{self.endpoint}/api/v1/events/tools"
        else:
            # 将HTTP端点转换为WebSocket端点
            websocket_url = self.endpoint.replace('http://', 'ws://').replace('https://', 'wss://')
            websocket_url = f"{websocket_url}/api/v1/events/tools"
        
        try:
            logger.info(f"🔌 连接到ToolScore实时更新: {websocket_url}")
            # 创建WebSocket连接（兼容旧版本websockets）
            try:
                # 首选 websockets 库客户端
                try:
                    self.websocket = await websockets.connect(
                        websocket_url,
                        extra_headers={
                            "User-Agent": "Enhanced-Reasoning-Runtime/1.0"
                        }
                    )
                except TypeError:
                    # 兼容旧版本websockets，不支持 extra_headers
                    self.websocket = await websockets.connect(websocket_url)
            except Exception as ws_err:
                logger.warning(f"websockets.connect 失败: {ws_err}，尝试使用 aiohttp ClientSession 作为后备方案")
                try:
                    import aiohttp
                    session = aiohttp.ClientSession()
                    self.websocket = await session.ws_connect(websocket_url, headers={"User-Agent": "Enhanced-Reasoning-Runtime/1.0"})
                except Exception as aio_err:
                    logger.error(f"aiohttp ws_connect 同样失败: {aio_err}")
                    raise aio_err
            self.is_connected = True
            self.reconnect_attempts = 0
            
            # 启动监听任务
            asyncio.create_task(self._listen_for_updates())
            logger.info("✅ 已连接到ToolScore实时更新流")
            
        except Exception as e:
            logger.error(f"❌ 连接ToolScore实时更新失败: {e}")
            self.is_connected = False
            # 启动重连机制
            if self.reconnect_attempts < self.max_reconnect_attempts:
                asyncio.create_task(self._reconnect_with_delay())
    
    async def _reconnect_with_delay(self):
        """延迟重连机制"""
        self.reconnect_attempts += 1
        delay = min(self.reconnect_delay * self.reconnect_attempts, 60)  # 最大60秒
        
        logger.info(f"⏳ {delay}秒后尝试重连 (第{self.reconnect_attempts}次)")
        await asyncio.sleep(delay)
        await self.connect_real_time_updates()
    
    async def _listen_for_updates(self):
        """监听工具更新事件"""
        try:
            import aiohttp
            async for message in self.websocket:
                try:
                    # websockets 库 -> str / bytes
                    # aiohttp        -> WSMessage 对象
                    if isinstance(message, aiohttp.WSMessage):
                        if message.type == aiohttp.WSMsgType.TEXT:
                            payload = message.data
                        elif message.type == aiohttp.WSMsgType.BINARY:
                            payload = message.data.decode()
                        elif message.type == aiohttp.WSMsgType.ERROR:
                            logger.error(f"WebSocket错误消息: {message.data}")
                            continue
                        else:
                            # ping/pong/close 等
                            continue
                    else:
                        # websockets 返回的 str/bytes
                        payload = message

                    event = json.loads(payload)
                    await self._handle_tool_event(event)
                except json.JSONDecodeError as e:
                    logger.error(f"解析WebSocket消息失败: {e}")
                except Exception as e:
                    logger.error(f"处理工具事件失败: {e}")
                    
        except websockets.exceptions.ConnectionClosed:
            logger.warning("🔌 WebSocket连接已断开")
            self.is_connected = False
            # 尝试重连
            if self.reconnect_attempts < self.max_reconnect_attempts:
                await self._reconnect_with_delay()
        except Exception as e:
            logger.error(f"❌ WebSocket监听异常: {e}")
            self.is_connected = False
    
    async def _handle_tool_event(self, event: Dict[str, Any]):
        """处理工具事件"""
        event_type = event.get("type")
        
        if event_type == "tool_installed":
            await self._handle_tool_installed(event)
        elif event_type == "tool_uninstalled":
            await self._handle_tool_uninstalled(event)
        elif event_type == "tool_updated":
            await self._handle_tool_updated(event)
        else:
            logger.debug(f"收到未知事件类型: {event_type}")
    
    async def _handle_tool_installed(self, event: Dict[str, Any]):
        """处理工具安装事件"""
        tool_id = event.get("tool_id")
        tool_name = event.get("name", tool_id)
        
        logger.info(f"🎉 新工具已安装: {tool_name} ({tool_id})")
        
        # 立即更新本地缓存，确保包含所有必要字段
        self.available_tools_cache[tool_id] = {
            "tool_id": tool_id,
            "name": tool_name,
            "description": event.get("description", f"Tool {tool_name}"),
            "capabilities": event.get("capabilities", []),
            "tool_type": event.get("tool_type", "function")
        }
        
        # 通知所有注册的回调
        await self._notify_tool_available(self.available_tools_cache[tool_id])
        
        # 检查是否有等待这个工具的任务
        await self._check_pending_requests(self.available_tools_cache[tool_id])
    
    async def _handle_tool_uninstalled(self, event: Dict[str, Any]):
        """处理工具卸载事件"""
        tool_id = event.get("tool_id")
        tool_name = event.get("name", tool_id)
        
        logger.info(f"📤 工具已卸载: {tool_name} ({tool_id})")
        
        # 从本地缓存移除
        self.available_tools_cache.pop(tool_id, None)
    
    async def _handle_tool_updated(self, event: Dict[str, Any]):
        """处理工具更新事件"""
        tool_id = event.get("tool_id")
        tool_name = event.get("name", tool_id)
        
        logger.info(f"🔄 工具已更新: {tool_name} ({tool_id})")
        
        # 更新本地缓存
        self.available_tools_cache[tool_id] = event
    
    async def _notify_tool_available(self, tool_event: Dict[str, Any]):
        """通知所有回调新工具可用"""
        for callback in self.tool_update_callbacks:
            try:
                await callback(tool_event)
            except Exception as e:
                logger.error(f"工具更新回调执行失败: {e}")
    
    async def _check_pending_requests(self, tool_event: Dict[str, Any]):
        """检查是否有等待这个工具的任务"""
        tool_capabilities = tool_event.get("capabilities", [])
        tool_id = tool_event.get("tool_id")
        
        completed_requests = []
        
        for request_id, request_info in self.pending_tool_requests.items():
            required_capabilities = request_info.get("required_capabilities", [])
            
            # 检查工具是否满足需求
            if self._tool_matches_requirement(tool_event, required_capabilities):
                logger.info(f"🚀 恢复等待任务: {request_id} (新工具: {tool_id})")
                
                # 执行回调
                callback = request_info.get("callback")
                if callback:
                    try:
                        await callback(tool_event)
                    except Exception as e:
                        logger.error(f"恢复任务回调执行失败: {e}")
                
                completed_requests.append(request_id)
        
        # 清理已完成的请求
        for request_id in completed_requests:
            self.pending_tool_requests.pop(request_id, None)
    
    def _tool_matches_requirement(self, tool_event: Dict[str, Any], 
                                required_capabilities: List[str]) -> bool:
        """检查工具是否满足需求"""
        if not required_capabilities:
            return True
        
        tool_capabilities = tool_event.get("capabilities", [])
        tool_capability_names = []
        
        # 提取能力名称
        for cap in tool_capabilities:
            if isinstance(cap, dict):
                tool_capability_names.append(cap.get("name", ""))
            elif isinstance(cap, str):
                tool_capability_names.append(cap)
        
        # 检查是否有匹配的能力
        for required_cap in required_capabilities:
            for tool_cap in tool_capability_names:
                if required_cap.lower() in tool_cap.lower() or tool_cap.lower() in required_cap.lower():
                    return True
        
        return False
    
    async def register_tool_update_callback(self, callback: Callable):
        """注册工具更新回调"""
        self.tool_update_callbacks.append(callback)
        logger.debug(f"已注册工具更新回调，当前回调数量: {len(self.tool_update_callbacks)}")
    
    async def register_pending_request(self, request_id: str, 
                                     required_capabilities: List[str],
                                     callback: Callable = None):
        """注册等待工具的请求"""
        self.pending_tool_requests[request_id] = {
            "required_capabilities": required_capabilities,
            "callback": callback,
            "timestamp": time.time()
        }
        logger.info(f"注册等待工具请求: {request_id} (需要: {required_capabilities})")
    
    async def get_fresh_tools_for_llm(self, fallback_client=None) -> str:
        """获取最新的工具列表，包括刚刚安装的"""
        tool_descriptions = []
        
        # 获取已注册的工具
        if fallback_client:
            try:
                registered_tools = await fallback_client.get_available_tools()
                if registered_tools and registered_tools.get("available_tools"):
                    tool_descriptions.append("# 已注册的工具")
                    for tool in registered_tools["available_tools"]:
                        tool_id = tool.get("tool_id", "unknown")
                        name = tool.get("name", tool_id)
                        tool_type = tool.get("tool_type", "unknown")
                        description = tool.get("description", f"Tool {name}")
                        capabilities = tool.get("capabilities", [])
                        
                        desc = f"- {tool_id} ({name}): {description}"
                        if capabilities:
                            cap_names = []
                            for cap in capabilities:
                                if isinstance(cap, dict):
                                    cap_names.append(cap.get("name", ""))
                                elif isinstance(cap, str):
                                    cap_names.append(cap)
                            if cap_names:
                                desc += f" (能力: {', '.join(cap_names)})"
                        desc += f" [{tool_type}类型]"
                        tool_descriptions.append(desc)
            except Exception as e:
                logger.error(f"获取已注册工具列表失败: {e}")
        
        # 如果有缓存的工具，添加实时安装的工具
        if self.available_tools_cache:
            cached_tools = []
            
            for tool_id, tool_info in self.available_tools_cache.items():
                name = tool_info.get("name", tool_id)
                description = tool_info.get("description", f"Tool {name}")
                capabilities = tool_info.get("capabilities", [])
                tool_type = tool_info.get("tool_type", "function")
                
                desc = f"- {tool_id} ({name}): {description}"
                if capabilities:
                    cap_names = []
                    for cap in capabilities:
                        if isinstance(cap, dict):
                            cap_names.append(cap.get("name", ""))
                        elif isinstance(cap, str):
                            cap_names.append(cap)
                    if cap_names:
                        desc += f" (能力: {', '.join(cap_names)})"
                desc += f" [{tool_type}类型]"
                cached_tools.append(desc)
            
            if cached_tools:
                tool_descriptions.append("# 实时安装的工具")
                tool_descriptions.extend(cached_tools)
            
            logger.debug(f"使用缓存的工具列表，包含 {len(self.available_tools_cache)} 个工具")
        
        final_description = "\n".join(tool_descriptions) if tool_descriptions else "暂无可用工具"
        
        # 🔍 新增：记录工具信息获取情况
        tool_count = len([line for line in final_description.split('\n') if line.strip().startswith('-')])
        logger.info(f"📋 工具信息获取完成: {tool_count} 个工具, 描述长度: {len(final_description)} 字符")
        
        return final_description
    
    async def _load_base_tools_from_json(self) -> str:
        """从mcp_tools.json加载基础工具信息"""
        try:
            import json
            import os
            
            # 尝试多个可能的路径
            possible_paths = [
                "/app/mcp_tools.json",
                "mcp_tools.json", 
                "../mcp_tools.json",
                "../../mcp_tools.json"
            ]
            
            tools_data = None
            used_path = None
            
            for path in possible_paths:
                if os.path.exists(path):
                    with open(path, 'r', encoding='utf-8') as f:
                        tools_data = json.load(f)
                    used_path = path
                    break
            
            if not tools_data:
                logger.warning("未找到mcp_tools.json文件")
                return ""
            
            logger.info(f"📖 从 {used_path} 加载了 {len(tools_data)} 个基础工具")
            
            # 格式化工具信息供LLM使用
            tool_descriptions = []
            for tool in tools_data[:50]:  # 限制数量避免prompt过长
                tool_id = tool.get("tool_id", tool.get("id", "unknown"))
                name = tool.get("name", tool_id)
                description = tool.get("description", "")
                capabilities = tool.get("capabilities", [])
                
                desc = f"- {tool_id}: {description}"
                
                if capabilities:
                    cap_str = ", ".join(capabilities) if isinstance(capabilities, list) else str(capabilities)
                    desc += f" (能力: {cap_str})"
                
                tool_descriptions.append(desc)
            
            result = "\n".join(tool_descriptions)
            
            if len(tools_data) > 50:
                result += f"\n... 还有 {len(tools_data) - 50} 个工具可通过mcp-search-tool查询"
                
            return result
            
        except Exception as e:
            logger.error(f"加载mcp_tools.json失败: {e}")
            return ""
    
    async def cleanup_expired_requests(self, max_age_seconds: int = 300):
        """清理过期的等待请求"""
        current_time = time.time()
        expired_requests = []
        
        for request_id, request_info in self.pending_tool_requests.items():
            if current_time - request_info["timestamp"] > max_age_seconds:
                expired_requests.append(request_id)
        
        for request_id in expired_requests:
            self.pending_tool_requests.pop(request_id, None)
            logger.info(f"清理过期等待请求: {request_id}")
    
    @property
    def connection_status(self) -> str:
        """获取连接状态"""
        if self.is_connected:
            return "connected"
        elif self.reconnect_attempts < self.max_reconnect_attempts:
            return "reconnecting"
        else:
            return "disconnected"
    
    async def close(self):
        """关闭WebSocket连接"""
        if self.websocket:
            await self.websocket.close()
            self.websocket = None
        self.is_connected = False
        logger.info("🔌 实时工具客户端已关闭") 