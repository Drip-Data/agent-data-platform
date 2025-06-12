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
        websocket_url = self.endpoint.replace('http://', 'ws://').replace('https://', 'wss://')
        websocket_url = f"{websocket_url}/api/v1/events/tools"
        
        try:
            logger.info(f"🔌 连接到ToolScore实时更新: {websocket_url}")
            self.websocket = await websockets.connect(websocket_url)
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
            async for message in self.websocket:
                try:
                    event = json.loads(message)
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
        
        # 立即更新本地缓存
        self.available_tools_cache[tool_id] = event
        
        # 通知所有注册的回调
        await self._notify_tool_available(event)
        
        # 检查是否有等待这个工具的任务
        await self._check_pending_requests(event)
    
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
        # 如果有缓存的工具，优先使用
        if self.available_tools_cache:
            tool_descriptions = []
            
            for tool_id, tool_info in self.available_tools_cache.items():
                name = tool_info.get("name", tool_id)
                description = tool_info.get("description", "No description")
                capabilities = tool_info.get("capabilities", [])
                
                desc = f"- {tool_id}: {description}"
                
                if capabilities:
                    cap_names = []
                    for cap in capabilities:
                        if isinstance(cap, dict):
                            cap_names.append(cap.get("name", ""))
                        elif isinstance(cap, str):
                            cap_names.append(cap)
                    
                    if cap_names:
                        desc += f" (能力: {', '.join(cap_names)})"
                
                tool_descriptions.append(desc)
            
            cached_description = "\n".join(tool_descriptions)
            logger.debug(f"使用缓存的工具列表，包含 {len(self.available_tools_cache)} 个工具")
        else:
            cached_description = ""
        
        # 如果有fallback客户端，获取服务器端工具并合并
        if fallback_client:
            try:
                server_description = await fallback_client.get_available_tools_for_llm()
                if server_description and cached_description:
                    return f"{cached_description}\n{server_description}"
                elif server_description:
                    return server_description
            except Exception as e:
                logger.error(f"获取服务器端工具列表失败: {e}")
        
        return cached_description or "暂无可用工具"
    
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