import asyncio
import json
import logging
import time
import websockets.legacy.client as websockets_client
import websockets.exceptions
from typing import Dict, Any, List, Optional

from .interfaces import ToolSpec, ExecutionResult, RegistrationResult, ToolCapability, ToolType, MCPServerSpec, FunctionToolSpec, ErrorType

logger = logging.getLogger(__name__)

class MCPToolClient:
    """
    MCP工具客户端 - 增强版本
    用于ReasoningRuntime连接到远程UnifiedToolLibrary (toolscore MCP Server)
    并通过WebSocket协议进行工具的发现和执行。
    
    增强功能：
    - 连接重试和指数退避
    - 心跳检测和健康监控
    - 连接池和故障转移
    - 详细的连接状态追踪
    """
    def __init__(self, toolscore_endpoint: str):
        self.toolscore_endpoint = toolscore_endpoint
        self.websocket: Optional[websockets_client.WebSocketClientProtocol] = None
        self._connected = False
        
        # 🔧 增强：连接重试配置
        self.max_retries = 3
        self.retry_delays = [1, 2, 4]  # 指数退避
        self.connection_timeout = 10.0
        self.request_timeout = 30.0
        
        # 🔧 增强：连接健康监控
        self._connection_lock = asyncio.Lock()
        self._last_ping_time = 0
        self._last_successful_request = 0
        self._connection_failures = 0
        self._max_failures_before_reset = 3
        self._health_check_interval = 30.0
        self._health_check_task = None
        
        # 🔧 增强：连接状态追踪
        self._connection_stats = {
            'total_connections': 0,
            'successful_connections': 0,
            'failed_connections': 0,
            'total_requests': 0,
            'failed_requests': 0,
            'reconnection_attempts': 0,
            'last_connection_time': 0,
            'total_uptime': 0,
            'connection_drops': 0
        }
        
        # 🔧 增强：故障转移和负载均衡
        self._backup_endpoints = []
        self._current_endpoint_index = 0
        self._endpoint_health_scores = {}
        
        # 🔧 增强：请求队列和批处理
        self._request_queue = asyncio.Queue(maxsize=100)
        self._batch_processor_task = None
        self._enable_batching = False
        
        logger.info(f"Enhanced MCPToolClient initialized for toolscore at {toolscore_endpoint}")
        
    def add_backup_endpoint(self, endpoint: str, priority: int = 1):
        """添加备份端点"""
        self._backup_endpoints.append({
            'endpoint': endpoint,
            'priority': priority,
            'health_score': 100,
            'last_used': 0
        })
        self._backup_endpoints.sort(key=lambda x: x['priority'])
        logger.info(f"🔄 添加备份端点: {endpoint} (优先级: {priority})")
    
    def enable_request_batching(self, batch_size: int = 5, batch_timeout: float = 1.0):
        """启用请求批处理"""
        self._enable_batching = True
        self._batch_size = batch_size
        self._batch_timeout = batch_timeout
        if not self._batch_processor_task:
            self._batch_processor_task = asyncio.create_task(self._batch_processor())
        logger.info(f"🚀 启用请求批处理 (批次大小: {batch_size}, 超时: {batch_timeout}s)")

    async def connect(self):
        """连接到toolscore MCP Server - 增强版本，支持重试和健康检查"""
        async with self._connection_lock:
            # 检查现有连接的健康状态
            if self._connected and self.websocket and await self._is_connection_healthy():
                logger.debug("Already connected to toolscore and connection is healthy")
                return
            
            # 关闭可能存在的不健康连接
            if self.websocket:
                await self._close_connection()
            
            self._connection_stats['total_connections'] += 1
            
            # 使用指数退避重试连接
            for attempt in range(self.max_retries):
                try:
                    delay = self.retry_delays[min(attempt, len(self.retry_delays) - 1)]
                    if attempt > 0:
                        logger.info(f"🔄 重试连接 (尝试 {attempt + 1}/{self.max_retries})，等待 {delay}s...")
                        await asyncio.sleep(delay)
                        self._connection_stats['reconnection_attempts'] += 1
                    
                    logger.info(f"🔌 连接到 toolscore: {self.toolscore_endpoint} (尝试 {attempt + 1})")
                    
                    # 使用超时连接
                    self.websocket = await asyncio.wait_for(
                        websockets_client.connect(
                            self.toolscore_endpoint,
                            ping_interval=20,  # 20秒心跳
                            ping_timeout=10,   # 10秒心跳超时
                            close_timeout=5    # 5秒关闭超时
                        ),
                        timeout=self.connection_timeout
                    )
                    
                    current_time = asyncio.get_event_loop().time()
                    self._connected = True
                    self._connection_failures = 0
                    self._last_successful_request = current_time
                    self._connection_stats['successful_connections'] += 1
                    self._connection_stats['last_connection_time'] = current_time
                    self._endpoint_health_scores[self.toolscore_endpoint] = min(100, self._endpoint_health_scores.get(self.toolscore_endpoint, 0) + 20)
                    
                    # 启动健康检查任务
                    await self._start_health_check()
                    
                    logger.info(f"✅ 成功连接到 toolscore: {self.toolscore_endpoint}")
                    return
                    
                except asyncio.TimeoutError:
                    logger.warning(f"⏰ 连接超时 (尝试 {attempt + 1}/{self.max_retries})")
                    self._connection_stats['failed_connections'] += 1
                except Exception as e:
                    logger.error(f"❌ 连接失败 (尝试 {attempt + 1}/{self.max_retries}): {e}")
                    self._connection_stats['failed_connections'] += 1
                    # 降低当前端点的健康评分
                    current_score = self._endpoint_health_scores.get(self.toolscore_endpoint, 100)
                    self._endpoint_health_scores[self.toolscore_endpoint] = max(0, current_score - 25)
                    
                    # 如果有备份端点且当前端点健康评分过低，尝试切换
                    if (self._backup_endpoints and 
                        self._endpoint_health_scores.get(self.toolscore_endpoint, 0) < 50 and 
                        attempt == self.max_retries - 1):
                        logger.info("🔄 尝试切换到备份端点...")
                        if await self._try_backup_endpoints():
                            return  # 成功连接到备份端点
            
            # 所有重试都失败了
            self._connected = False
            self._connection_failures += 1
            error_msg = f"无法连接到 toolscore，已尝试 {self.max_retries} 次: {self.toolscore_endpoint}"
            logger.error(f"❌ {error_msg}")
            raise ConnectionError(error_msg)

    async def disconnect(self):
        """断开与toolscore MCP Server的连接 - 增强版本"""
        async with self._connection_lock:
            await self._stop_health_check()
            await self._close_connection()
            logger.info("✅ 已断开与 toolscore 的连接")
    
    async def _close_connection(self):
        """安全关闭连接"""
        if self.websocket:
            try:
                await asyncio.wait_for(self.websocket.close(), timeout=5.0)
            except Exception as e:
                logger.warning(f"⚠️ 关闭 WebSocket 连接时出错: {e}")
            finally:
                self.websocket = None
                self._connected = False
    
    async def _is_connection_healthy(self) -> bool:
        """检查连接是否健康"""
        if not self.websocket or self.websocket.closed:
            return False
        
        try:
            # 发送ping检查连接
            await asyncio.wait_for(self.websocket.ping(), timeout=5.0)
            return True
        except Exception as e:
            logger.debug(f"连接健康检查失败: {e}")
            return False
    
    async def _start_health_check(self):
        """启动健康检查任务"""
        await self._stop_health_check()  # 确保没有重复任务
        self._health_check_task = asyncio.create_task(self._health_check_loop())
        logger.debug("健康检查任务已启动")
    
    async def _stop_health_check(self):
        """停止健康检查任务"""
        if self._health_check_task and not self._health_check_task.done():
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
            self._health_check_task = None
            logger.debug("健康检查任务已停止")
    
    async def _health_check_loop(self):
        """健康检查循环"""
        while self._connected:
            try:
                await asyncio.sleep(self._health_check_interval)
                
                if not await self._is_connection_healthy():
                    logger.warning("🔴 检测到连接不健康，标记为断开")
                    self._connected = False
                    self._connection_failures += 1
                    break
                else:
                    logger.debug("💚 连接健康检查通过")
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ 健康检查循环出错: {e}")
                break
    
    def get_connection_stats(self) -> Dict[str, Any]:
        """获取连接统计信息"""
        current_time = asyncio.get_event_loop().time()
        uptime = current_time - self._connection_stats.get('last_connection_time', current_time)
        
        return {
            **self._connection_stats,
            'is_connected': self._connected,
            'connection_failures': self._connection_failures,
            'time_since_last_success': current_time - self._last_successful_request if self._last_successful_request > 0 else 0,
            'health_check_active': self._health_check_task is not None and not self._health_check_task.done(),
            'current_uptime': uptime if self._connected else 0,
            'success_rate': (self._connection_stats['successful_connections'] / max(1, self._connection_stats['total_connections'])) * 100,
            'request_success_rate': ((self._connection_stats['total_requests'] - self._connection_stats['failed_requests']) / max(1, self._connection_stats['total_requests'])) * 100,
            'current_endpoint': self.toolscore_endpoint,
            'backup_endpoints_available': len(self._backup_endpoints),
            'endpoint_health_score': self._endpoint_health_scores.get(self.toolscore_endpoint, 0)
        }

    async def _send_request(self, request_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """发送请求到toolscore并等待响应 - 增强版本，支持超时和智能重试"""
        self._connection_stats['total_requests'] += 1
        
        # 🔄 智能重连：检查连接失败次数，决定是否需要重置
        if self._connection_failures >= self._max_failures_before_reset:
            logger.info(f"🔄 连接失败过多 ({self._connection_failures})，执行完全重置")
            await self._close_connection()
            self._connection_failures = 0
        
        # 确保连接可用
        if not self._connected or self.websocket is None:
            await self.connect()

        if self.websocket is None:
            self._connection_stats['failed_requests'] += 1
            raise ConnectionError("无法建立与 toolscore 的连接")

        import uuid
        request_id = str(uuid.uuid4())
        request = {
            "type": request_type,
            "request_id": request_id,
            **payload
        }
        
        # 🔄 重试逻辑：最多重试2次
        for attempt in range(2):
            try:
                # 🕐 使用超时发送和接收
                await asyncio.wait_for(
                    self.websocket.send(json.dumps(request)), 
                    timeout=10.0
                )
                
                response_str = await asyncio.wait_for(
                    self.websocket.recv(), 
                    timeout=self.request_timeout
                )
                
                response = json.loads(response_str)
                
                # 🎯 成功处理响应
                self._last_successful_request = asyncio.get_event_loop().time()
                self._connection_failures = max(0, self._connection_failures - 1)  # 逐步减少失败计数
                
                if not response.get("success", False):
                    error_msg = response.get("error") or response.get("message", "Unknown error")
                    logger.warning(f"⚠️ Toolscore 返回错误: {error_msg}")
                    raise Exception(f"Toolscore error: {error_msg}")
                
                return response
                
            except asyncio.TimeoutError:
                logger.warning(f"⏰ 请求超时 (尝试 {attempt + 1}/2): {request_type}")
                self._connection_stats['failed_requests'] += 1
                self._connection_failures += 1
                
                if attempt == 0:  # 第一次超时，尝试重连
                    logger.info("🔄 超时后尝试重新连接...")
                    await self._close_connection()
                    await self.connect()
                    continue
                else:
                    raise TimeoutError(f"请求超时: {request_type}")
            
            except (websockets.exceptions.ConnectionClosed, 
                    websockets.exceptions.ConnectionClosedOK,
                    websockets.exceptions.ConnectionClosedError) as conn_error:
                logger.warning(f"🔌 连接断开: {conn_error}")
                self._connected = False
                self._connection_failures += 1
                self._connection_stats['failed_requests'] += 1
                self._connection_stats['connection_drops'] += 1
                
                # 降低当前端点健康评分
                current_score = self._endpoint_health_scores.get(self.toolscore_endpoint, 100)
                self._endpoint_health_scores[self.toolscore_endpoint] = max(0, current_score - 15)
                
                if attempt == 0:  # 第一次连接断开，尝试重连
                    logger.info("🔄 连接断开后尝试重新连接...")
                    await self.connect()
                    
                    if self._connected and self.websocket:
                        continue
                    else:
                        raise ConnectionError("重连失败，无法完成请求")
                else:
                    raise ConnectionError("连接持续不稳定，无法完成请求")
            
            except json.JSONDecodeError as e:
                logger.error(f"❌ JSON 解析错误: {e}")
                self._connection_stats['failed_requests'] += 1
                raise Exception(f"服务器响应格式错误: {e}")
            
            except Exception as e:
                logger.error(f"❌ 请求处理异常 (尝试 {attempt + 1}/2): {e}")
                self._connection_stats['failed_requests'] += 1
                self._connection_failures += 1
                
                if attempt == 0 and "ConnectionClosed" in str(type(e)):
                    # 最后一次尝试处理可能的连接问题
                    await self._close_connection()
                    await self.connect()
                    continue
                else:
                    raise
        
            # 如果到这里，说明两次尝试都失败了
        # 尝试使用备份端点
        if self._backup_endpoints and not await self._try_backup_endpoints():
            logger.error("❌ 所有端点都无法连接")
        
        raise Exception(f"请求 {request_type} 在重试后仍然失败")
    
    async def _try_backup_endpoints(self) -> bool:
        """尝试连接备份端点"""
        if not self._backup_endpoints:
            return False
        
        # 按健康评分排序备份端点
        sorted_backups = sorted(
            self._backup_endpoints, 
            key=lambda x: (x['health_score'], -x['last_used'])
        )
        
        for backup in sorted_backups[:2]:  # 只尝试前2个最健康的备份端点
            try:
                logger.info(f"🔄 尝试备份端点: {backup['endpoint']}")
                old_endpoint = self.toolscore_endpoint
                self.toolscore_endpoint = backup['endpoint']
                
                # 尝试连接
                await self.connect()
                
                if self._connected:
                    backup['last_used'] = asyncio.get_event_loop().time()
                    backup['health_score'] = min(100, backup['health_score'] + 10)
                    logger.info(f"✅ 成功切换到备份端点: {backup['endpoint']}")
                    return True
                else:
                    # 恢复原端点
                    self.toolscore_endpoint = old_endpoint
                    backup['health_score'] = max(0, backup['health_score'] - 20)
                    
            except Exception as e:
                logger.warning(f"⚠️ 备份端点连接失败: {backup['endpoint']} - {e}")
                backup['health_score'] = max(0, backup['health_score'] - 30)
        
        return False
    
    async def _batch_processor(self):
        """批处理请求处理器"""
        batch = []
        last_batch_time = asyncio.get_event_loop().time()
        
        while True:
            try:
                # 等待新请求或超时
                try:
                    request_item = await asyncio.wait_for(
                        self._request_queue.get(), 
                        timeout=self._batch_timeout
                    )
                    batch.append(request_item)
                except asyncio.TimeoutError:
                    # 超时，处理当前批次
                    pass
                
                current_time = asyncio.get_event_loop().time()
                should_process = (
                    len(batch) >= self._batch_size or 
                    (batch and current_time - last_batch_time >= self._batch_timeout)
                )
                
                if should_process and batch:
                    await self._process_batch(batch)
                    batch = []
                    last_batch_time = current_time
                    
            except asyncio.CancelledError:
                # 处理剩余批次后退出
                if batch:
                    await self._process_batch(batch)
                break
            except Exception as e:
                logger.error(f"❌ 批处理器异常: {e}")
                await asyncio.sleep(1)
    
    async def _process_batch(self, batch: List[Dict[str, Any]]):
        """处理批量请求"""
        if not batch:
            return
        
        logger.debug(f"📦 处理批量请求: {len(batch)} 个")
        
        # 为简化，目前逐个处理，未来可以实现真正的批量API
        for request_item in batch:
            try:
                request_data = request_item['request']
                result_future = request_item['future']
                
                if not result_future.done():
                    try:
                        result = await self._send_request(
                            request_data['type'], 
                            {k: v for k, v in request_data.items() if k != 'type'}
                        )
                        result_future.set_result(result)
                    except Exception as e:
                        result_future.set_exception(e)
                        
            except Exception as e:
                logger.error(f"❌ 处理批量请求项失败: {e}")
    
    async def send_batched_request(self, request_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """发送批量请求"""
        if not self._enable_batching:
            return await self._send_request(request_type, payload)
        
        # 创建future来接收结果
        result_future = asyncio.Future()
        request_item = {
            'request': {'type': request_type, **payload},
            'future': result_future
        }
        
        try:
            # 添加到队列
            await asyncio.wait_for(self._request_queue.put(request_item), timeout=1.0)
            # 等待结果
            return await result_future
        except asyncio.TimeoutError:
            # 队列满，回退到直接发送
            return await self._send_request(request_type, payload)

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
        # 停止批处理器
        if self._batch_processor_task and not self._batch_processor_task.done():
            self._batch_processor_task.cancel()
            try:
                await self._batch_processor_task
            except asyncio.CancelledError:
                pass
        
        await self.disconnect()
        logger.info("✅ MCPToolClient 资源清理完成")
    
    # 添加兼容性方法别名
    async def list_tools(self) -> List[ToolSpec]:
        """获取所有可用工具 (get_all_tools 的别名)"""
        return await self.get_all_tools()
    
    async def call_tool(self, tool_id: str, action: str = "execute", parameters: Dict[str, Any] = None) -> ExecutionResult:
        """调用工具 (execute_tool 的别名)"""
        if parameters is None:
            parameters = {}
        return await self.execute_tool(tool_id, action, parameters)
    
    async def execute_tool_with_retry(self, tool_id: str, action: str, parameters: Dict[str, Any], max_retries: int = 2) -> ExecutionResult:
        """带重试的工具执行"""
        last_error = None
        
        for attempt in range(max_retries + 1):
            try:
                result = await self.execute_tool(tool_id, action, parameters)
                
                # 如果成功或是业务错误（非连接错误），直接返回
                if result.success or result.error_type != ErrorType.NETWORK_ERROR:
                    return result
                
                # 网络错误，记录并继续重试
                last_error = result.error_message
                if attempt < max_retries:
                    wait_time = 2 ** attempt  # 指数退避
                    logger.info(f"🔄 工具调用失败，{wait_time}s后重试 (尝试 {attempt + 1}/{max_retries + 1}): {tool_id}.{action}")
                    await asyncio.sleep(wait_time)
                
            except Exception as e:
                last_error = str(e)
                if attempt < max_retries:
                    wait_time = 2 ** attempt
                    logger.warning(f"🔄 工具调用异常，{wait_time}s后重试: {e}")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"❌ 工具调用最终失败: {tool_id}.{action} - {e}")
        
        # 所有重试都失败了
        return ExecutionResult(
            success=False,
            data=None,
            error_type=ErrorType.NETWORK_ERROR,
            error_message=f"工具调用在 {max_retries + 1} 次尝试后失败: {last_error}",
            metadata={'retries_exhausted': True, 'max_retries': max_retries}
        )
    
    def get_health_report(self) -> Dict[str, Any]:
        """获取详细的健康报告"""
        stats = self.get_connection_stats()
        current_time = asyncio.get_event_loop().time()
        
        # 计算健康评分
        health_score = 100
        
        # 连接成功率影响 (40%权重)
        connection_success_rate = stats['success_rate']
        health_score = health_score * (connection_success_rate / 100) * 0.4 + health_score * 0.6
        
        # 请求成功率影响 (40%权重)
        request_success_rate = stats['request_success_rate']
        health_score = health_score * (request_success_rate / 100) * 0.4 + health_score * 0.6
        
        # 连接稳定性影响 (20%权重)
        if stats['connection_drops'] > 5:
            stability_penalty = min(50, stats['connection_drops'] * 5)
            health_score = health_score * (1 - stability_penalty / 100 * 0.2)
        
        # 确定健康状态
        if health_score >= 80:
            health_status = "healthy"
        elif health_score >= 60:
            health_status = "degraded"
        elif health_score >= 30:
            health_status = "unhealthy"
        else:
            health_status = "critical"
        
        return {
            'health_status': health_status,
            'health_score': round(health_score, 2),
            'is_connected': self._connected,
            'connection_stats': stats,
            'recommendations': self._get_health_recommendations(health_score, stats),
            'timestamp': current_time
        }
    
    def _get_health_recommendations(self, health_score: float, stats: Dict[str, Any]) -> List[str]:
        """获取健康改善建议"""
        recommendations = []
        
        if stats['success_rate'] < 90:
            recommendations.append("考虑增加备份端点以提高连接成功率")
        
        if stats['request_success_rate'] < 95:
            recommendations.append("检查网络连接稳定性，考虑增加重试次数")
        
        if stats['connection_drops'] > 3:
            recommendations.append("频繁断连，建议检查服务器稳定性")
        
        if stats['time_since_last_success'] > 300:  # 5分钟
            recommendations.append("长时间未成功连接，建议检查服务器状态")
        
        if not recommendations:
            recommendations.append("连接状态良好，继续保持")
        
        return recommendations