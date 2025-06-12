"""
工具同步管理器
实现集中式工具注册和实时状态同步机制
"""

import asyncio
import json
import logging
import time
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, asdict
import redis.asyncio as redis

logger = logging.getLogger(__name__)

@dataclass
class ToolEvent:
    """工具事件"""
    event_type: str  # 'register', 'unregister', 'update', 'status_change'
    tool_id: str
    tool_spec: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None
    source_service: str = ""
    timestamp: float = 0.0
    
    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()

class ToolSyncManager:
    """
    工具同步管理器
    
    职责：
    1. 管理工具注册事件的发布和订阅
    2. 实现服务间的工具状态同步
    3. 提供工具缓存管理功能
    4. 处理工具执行时的状态协调
    """
    
    def __init__(self, redis_url: str, service_id: str):
        self.redis_url = redis_url
        self.service_id = service_id
        self.redis_client: Optional[redis.Redis] = None
        self.pubsub = None
        
        # 本地工具缓存
        self._tool_cache: Dict[str, Dict[str, Any]] = {}
        self._cache_lock = asyncio.Lock()
        
        # 事件处理器
        self._event_handlers: Dict[str, List[Callable]] = {}
        
        # 同步任务
        self._sync_task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._is_running = False
        
        # 同步状态
        self._last_sync_time = 0.0
        self._sync_interval = 30.0  # 30秒同步一次
        
        logger.info(f"工具同步管理器初始化: {service_id}")
    
    async def initialize(self):
        """初始化同步管理器"""
        try:
            # 连接Redis
            self.redis_client = redis.from_url(self.redis_url)
            await self.redis_client.ping()
            
            # 初始化Pub/Sub
            self.pubsub = self.redis_client.pubsub()
            await self.pubsub.subscribe('tool_events')
            
            # 启动事件监听任务
            self._sync_task = asyncio.create_task(self._event_listener())
            
            # 启动心跳任务
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
            
            self._is_running = True
            
            logger.info("✅ 工具同步管理器启动成功")
            
        except Exception as e:
            logger.error(f"❌ 工具同步管理器初始化失败: {e}")
            raise
    
    async def cleanup(self):
        """清理资源"""
        self._is_running = False
        
        if self._sync_task:
            self._sync_task.cancel()
            try:
                await self._sync_task
            except asyncio.CancelledError:
                pass
        
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
        
        if self.pubsub:
            await self.pubsub.close()
        
        if self.redis_client:
            await self.redis_client.close()
            
        logger.info("工具同步管理器已清理")
    
    def register_event_handler(self, event_type: str, handler: Callable):
        """注册事件处理器"""
        if event_type not in self._event_handlers:
            self._event_handlers[event_type] = []
        self._event_handlers[event_type].append(handler)
        logger.debug(f"注册事件处理器: {event_type}")
    
    async def publish_tool_event(self, event: ToolEvent):
        """发布工具事件"""
        try:
            event.source_service = self.service_id
            event_data = asdict(event)
            
            await self.redis_client.publish('tool_events', json.dumps(event_data))
            logger.info(f"📢 发布工具事件: {event.event_type} - {event.tool_id}")
            
        except Exception as e:
            logger.error(f"❌ 发布工具事件失败: {e}")
    
    async def _event_listener(self):
        """事件监听器"""
        logger.info("🎧 开始监听工具事件...")
        
        try:
            while self._is_running:
                try:
                    message = await asyncio.wait_for(
                        self.pubsub.get_message(ignore_subscribe_messages=True),
                        timeout=1.0
                    )
                    
                    if message and message['type'] == 'message':
                        await self._handle_tool_event(message['data'])
                        
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    logger.error(f"❌ 处理工具事件时出错: {e}")
                    await asyncio.sleep(1)
                    
        except asyncio.CancelledError:
            logger.info("工具事件监听器已停止")
        except Exception as e:
            logger.error(f"❌ 工具事件监听器异常退出: {e}")
    
    async def _heartbeat_loop(self):
        """心跳循环 - 定期同步和健康检查"""
        logger.info("💓 启动心跳循环...")
        
        try:
            while self._is_running:
                try:
                    # 记录心跳
                    await self._record_heartbeat()
                    
                    # 检查是否需要同步
                    current_time = time.time()
                    if current_time - self._last_sync_time > self._sync_interval:
                        await self._periodic_sync()
                        self._last_sync_time = current_time
                    
                    await asyncio.sleep(10)  # 每10秒心跳一次
                    
                except Exception as e:
                    logger.error(f"❌ 心跳循环出错: {e}")
                    await asyncio.sleep(5)
                    
        except asyncio.CancelledError:
            logger.info("心跳循环已停止")
    
    async def _record_heartbeat(self):
        """记录服务心跳"""
        try:
            heartbeat_data = {
                "service_id": self.service_id,
                "timestamp": time.time(),
                "status": "active",
                "cached_tools_count": len(self._tool_cache)
            }
            
            await self.redis_client.setex(
                f"heartbeat:{self.service_id}",
                30,  # 30秒过期
                json.dumps(heartbeat_data)
            )
            
        except Exception as e:
            logger.error(f"❌ 记录心跳失败: {e}")
    
    async def _periodic_sync(self):
        """定期同步"""
        logger.debug("🔄 执行定期同步...")
        
        try:
            # 检查中央注册中心的工具列表
            # 如果发现不一致，触发重新同步
            pass
            
        except Exception as e:
            logger.error(f"❌ 定期同步失败: {e}")
    
    async def _handle_tool_event(self, message_data):
        """处理工具事件"""
        try:
            event_data = json.loads(message_data)
            event = ToolEvent(**event_data)
            
            # 忽略自己发布的事件
            if event.source_service == self.service_id:
                return
            
            logger.info(f"📥 收到工具事件: {event.event_type} - {event.tool_id} (来自 {event.source_service})")
            
            # 更新本地缓存
            await self._update_local_cache(event)
            
            # 调用注册的事件处理器
            handlers = self._event_handlers.get(event.event_type, [])
            for handler in handlers:
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler(event)
                    else:
                        handler(event)
                except Exception as e:
                    logger.error(f"❌ 事件处理器执行失败: {e}")
                    
        except Exception as e:
            logger.error(f"❌ 处理工具事件失败: {e}")
    
    async def _update_local_cache(self, event: ToolEvent):
        """更新本地工具缓存"""
        async with self._cache_lock:
            if event.event_type == 'register':
                if event.tool_spec:
                    self._tool_cache[event.tool_id] = event.tool_spec
                    logger.debug(f"📝 工具缓存已更新: {event.tool_id}")
                    
            elif event.event_type == 'unregister':
                if event.tool_id in self._tool_cache:
                    del self._tool_cache[event.tool_id]
                    logger.debug(f"🗑️ 工具缓存已删除: {event.tool_id}")
                    
            elif event.event_type == 'update':
                if event.tool_spec and event.tool_id in self._tool_cache:
                    self._tool_cache[event.tool_id].update(event.tool_spec)
                    logger.debug(f"🔄 工具缓存已更新: {event.tool_id}")
    
    async def get_cached_tools(self) -> Dict[str, Dict[str, Any]]:
        """获取缓存的工具列表"""
        async with self._cache_lock:
            return self._tool_cache.copy()
    
    async def get_cached_tool(self, tool_id: str) -> Optional[Dict[str, Any]]:
        """获取缓存的工具"""
        async with self._cache_lock:
            return self._tool_cache.get(tool_id)
    
    async def sync_tools_from_central(self, central_endpoint: str):
        """从中央注册中心同步工具"""
        try:
            import aiohttp
            
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{central_endpoint}/tools") as response:
                    if response.status == 200:
                        result = await response.json()
                        tools = result.get("tools", [])
                        
                        async with self._cache_lock:
                            # 清空现有缓存
                            self._tool_cache.clear()
                            
                            # 重新填充缓存
                            for tool in tools:
                                tool_id = tool.get("tool_id")
                                if tool_id:
                                    self._tool_cache[tool_id] = tool
                        
                        logger.info(f"✅ 从中央注册中心同步了 {len(tools)} 个工具")
                        return True
                    else:
                        logger.error(f"❌ 同步工具失败: HTTP {response.status}")
                        return False
                        
        except Exception as e:
            logger.error(f"❌ 从中央注册中心同步工具失败: {e}")
            return False
    
    async def register_tool_to_central(self, tool_spec: Dict[str, Any], central_endpoint: str) -> bool:
        """向中央注册中心注册工具"""
        try:
            import aiohttp
            
            registration_data = {"tool_spec": tool_spec}
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{central_endpoint}/admin/tools/register",
                    json=registration_data,
                    headers={"Content-Type": "application/json"}
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        if result.get("success"):
                            logger.info(f"✅ 工具已注册到中央注册中心: {tool_spec.get('tool_id')}")
                            
                            # 发布注册事件
                            event = ToolEvent(
                                event_type="register",
                                tool_id=tool_spec.get("tool_id"),
                                tool_spec=tool_spec
                            )
                            await self.publish_tool_event(event)
                            return True
                        else:
                            logger.error(f"❌ 中央注册中心拒绝注册: {result.get('message')}")
                            return False
                    else:
                        logger.error(f"❌ 注册请求失败: HTTP {response.status}")
                        return False
                        
        except Exception as e:
            logger.error(f"❌ 向中央注册中心注册工具失败: {e}")
            return False
    
    async def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        async with self._cache_lock:
            return {
                "cached_tools_count": len(self._tool_cache),
                "cached_tools": list(self._tool_cache.keys()),
                "service_id": self.service_id,
                "is_running": self._is_running,
                "last_sync_time": self._last_sync_time,
                "event_handlers": {
                    event_type: len(handlers) 
                    for event_type, handlers in self._event_handlers.items()
                }
            }


class ToolExecutionCoordinator:
    """
    工具执行协调器
    
    职责：
    1. 协调工具执行过程中的状态同步
    2. 处理执行时的服务间通信
    3. 管理执行上下文和状态传递
    """
    
    def __init__(self, sync_manager: ToolSyncManager):
        self.sync_manager = sync_manager
        self._execution_contexts: Dict[str, Dict[str, Any]] = {}
        self._context_lock = asyncio.Lock()
        
    async def start_execution_context(self, execution_id: str, context: Dict[str, Any]):
        """启动执行上下文"""
        async with self._context_lock:
            self._execution_contexts[execution_id] = {
                "context": context,
                "start_time": time.time(),
                "status": "running"
            }
        
        # 发布执行开始事件
        event = ToolEvent(
            event_type="execution_start",
            tool_id=context.get("tool_id", "unknown"),
            metadata={
                "execution_id": execution_id,
                "context": context
            }
        )
        await self.sync_manager.publish_tool_event(event)
        
        logger.info(f"🚀 工具执行上下文启动: {execution_id}")
    
    async def update_execution_context(self, execution_id: str, updates: Dict[str, Any]):
        """更新执行上下文"""
        async with self._context_lock:
            if execution_id in self._execution_contexts:
                self._execution_contexts[execution_id]["context"].update(updates)
                
                # 发布上下文更新事件
                event = ToolEvent(
                    event_type="execution_update",
                    tool_id=self._execution_contexts[execution_id]["context"].get("tool_id", "unknown"),
                    metadata={
                        "execution_id": execution_id,
                        "updates": updates
                    }
                )
                await self.sync_manager.publish_tool_event(event)
                
                logger.debug(f"🔄 执行上下文已更新: {execution_id}")
    
    async def finish_execution_context(self, execution_id: str, result: Dict[str, Any]):
        """结束执行上下文"""
        async with self._context_lock:
            if execution_id in self._execution_contexts:
                context = self._execution_contexts[execution_id]
                context["status"] = "completed"
                context["end_time"] = time.time()
                context["result"] = result
                
                # 发布执行完成事件
                event = ToolEvent(
                    event_type="execution_finish",
                    tool_id=context["context"].get("tool_id", "unknown"),
                    metadata={
                        "execution_id": execution_id,
                        "result": result,
                        "duration": context["end_time"] - context["start_time"]
                    }
                )
                await self.sync_manager.publish_tool_event(event)
                
                # 清理上下文（保留一段时间用于调试）
                await asyncio.sleep(60)  # 保留1分钟
                if execution_id in self._execution_contexts:
                    del self._execution_contexts[execution_id]
                
                logger.info(f"✅ 工具执行上下文完成: {execution_id}")
    
    async def get_execution_context(self, execution_id: str) -> Optional[Dict[str, Any]]:
        """获取执行上下文"""
        async with self._context_lock:
            return self._execution_contexts.get(execution_id)
    
    async def get_active_executions(self) -> List[str]:
        """获取活跃的执行上下文ID列表"""
        async with self._context_lock:
            return list(self._execution_contexts.keys()) 