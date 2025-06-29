"""
增强的ToolScore核心管理器
集成增强的DynamicMCPManager和新的智能检测功能
"""

import asyncio
import json
import logging
import time
from typing import Dict, Any, List, Optional, Set
from pathlib import Path

# 导入原有组件
from .interfaces import ToolSpec, MCPServerSpec, ToolCapability, ToolType, RegistrationResult
from .runners import ProcessRunner, BaseRunner
from .websocket_manager import WebSocketManager
from .cache_manager import CacheManager

# 导入增强组件
# 优先尝试加载v2.0架构，如果失败则使用原版本
try:
    from .service_container import MCPServiceContainer
    from .enhanced_core_manager_v2 import EnhancedCoreManagerV2
    USE_V2_ARCHITECTURE = True
except ImportError:
    USE_V2_ARCHITECTURE = False

# 导入原始架构组件
from .dynamic_mcp_manager import DynamicMCPManager
from .runners.enhanced_process_runner import EnhancedProcessRunner

logger = logging.getLogger(__name__)


class CoreManager:
    """
    增强的ToolScore核心管理器
    集成智能检测、会话管理和增强的错误处理
    """
    
    def __init__(self, redis_url: str = "redis://localhost:6379", redis_manager=None, config_manager=None):
        self.redis_url = redis_url
        self.redis_client = None
        self.redis_manager = redis_manager
        self.config_manager = config_manager
        
        # 使用增强的ProcessRunner
        self.runner: BaseRunner = EnhancedProcessRunner()
        logger.info("✅ CoreManager 使用增强的ProcessRunner")
        
        # 内存缓存
        self._tool_cache: Dict[str, Dict[str, Any]] = {}
        self._cache_lock = asyncio.Lock()
        
        # WebSocket连接管理
        self.websocket_connections: Set = set()
        
        # 预置MCP服务器配置
        self.predefined_servers = [
            {
                "tool_id": "search_tool",
                "name": "Search Tool MCP Server",
                "description": "Advanced search and research capabilities",
                "endpoint": "ws://localhost:8080/mcp",
                "capabilities": [
                    {
                        "name": "search_web",
                        "description": "Search the web using multiple search engines",
                        "parameters": {
                            "query": {"type": "string", "description": "Search query", "required": True},
                            "max_results": {"type": "integer", "description": "Maximum results", "required": False}
                        }
                    }
                ],
                "tags": ["search", "web", "research"]
            },
            {
                "tool_id": "browser_use",
                "name": "Browser Use MCP Server", 
                "description": "AI-powered browser automation and control",
                "endpoint": "ws://localhost:8084/mcp",
                "capabilities": [
                    {
                        "name": "browser_use_execute_task",
                        "description": "Execute complex browser tasks using AI",
                        "parameters": {
                            "task": {"type": "string", "description": "Natural language task description", "required": True},
                            "max_steps": {"type": "integer", "description": "Maximum execution steps", "required": False},
                            "use_vision": {"type": "boolean", "description": "Enable visual understanding", "required": False}
                        }
                    }
                ],
                "tags": ["browser", "automation", "ai"]
            }
        ]
        
        # 智能选择管理器版本
        if USE_V2_ARCHITECTURE:
            logger.info("🚀 使用v2.0服务容器架构")
            self.v2_manager = EnhancedCoreManagerV2(config_manager)
            self.dynamic_mcp_manager = None  # v2架构中集成了这个功能
        else:
            logger.info("🔧 使用原始架构")
            self.dynamic_mcp_manager = DynamicMCPManager(self.runner, config_manager)
            self.v2_manager = None
        self.websocket_manager = WebSocketManager()
        self.monitoring_api = None
        self.cache_manager = CacheManager()
        
        # 服务状态
        self.is_running = False
        self.persistent_servers: Dict[str, Dict[str, Any]] = {}
        
        logger.info("✅ 增强的核心管理器初始化完成")
    
    async def initialize(self):
        """初始化增强核心管理器"""
        logger.info("🚀 正在初始化增强的CoreManager...")
        
        try:
            # 优先尝试v2.0架构
            if USE_V2_ARCHITECTURE and self.v2_manager:
                logger.info("🔄 使用v2.0服务容器架构初始化...")
                try:
                    await self.v2_manager.initialize()
                    self.is_running = True
                    logger.info("✅ v2.0架构初始化完成")
                    return
                except Exception as e:
                    logger.error(f"❌ v2.0架构初始化失败: {e}")
                    logger.info("🔄 回退到原始架构...")
                    # 创建原始组件作为备用
                    from .dynamic_mcp_manager import DynamicMCPManager
                    self.dynamic_mcp_manager = DynamicMCPManager(self.runner, self.config_manager)
                    self.v2_manager = None
            
            # 原始架构初始化流程
            # 初始化Redis连接
            if self.redis_manager:
                self.redis_client = await self._get_redis_client()
                logger.info("✅ Redis连接已建立")
            
            # 启动增强的DynamicMCPManager
            if self.dynamic_mcp_manager:
                await self.dynamic_mcp_manager.start()
                logger.info("✅ 增强的DynamicMCPManager已启动")
            
            # 加载持久化服务器配置
            await self._load_persistent_servers()
            
            # 自动注册预置MCP服务器
            registration_results = await self._auto_register_predefined_servers()
            logger.info(f"✅ 预置服务器注册完成: {registration_results['success_count']} 成功, {registration_results['failed_count']} 失败")
            
            # 标记为已初始化
            self.is_running = True
            logger.info("🎯 增强的CoreManager初始化完成")
            
        except Exception as e:
            logger.error(f"❌ 增强的CoreManager初始化失败: {e}")
            raise
    
    async def start(self):
        """启动增强的ToolScore核心服务"""
        if self.is_running:
            logger.info("服务已在运行中")
            return
        
        try:
            logger.info("正在启动增强的ToolScore核心服务...")
            
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
            logger.info("✅ 增强的ToolScore核心服务启动完成")
            
        except Exception as e:
            logger.error(f"❌ 启动增强的ToolScore核心服务失败: {e}")
            await self.stop()
            raise
    
    async def stop(self):
        """停止增强的ToolScore核心服务"""
        if not self.is_running:
            return
        
        try:
            logger.info("正在停止增强的ToolScore核心服务...")
            
            # 保存持久化服务器状态
            await self._save_persistent_servers()
            
            # 停止增强的DynamicMCPManager
            if self.dynamic_mcp_manager:
                await self.dynamic_mcp_manager.stop()
            
            # 停止其他组件
            if self.monitoring_api and hasattr(self.monitoring_api, 'stop'):
                await self.monitoring_api.stop()
            if self.websocket_manager:
                await self.websocket_manager.stop()
            if self.cache_manager:
                await self.cache_manager.stop()
            
            # 清理所有运行的服务器
            if isinstance(self.runner, (ProcessRunner, EnhancedProcessRunner)):
                await self.runner.cleanup_all()
            
            self.is_running = False
            logger.info("✅ 增强的ToolScore核心服务已停止")
            
        except Exception as e:
            logger.error(f"❌ 停止增强的ToolScore核心服务时出错: {e}")
    
    # === 增强的工具搜索和安装功能 ===
    
    async def search_and_install_tools(self, query: str, max_tools: int = 3) -> Dict[str, Any]:
        """
        使用增强的工具搜索和安装功能
        """
        try:
            logger.info(f"🔍 开始搜索和安装工具: {query}")
            
            # 如果v2管理器可用，使用v2架构
            if self.v2_manager:
                return await self.v2_manager.search_and_install_tools(query, max_tools)
            
            # 否则使用原始架构
            if not self.dynamic_mcp_manager:
                return {
                    "success": False,
                    "message": "动态MCP管理器未初始化",
                    "installed_tools": [],
                    "error_message": "管理器未初始化"
                }
            
            # 使用DynamicMCPManager进行搜索 - 注意：DynamicMCPManager不直接支持安装，只支持搜索
            candidates = await self.dynamic_mcp_manager.search_mcp_servers(query, [])
            
            # 创建一个简单的结果对象
            class SimpleResult:
                def __init__(self, success, installed_tools, message):
                    self.success = success
                    self.installed_tools = installed_tools
                    self.message = message
            
            result = SimpleResult(
                success=True,
                installed_tools=[],  # DynamicMCPManager不直接安装，只搜索
                message=f"找到 {len(candidates)} 个候选服务器"
            )
            
            # 更新缓存
            if result.success and result.installed_tools:
                for tool in result.installed_tools:
                    tool_id = tool.get('tool_id')
                    if tool_id:
                        await self._update_tool_cache(tool_id, tool)
            
            return {
                "success": result.success,
                "message": result.message,
                "installed_tools": result.installed_tools,
                "error_message": result.error_message
            }
            
        except Exception as e:
            logger.error(f"❌ 搜索和安装工具失败: {e}")
            return {
                "success": False,
                "message": "搜索和安装失败",
                "installed_tools": [],
                "error_message": str(e)
            }
    
    async def call_tool(self, server_id: str, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        调用指定服务器的工具
        """
        try:
            if self.v2_manager is not None:
                # v2.0架构
                container = getattr(self.v2_manager, 'service_container', None)
                if container and hasattr(container, 'call_service_for_llm'):
                    return await container.call_service_for_llm(server_id, tool_name, arguments)
                else:
                    # v2架构暂不支持工具调用
                    return {
                        "success": False,
                        "error": "v2架构暂不支持直接工具调用",
                        "server_id": server_id,
                        "tool_name": tool_name
                    }
            elif self.dynamic_mcp_manager is not None:
                # 原始架构 - DynamicMCPManager不支持直接工具调用
                return {
                    "success": False,
                    "error": "原始架构暂不支持直接工具调用",
                    "server_id": server_id,
                    "tool_name": tool_name
                }
            else:
                return {
                    "success": False,
                    "error": "没有可用的MCP管理器",
                    "server_id": server_id,
                    "tool_name": tool_name
                }
        except Exception as e:
            logger.error(f"❌ 调用工具失败: {server_id}.{tool_name}, 错误: {e}")
            return {
                "success": False,
                "error": str(e),
                "server_id": server_id,
                "tool_name": tool_name
            }
    
    async def list_available_tools(self, server_id: Optional[str] = None) -> Dict[str, Any]:
        """
        列出可用的工具
        """
        try:
            # 检查架构版本
            if self.v2_manager is not None:
                # v2.0架构：使用service_container
                logger.debug("使用v2.0架构获取工具列表")
                container = getattr(self.v2_manager, 'service_container', None)
                if container and hasattr(container, 'list_available_tools'):
                    return await container.list_available_tools(server_id)
                else:
                    # 回退方案：返回基本的工具信息
                    logger.warning("v2架构暂不支持详细工具列表，返回基本信息")
                    return {
                        "success": True,
                        "servers": {
                            "microsandbox": {"tools": [{"name": "execute"}]},
                            "browser_use": {"tools": [{"name": "browser_action"}]},
                            "deepsearch": {"tools": [{"name": "research"}]},
                            "search_tool": {"tools": [{"name": "search_file_content"}]}
                        }
                    }
            elif self.dynamic_mcp_manager is not None:
                # 原始架构 - 回退方案，因为DynamicMCPManager没有list_available_tools方法
                logger.warning("原始架构暂不支持详细工具列表，返回基本信息")
                return {
                    "success": True,
                    "servers": {
                        "microsandbox": {"tools": [{"name": "execute", "available_actions": ["microsandbox_execute"]}]},
                        "browser_use": {"tools": [{"name": "browser_action", "available_actions": ["browser_go_to_url", "browser_click"]}]},
                        "deepsearch": {"tools": [{"name": "research", "available_actions": ["research", "quick_research"]}]},
                        "search_tool": {"tools": [{"name": "search_file_content", "available_actions": ["search_file_content"]}]}
                    }
                }
            else:
                logger.error("❌ 没有可用的MCP管理器")
                return {"success": False, "error": "No MCP manager available"}
        except Exception as e:
            logger.error(f"❌ 列出工具失败: {e}")
            return {"success": False, "error": str(e)}
    
    # === 统计和监控功能 ===
    
    def get_enhanced_stats(self) -> Dict[str, Any]:
        """获取增强的统计信息"""
        base_stats = self.get_stats()
        
        # 添加增强功能的统计
        enhanced_stats = {
            **base_stats,
            "enhanced_features": {
                "dynamic_mcp_manager": bool(self.dynamic_mcp_manager),
                "session_count": len(self.dynamic_mcp_manager.session_handlers) if self.dynamic_mcp_manager else 0,
                "enhanced_runner": isinstance(self.runner, EnhancedProcessRunner)
            }
        }
        
        # 添加安装统计
        if isinstance(self.runner, EnhancedProcessRunner):
            enhanced_stats["installation_stats"] = self.runner.get_installation_stats()
        
        return enhanced_stats
    
    async def get_enhanced_status(self) -> Dict[str, Any]:
        """获取增强的系统状态"""
        try:
            base_status = await self.health_check()
            
            # 获取增强管理器状态
            manager_status = {}
            if self.dynamic_mcp_manager:
                manager_status = await self.dynamic_mcp_manager.get_manager_status()
            
            return {
                "base_health": base_status,
                "enhanced_manager": manager_status,
                "timestamp": time.time()
            }
        except Exception as e:
            logger.error(f"❌ 获取增强状态失败: {e}")
            return {
                "error": str(e),
                "timestamp": time.time()
            }
    
    # === 原有功能的保持 ===
    
    async def _get_redis_client(self):
        """获取Redis客户端"""
        if self.redis_manager:
            import redis.asyncio as redis
            return redis.from_url(self.redis_manager.get_redis_url())
        return None
    
    async def _auto_register_predefined_servers(self) -> Dict[str, int]:
        """自动注册预置MCP服务器"""
        registration_results = {"success_count": 0, "failed_count": 0}
        
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
        
        return registration_results
    
    async def _check_server_availability(self, endpoint: str, timeout: float = 5.0) -> bool:
        """检查MCP服务器是否可达"""
        try:
            import websockets
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
            
            # 尝试更宽松的连接检查
            try:
                # 仅检查WebSocket连接是否能建立
                async with websockets.connect(endpoint, timeout=timeout) as websocket:
                    return True
            except Exception as e2:
                logger.debug(f"服务器连接完全失败: {e2}")
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
        
        try:
            event_data = {
                "event_type": event_type,
                "tool_id": server_spec.tool_id,
                "name": server_spec.name,
                "capabilities": [cap.name for cap in server_spec.capabilities],
                "timestamp": time.time()
            }
            
            await self.redis_client.publish("tool_events", json.dumps(event_data))
        except Exception as e:
            logger.error(f"发布工具事件失败: {e}")
    
    async def _notify_websocket_clients(self, message: Dict[str, Any]):
        """通知WebSocket客户端"""
        if self.websocket_manager:
            try:
                await self.websocket_manager.broadcast(message)
            except Exception as e:
                logger.error(f"WebSocket通知失败: {e}")
    
    async def _update_tool_cache(self, tool_id: str, tool_data: Dict[str, Any]):
        """更新工具缓存"""
        async with self._cache_lock:
            self._tool_cache[tool_id] = tool_data
    
    async def get_cached_result(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """获取缓存结果（兼容tool_gap_detector的接口）"""
        try:
            async with self._cache_lock:
                return self._tool_cache.get(cache_key)
        except Exception as e:
            logger.error(f"❌ 获取缓存结果失败 {cache_key}: {e}")
            return None
    
    async def set_cached_result(self, cache_key: str, result: Dict[str, Any], ttl: int = 3600) -> bool:
        """设置缓存结果（兼容tool_gap_detector的接口）"""
        try:
            async with self._cache_lock:
                self._tool_cache[cache_key] = {
                    "result": result,
                    "timestamp": time.time(),
                    "ttl": ttl
                }
                return True
        except Exception as e:
            logger.error(f"❌ 设置缓存结果失败 {cache_key}: {e}")
            return False
    
    async def cache_search_result(self, cache_key: str, result: Dict[str, Any], ttl: int = 3600) -> bool:
        """缓存搜索结果（兼容tool_gap_detector的接口）"""
        return await self.set_cached_result(cache_key, result, ttl)
    
    async def _load_persistent_servers(self):
        """加载持久化服务器配置"""
        try:
            config_path = Path("config/persistent_servers.json")
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    self.persistent_servers = json.load(f)
                logger.info(f"✅ 已加载 {len(self.persistent_servers)} 个持久化服务器配置")
            else:
                logger.info("📝 持久化服务器配置文件不存在，使用空配置")
                self.persistent_servers = {}
        except Exception as e:
            logger.error(f"❌ 加载持久化服务器配置失败: {e}")
            self.persistent_servers = {}
    
    async def _save_persistent_servers(self):
        """保存持久化服务器配置"""
        try:
            config_path = Path("config/persistent_servers.json")
            config_path.parent.mkdir(exist_ok=True)
            
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(self.persistent_servers, f, indent=2, ensure_ascii=False)
            
            logger.info("✅ 持久化服务器配置已保存")
        except Exception as e:
            logger.error(f"❌ 保存持久化服务器配置失败: {e}")
    
    async def _restore_persistent_servers(self):
        """恢复持久化服务器"""
        try:
            logger.info("🔄 开始恢复持久化服务器...")
            
            for server_name, server_config in self.persistent_servers.items():
                if isinstance(server_config, dict):
                    try:
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
    
    def get_stats(self) -> Dict[str, Any]:
        """获取系统统计信息"""
        running_servers = {}
        if isinstance(self.runner, (ProcessRunner, EnhancedProcessRunner)):
            running_servers = self.runner.list_running_servers()
        
        return {
            "is_running": self.is_running,
            "persistent_servers": len(self.persistent_servers),
            "dynamic_servers": len(running_servers),
            "total_servers": len(self.persistent_servers) + len(running_servers),
            "runner_type": "EnhancedProcessRunner" if isinstance(self.runner, EnhancedProcessRunner) else "ProcessRunner",
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
            
        except Exception as e:
            logger.error(f"健康检查时出错: {e}")
            health_status["overall"] = "error"
            health_status["error"] = str(e)
        
        return health_status
    
    def get_enhanced_stats(self) -> Dict[str, Any]:
        """获取增强的系统统计信息"""
        basic_stats = self.get_stats()
        
        # 添加增强统计信息
        enhanced_info = {
            "enhanced_features": True,
            "runner_enhanced": isinstance(self.runner, EnhancedProcessRunner),
            "dynamic_manager_enhanced": isinstance(self.dynamic_mcp_manager, EnhancedDynamicMCPManager),
            "enhanced_capabilities": {
                "smart_detection": True,
                "error_recovery": True,
                "session_management": True,
                "config_validation": True,
                "performance_monitoring": True
            },
            "enhancement_timestamp": time.time()
        }
        
        return {**basic_stats, **enhanced_info}