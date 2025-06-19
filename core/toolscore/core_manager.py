"""
ToolScore 核心管理器 - 合并版本
整合所有分散的管理功能到单一文件中
"""

import asyncio
import json
import logging
import time
import redis.asyncio as redis
from typing import Dict, Any, List, Optional, Set
from pathlib import Path
import websockets

from .interfaces import ToolSpec, MCPServerSpec, ToolCapability, ToolType, RegistrationResult

# Runner 抽象：只使用 ProcessRunner
from core.toolscore.runners import ProcessRunner, BaseRunner
from core.toolscore.websocket_manager import WebSocketManager
from core.toolscore.cache_manager import CacheManager

logger = logging.getLogger(__name__)

class CoreManager:
    """
    ToolScore核心管理器 - 整合版本
    
    整合功能：
    - MCP容器和镜像管理 (原persistent_container_manager + mcp_image_manager)
    - 实时注册和缓存 (原real_time_registry + mcp_cache_manager)    - 自动注册预置服务器 (原auto_register)    - 工具注册表管理 (原tool_registry)
    - 简化的持久化存储 (原persistent_storage)
    """
    
    def __init__(self, redis_url: str = "redis://localhost:6379", redis_manager=None, config_manager=None):
        self.redis_url = redis_url
        self.redis_client: Optional[redis.Redis] = None
        self.redis_manager = redis_manager  # 新增：Redis管理器实例
        self.config_manager = config_manager  # 新增：配置管理器

        # === Runner 选择 ===
        # 强制注入 ProcessRunner 实例
        self.runner: BaseRunner = ProcessRunner()
        logger.info("CoreManager 强制使用 ProcessRunner")
        
        # 内存缓存
        self._tool_cache: Dict[str, Dict[str, Any]] = {}
        self._cache_lock = asyncio.Lock()
        
        # WebSocket连接管理
        self.websocket_connections: Set = set()
        
        # 预置MCP服务器配置
        self.predefined_servers = [
            {
                "tool_id": "microsandbox-server",
                "name": "MicroSandbox Secure Executor",
                "description": "Execute Python code in secure isolated sandbox with hardware-level isolation and comprehensive monitoring",
                "endpoint": "ws://localhost:8081/mcp",
                "capabilities": [
                    {
                        "name": "microsandbox_execute",
                        "description": "Execute Python code in secure sandbox environment",
                        "parameters": {
                            "code": {"type": "string", "description": "Python code to execute", "required": True},
                            "session_id": {"type": "string", "description": "Session ID for multi-turn execution", "required": False},
                            "timeout": {"type": "integer", "description": "Execution timeout in seconds", "required": False}
                        }
                    },
                    {
                        "name": "microsandbox_install_package",
                        "description": "Install Python packages in sandbox environment",
                        "parameters": {
                            "package_name": {"type": "string", "description": "Package name to install", "required": True}
                        }
                    },
                    {
                        "name": "microsandbox_get_performance_stats",
                        "description": "Get performance statistics and monitoring data",
                        "parameters": {}
                    }
                ],
                "tags": ["python", "code", "execution", "sandbox", "security", "monitoring"]
            },
            {
                "tool_id": "browser-use-server", 
                "name": "Browser-Use AI Automation",
                "description": "AI-powered browser automation with natural language task execution and comprehensive web interaction capabilities",
                "endpoint": "ws://localhost:8082/mcp",
                "capabilities": [
                    {
                        "name": "browser_use_execute_task",
                        "description": "Execute complex browser tasks using AI and natural language",
                        "parameters": {
                            "task": {"type": "string", "description": "Natural language task description", "required": True},
                            "max_steps": {"type": "integer", "description": "Maximum execution steps", "required": False},
                            "use_vision": {"type": "boolean", "description": "Enable visual understanding", "required": False}
                        }
                    },
                    {
                        "name": "browser_navigate",
                        "description": "Navigate to a specific URL",
                        "parameters": {
                            "url": {"type": "string", "description": "URL to navigate to", "required": True}
                        }
                    },
                    {
                        "name": "browser_screenshot",
                        "description": "Take a screenshot of the current page",
                        "parameters": {
                            "filename": {"type": "string", "description": "Screenshot filename", "required": False}
                        }
                    },
                    {
                        "name": "browser_extract_content",
                        "description": "Extract specific content from the page using AI",
                        "parameters": {
                            "goal": {"type": "string", "description": "Content extraction goal", "required": True}
                        }
                    }
                ],
                "tags": ["browser", "web", "navigation", "automation", "ai", "vision", "nlp"]
            }
        ]
        
        # 初始化各个管理器
        # 延迟导入避免循环依赖
        self.dynamic_mcp_manager = None
        self.websocket_manager = WebSocketManager()
        self.monitoring_api = None
        self.cache_manager = CacheManager()
        
        # 服务状态
        self.is_running = False
        self.persistent_servers: Dict[str, Dict[str, Any]] = {}
        
        logger.info("✅ 核心管理器初始化完成")
    
    async def initialize(self):
        """初始化核心管理器"""
        try:
            # 连接Redis - 支持fallback模式
            if self.redis_manager and self.redis_manager.is_fallback_mode():
                logger.info("使用内存存储模式，跳过Redis连接")
                self.redis_client = None
            else:
                self.redis_client = redis.from_url(self.redis_url)
                if self.redis_client:
                    try:
                        await self.redis_client.ping()
                        logger.info("Redis连接成功")
                    except Exception as e:
                        logger.warning(f"Redis连接失败，使用内存模式: {e}")
                        self.redis_client = None
            
            # 延迟导入避免循环依赖
            from core.toolscore.dynamic_mcp_manager import DynamicMCPManager
            from core.toolscore.monitoring_api import ToolScoreMonitoringAPI
            
            self.dynamic_mcp_manager = DynamicMCPManager(runner=self.runner, config_manager=self.config_manager)
            # 暂时不传入工具库，稍后通过设置方法注入
            self.monitoring_api = ToolScoreMonitoringAPI()
            
            # 恢复容器
            await self._recover_all_containers()
            
            # 暂时禁用自动注册，在所有服务启动后再手动注册
            # await self._auto_register_predefined_servers()
            
            logger.info("✅ 核心管理器初始化完成") # 修正日志信息，这里是初始化完成，不是启动成功
            
        except Exception as e:
            logger.error(f"❌ 核心管理器初始化失败: {e}")
            raise

    async def set_tool_library_for_monitoring(self, tool_library):
        """在监控API中设置工具库"""
        if self.monitoring_api:
            self.monitoring_api.tool_library = tool_library
            logger.info("工具库已成功注入到监控API。")
        else:
            logger.warning("monitoring_api 未初始化，无法注入 tool_library。")
    
    # === 容器管理功能 (合并 persistent_container_manager + mcp_image_manager) ===
    
    async def _recover_all_containers(self):
        """恢复所有MCP容器"""
        try:
            # 仅 ProcessRunner 才恢复容器
            if not isinstance(self.runner, ProcessRunner):
                logger.info("当前 Runner 非 ProcessRunner，跳过容器恢复")
                return 0

            # ProcessRunner 不管理 Docker 容器，所以这里不调用 list_running_containers
            # 而是假设没有需要恢复的容器
            logger.info("ProcessRunner 模式下不恢复 Docker 容器。")
            return 0 # 修正：这里应该返回实际恢复的数量，但ProcessRunner不恢复容器，所以返回0
            
            recovered_count = 0
            for container in containers:
                try:
                    if container.status != 'running':
                        container.start()
                        logger.info(f"恢复容器: {container.name}")
                        recovered_count += 1
                        
                except Exception as e:
                    logger.error(f"恢复容器失败 {container.name}: {e}")
            
            logger.info(f"恢复了 {recovered_count} 个MCP容器")
            return recovered_count
            
        except Exception as e:
            logger.error(f"容器恢复失败: {e}")
            return 0
    
    async def create_persistent_container(self, image_id: str, server_spec: MCPServerSpec, port: int) -> str:
        """创建持久化容器"""
        container_name = f"mcp-{server_spec.tool_id}"
        
        container_config = {
            "image": image_id,
            "name": container_name,
            "ports": {f"{port}/tcp": port},
            "environment": {
                "MCP_SERVER_PORT": str(port),
            },
            "restart_policy": {"Name": "unless-stopped"},
            "network_mode": "agent-data-platform_agent_network",
            "labels": {
                "mcp.server.id": server_spec.tool_id,
                "mcp.server.name": server_spec.name,
                "mcp.manager": "toolscore",
                "mcp.auto-recover": "true"
            }
        }
        
        # 当使用 ProcessRunner 时直接返回 None
        # ProcessRunner 不创建 Docker 容器，直接返回成功
        logger.debug("ProcessRunner 模式下不创建 Docker 容器，模拟成功。")
        return "process-runner-no-container"

        try:
            container = self.runner.run_container(detach=True, **container_config)
            logger.info(f"创建持久化容器: {container.name}")
            return container.id
            
        except Exception as e:
            logger.error(f"创建容器失败: {e}")
            raise
    
    # === 实时注册和缓存功能 (合并 real_time_registry + mcp_cache_manager) ===
    
    async def register_tool_immediately(self, server_spec: MCPServerSpec):
        """立即注册工具并通知所有客户端"""
        try:
            # 更新本地缓存
            async with self._cache_lock:
                self._tool_cache[server_spec.tool_id] = {
                    "tool_id": server_spec.tool_id,
                    "name": server_spec.name,
                    "description": server_spec.description,
                    "capabilities": [cap.name for cap in server_spec.capabilities],
                    "endpoint": server_spec.endpoint
                }
            
            # 发布Redis事件
            await self._publish_tool_event("tool_available", server_spec)
            
            # WebSocket通知
            await self._notify_websocket_clients({
                "type": "tool_installed",
                "tool_id": server_spec.tool_id,
                "name": server_spec.name,
                "status": "ready"
            })
            
            logger.info(f"工具立即可用: {server_spec.tool_id}")
            return True
            
        except Exception as e:
            logger.error(f"立即注册失败: {e}")
            return False
    
    async def _publish_tool_event(self, event_type: str, server_spec: MCPServerSpec):
        """发布工具事件到Redis"""
        if not self.redis_client:
            return
            
        event_data = {
            "event_type": event_type,
            "tool_id": server_spec.tool_id,
            "tool_spec": {
                "tool_id": server_spec.tool_id,
                "name": server_spec.name,
                "description": server_spec.description,
                "capabilities": [cap.name for cap in server_spec.capabilities],
                "endpoint": server_spec.endpoint
            },
            "timestamp": time.time()
        }
        
        await self.redis_client.publish('tool_events', json.dumps(event_data))
        await self.redis_client.publish('immediate_tool_updates', json.dumps(event_data))
    
    async def _notify_websocket_clients(self, notification: dict):
        """WebSocket通知所有客户端"""
        if not self.websocket_connections:
            return
            
        disconnected_clients = set()
        for websocket in self.websocket_connections:
            try:
                payload = json.dumps(notification)
                if hasattr(websocket, "send_str"):
                    # aiohttp.web.WebSocketResponse
                    await websocket.send_str(payload)
                else:
                    # websockets.client.ServerConnection / WebSocketCommonProtocol
                    await websocket.send(payload)
            except Exception as e:
                logger.warning(f"WebSocket通知失败: {e}")
                disconnected_clients.add(websocket)
        
        # 清理断开的连接
        self.websocket_connections -= disconnected_clients
    
    async def add_websocket_connection(self, websocket):
        """添加WebSocket连接"""
        self.websocket_connections.add(websocket)
        logger.debug(f"WebSocket连接已添加，当前连接数: {len(self.websocket_connections)}")
    
    async def remove_websocket_connection(self, websocket):
        """移除WebSocket连接"""
        self.websocket_connections.discard(websocket)
        logger.debug(f"WebSocket连接已移除，当前连接数: {len(self.websocket_connections)}")
    
    # === 缓存管理功能 ===
    
    async def cache_search_result(self, cache_key: str, data: Any, ttl: int = 3600):
        """缓存搜索结果"""
        if self.redis_client:
            await self.redis_client.setex(cache_key, ttl, json.dumps(data))
    
    async def get_cached_result(self, cache_key: str) -> Optional[Any]:
        """获取缓存结果"""
        if not self.redis_client:
            return None
            
        try:
            cached_data = await self.redis_client.get(cache_key)
            return json.loads(cached_data) if cached_data else None
        except:
            return None
    
    # === 自动注册功能 (合并 auto_register) ===
    
    async def _auto_register_predefined_servers(self) -> Dict[str, Any]:
        """自动注册所有预置的MCP服务器"""
        logger.info("🔄 开始自动注册预置MCP服务器...")
        
        registration_results = {
            "success_count": 0,
            "failed_count": 0,
            "results": []
        }
        
        for server_config in self.predefined_servers:
            try:
                # 检查服务器是否可达
                is_available = await self._check_server_availability(server_config["endpoint"])
                
                if is_available:
                    # 创建服务器规范
                    server_spec = await self._create_server_spec_from_config(server_config)
                    
                    # 注册服务器
                    success = await self.register_tool_immediately(server_spec)
                    
                    if success:
                        registration_results["success_count"] += 1
                        logger.info(f"✅ 成功注册: {server_config['name']}")
                    else:
                        registration_results["failed_count"] += 1
                        
                else:
                    registration_results["failed_count"] += 1
                    logger.warning(f"⚠️ 服务器不可达: {server_config['name']}")
                    
            except Exception as e:
                registration_results["failed_count"] += 1
                logger.error(f"❌ 注册异常: {server_config['name']} - {e}")
        
        logger.info(f"🎯 自动注册完成: {registration_results['success_count']} 成功, {registration_results['failed_count']} 失败")
        return registration_results
    
    async def _check_server_availability(self, endpoint: str, timeout: float = 5.0) -> bool:
        """检查MCP服务器是否可达"""
        try:
            async with websockets.connect(endpoint, timeout=timeout) as websocket:
                ping_message = {"jsonrpc": "2.0", "id": 1, "method": "ping"}
                await websocket.send(json.dumps(ping_message))
                
                try:
                    await asyncio.wait_for(websocket.recv(), timeout=2.0)
                    return True
                except asyncio.TimeoutError:
                    return True  # 连接成功但无响应也算可达
                    
        except Exception as e:
            logger.debug(f"服务器 {endpoint} 不可达: {e}")
            return False
    
    async def _create_server_spec_from_config(self, server_config: Dict[str, Any]) -> MCPServerSpec:
        """从配置创建服务器规范"""
        capabilities = []
        for cap_config in server_config["capabilities"]:
            capability = ToolCapability(
                name=cap_config["name"],
                description=cap_config["description"],
                parameters=cap_config["parameters"]
            )
            capabilities.append(capability)
        
        return MCPServerSpec(
            tool_id=server_config["tool_id"],
            name=server_config["name"],
            description=server_config["description"],
            tool_type=ToolType.MCP_SERVER,
            capabilities=capabilities,
            tags=server_config["tags"],
            enabled=True,
            endpoint=server_config["endpoint"]
        )
    
    # === 持久化存储功能 (简化版) ===
    
    async def save_mcp_server(self, server_spec: MCPServerSpec, install_result: dict):
        """保存MCP服务器到持久化存储"""
        if not self.redis_client:
            return
            
        server_data = {
            "server_data": {
                "tool_id": server_spec.tool_id,
                "name": server_spec.name,
                "description": server_spec.description,
                "endpoint": server_spec.endpoint,
                "capabilities": [cap.name for cap in server_spec.capabilities],
                "tags": server_spec.tags
            },
            "install_result": install_result,
            "saved_at": time.time()
        }
        
        await self.redis_client.hset("mcp_servers", server_spec.tool_id, json.dumps(server_data))
        logger.info(f"保存MCP服务器: {server_spec.tool_id}")
    
    async def load_all_mcp_servers(self) -> List[Dict[str, Any]]:
        """加载所有持久化的MCP服务器"""
        if not self.redis_client:
            return []
            
        try:
            servers_data = await self.redis_client.hgetall("mcp_servers")
            return [json.loads(data) for data in servers_data.values()]
        except Exception as e:
            logger.error(f"加载MCP服务器失败: {e}")
            return []
    
    # === 清理功能 ===
    
    async def cleanup(self):
        """清理资源"""
        # 关闭所有WebSocket连接
        for websocket in list(self.websocket_connections):
            try:
                await websocket.close()
            except:
                pass
        self.websocket_connections.clear()
        
        # 关闭Redis连接
        if self.redis_client:
            await self.redis_client.close()
            
        logger.info("核心管理器资源已清理")
    
    async def check_cached_image(self, image_name: str) -> bool:
        """检查镜像是否已经缓存
        
        Args:
            image_name: 镜像名称
            
        Returns:
            bool: 如果镜像已缓存返回True，否则返回False
        """
        try:
            # ProcessRunner 不处理镜像，直接返回 False
            logger.info("ProcessRunner 模式下不检查镜像缓存。")
            return False
        except Exception as e:
            logger.error(f"检查镜像缓存失败: {e}")
            return False

    async def start(self):
        """启动 ToolScore 核心服务"""
        if self.is_running:
            logger.warning("CoreManager 已在运行中")
            return

        try:
            logger.info("正在启动 ToolScore 核心服务...")
            
            # 启动各个组件
            if self.cache_manager:
                await self.cache_manager.start()
            if self.websocket_manager:
                await self.websocket_manager.start()
            if self.monitoring_api and hasattr(self.monitoring_api, 'start'):
                await self.monitoring_api.start()
            if self.dynamic_mcp_manager and hasattr(self.dynamic_mcp_manager, 'start'):
                await self.dynamic_mcp_manager.start()
            
            # 恢复持久化服务器
            await self._restore_persistent_servers()
            
            self.is_running = True
            logger.info("ToolScore 核心服务启动完成")
            
        except Exception as e:
            logger.error(f"启动 ToolScore 核心服务失败: {e}")
            await self.stop()
            raise

    async def stop(self):
        """停止 ToolScore 核心服务"""
        if not self.is_running:
            return

        try:
            logger.info("正在停止 ToolScore 核心服务...")
            
            # 保存持久化服务器状态
            await self._save_persistent_servers()
            
            # 停止各个组件
            if self.dynamic_mcp_manager:
                await self.dynamic_mcp_manager.stop()
            if self.monitoring_api and hasattr(self.monitoring_api, 'stop'):
                await self.monitoring_api.stop()
            if self.websocket_manager:
                await self.websocket_manager.stop()
            if self.cache_manager:
                await self.cache_manager.stop()
            
            # 清理所有运行的服务器
            # ProcessRunner 有 cleanup_all 方法
            if isinstance(self.runner, ProcessRunner):
                await self.runner.cleanup_all()
            
            self.is_running = False
            logger.info("ToolScore 核心服务已停止")
            
        except Exception as e:
            logger.error(f"停止 ToolScore 核心服务时出错: {e}")

    async def _restore_persistent_servers(self):
        """恢复持久化的 MCP 服务器"""
        logger.info("正在恢复持久化的 MCP 服务器...")
        
        try:
            # 从配置文件加载持久化服务器
            config_path = Path("config/persistent_servers.json")
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    persistent_config = json.load(f)
                
                for server_name, server_config in persistent_config.items():
                    try:
                        logger.info(f"正在恢复服务器: {server_name}")
                        result = await self.runner.install_server(server_config)
                        
                        if result.get("success"):
                            self.persistent_servers[server_name] = {
                                "server_id": result["server_id"],
                                "endpoint": result["endpoint"],
                                "config": server_config,
                                "status": "running"
                            }
                            logger.info(f"服务器 {server_name} 恢复成功")
                        else:
                            logger.error(f"恢复服务器 {server_name} 失败: {result.get('error_msg')}")
                            
                    except Exception as e:
                        logger.error(f"恢复服务器 {server_name} 时出错: {e}")
            
            logger.info(f"持久化服务器恢复完成，成功恢复 {len(self.persistent_servers)} 个服务器")
            
        except Exception as e:
            logger.error(f"恢复持久化服务器时出错: {e}")

    async def _save_persistent_servers(self):
        """保存持久化服务器状态"""
        try:
            config_path = Path("config/persistent_servers.json")
            config_path.parent.mkdir(exist_ok=True)
            
            # 保存配置信息（不包含运行时状态）
            persistent_config = {}
            for server_name, server_info in self.persistent_servers.items():
                if server_info.get("config"):
                    persistent_config[server_name] = server_info["config"]
            
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(persistent_config, f, indent=2, ensure_ascii=False)
            
            logger.info(f"持久化服务器配置已保存到 {config_path}")
            
        except Exception as e:
            logger.error(f"保存持久化服务器配置时出错: {e}")

    async def create_persistent_service(self, service_name: str, image_name: str, 
                                      port: int, env_vars: Optional[Dict[str, str]] = None,
                                      **kwargs) -> Dict[str, Any]:
        """创建持久化服务 (ProcessRunner 模式)"""
        logger.info(f"创建持久化服务: {service_name}")
        
        try:
            # 构建服务器配置
            server_config = {
                "name": service_name,
                "repo_url": kwargs.get("repo_url"),
                "project_type": kwargs.get("project_type", "python"),
                "entry_point": kwargs.get("entry_point"),
                "port": port,
                "env_vars": env_vars or {}
            }
            
            # 启动服务器
            result = await self.runner.install_server(server_config)
            
            if result.get("success"):
                self.persistent_servers[service_name] = {
                    "server_id": result["server_id"],
                    "endpoint": result["endpoint"],
                    "config": server_config,
                    "status": "running"
                }
                
                # 保存配置
                await self._save_persistent_servers()
                
                logger.info(f"持久化服务 {service_name} 创建成功")
                return {
                    "success": True,
                    "service_name": service_name,
                    "endpoint": result["endpoint"],
                    "server_id": result["server_id"]
                }
            else:
                logger.error(f"创建持久化服务 {service_name} 失败: {result.get('error_msg')}")
                return {
                    "success": False,
                    "error_msg": result.get("error_msg")
                }
                
        except Exception as e:
            logger.error(f"创建持久化服务 {service_name} 时出错: {e}")
            return {
                "success": False,
                "error_msg": str(e)
            }

    async def get_service_status(self, service_name: str) -> Dict[str, Any]:
        """获取服务状态"""
        if service_name in self.persistent_servers:
            server_info = self.persistent_servers[service_name]
            server_id = server_info.get("server_id")
            endpoint = server_info.get("endpoint")
            
            # 检查服务健康状态
            is_healthy = await self.runner.health_check(endpoint) if endpoint else False
            
            return {
                "service_name": service_name,
                "server_id": server_id,
                "endpoint": endpoint,
                "status": "running" if is_healthy else "unhealthy",
                "is_healthy": is_healthy
            }
        else:
            return {
                "service_name": service_name,
                "status": "not_found",
                "is_healthy": False
            }

    async def list_services(self) -> List[Dict[str, Any]]:
        """列出所有服务"""
        services = []
        
        # 持久化服务
        for service_name in self.persistent_servers:
            status = await self.get_service_status(service_name)
            services.append(status)
        
        # 动态 MCP 服务器
        # ProcessRunner 有 list_running_servers 方法
        if isinstance(self.runner, ProcessRunner):
            running_servers = self.runner.list_running_servers()
            for server_id, server_info in running_servers.items():
                # 避免重复添加已在 persistent_servers 中的服务
                if server_id not in [s.get("server_id") for s in services]:
                    services.append({
                        "service_name": server_info.get("name", server_id),
                        "server_id": server_id,
                        "endpoint": server_info.get("endpoint"),
                        "status": "running",
                        "is_dynamic": True
                    })
        
        return services

    async def remove_service(self, service_name: str) -> bool:
        """移除服务"""
        if service_name not in self.persistent_servers:
            logger.warning(f"服务 {service_name} 不存在")
            return False
        
        try:
            server_info = self.persistent_servers[service_name]
            server_id = server_info.get("server_id")
            
            # 停止服务器
            if server_id:
                success = await self.runner.stop_server(server_id)
                if not success:
                    logger.warning(f"停止服务器 {server_id} 失败，但仍将从配置中移除")
            
            # 从持久化配置中移除
            del self.persistent_servers[service_name]
            await self._save_persistent_servers()
            
            logger.info(f"服务 {service_name} 已移除")
            return True
            
        except Exception as e:
            logger.error(f"移除服务 {service_name} 时出错: {e}")
            return False

    def get_stats(self) -> Dict[str, Any]:
        """获取系统统计信息"""
        running_servers = {}
        if isinstance(self.runner, ProcessRunner):
            running_servers = self.runner.list_running_servers()
        
        return {
            "is_running": self.is_running,
            "persistent_servers": len(self.persistent_servers),
            "dynamic_servers": len(running_servers),
            "total_servers": len(self.persistent_servers) + len(running_servers),
            "runner_type": "ProcessRunner",
            "cache_stats": self.cache_manager.get_stats() if self.cache_manager else {},
            "websocket_connections": len(self.websocket_manager.connections) if self.websocket_manager else 0
        }

    async def health_check(self) -> Dict[str, Any]:
        """系统健康检查"""
        health_status = {
            "overall": "healthy",
            "components": {},
            "timestamp": asyncio.get_event_loop().time()
        }
        
        try:
            # 检查各个组件
            components = [
                ("cache_manager", self.cache_manager),
                ("websocket_manager", self.websocket_manager),
                ("monitoring_api", self.monitoring_api),
                ("dynamic_mcp_manager", self.dynamic_mcp_manager)
            ]
            
            for name, component in components:
                try:
                    if hasattr(component, 'health_check'):
                        component_health = await component.health_check()
                    else:
                        component_health = {"status": "running" if getattr(component, 'is_running', True) else "stopped"}
                    
                    health_status["components"][name] = component_health
                    
                    if component_health.get("status") != "running":
                        health_status["overall"] = "degraded"
                        
                except Exception as e:
                    health_status["components"][name] = {"status": "error", "error": str(e)}
                    health_status["overall"] = "unhealthy"
            
            # 检查持久化服务
            unhealthy_services = 0
            for service_name in self.persistent_servers:
                status = await self.get_service_status(service_name)
                if not status.get("is_healthy"):
                    unhealthy_services += 1
            
            if unhealthy_services > 0:
                health_status["unhealthy_services"] = unhealthy_services
                if unhealthy_services == len(self.persistent_servers):
                    health_status["overall"] = "unhealthy"
                else:
                    health_status["overall"] = "degraded"
            
        except Exception as e:
            logger.error(f"健康检查时出错: {e}")
            health_status["overall"] = "error"
            health_status["error"] = str(e)
        
        return health_status 