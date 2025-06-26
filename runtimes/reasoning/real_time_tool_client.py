"""
实时工具客户端 - Enhanced Reasoning Runtime专用
通过WebSocket监听工具变更，立即响应新工具可用性
"""

import asyncio
import json
import logging
import websockets.legacy.client as websockets_client
import time
from typing import Dict, Any, List, Callable, Optional

# 导入结构化工具系统
from core.toolscore.structured_tools import tool_registry
from core.toolscore.tool_definitions import *  # 自动注册所有工具

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
            websocket_url = self.endpoint
        else:
            # 将HTTP端点转换为WebSocket端点
            websocket_url = self.endpoint.replace('http://', 'ws://').replace('https://', 'wss://')
        
        try:
            logger.info(f"🔌 连接到ToolScore实时更新: {websocket_url}")
            # 创建WebSocket连接（兼容旧版本websockets）
            try:
                # 首选 websockets 库客户端
                try:
                    self.websocket = await websockets_client.connect(
                        websocket_url,
                        extra_headers={
                            "User-Agent": "Enhanced-Reasoning-Runtime/1.0"
                        }
                    )
                except TypeError:
                    # 兼容旧版本websockets，不支持 extra_headers
                    self.websocket = await websockets_client.connect(websocket_url)
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
            if self.websocket is None:
                logger.error("WebSocket连接未建立")
                return
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
                    
        except Exception as e:
            if "ConnectionClosed" in str(type(e)):
                logger.warning("🔌 WebSocket连接已断开")
                self.is_connected = False
                # 尝试重连
                if self.reconnect_attempts < self.max_reconnect_attempts:
                    await self._reconnect_with_delay()
            else:
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
                                     callback: Optional[Callable[[], Any]] = None):
        """注册等待工具的请求"""
        self.pending_tool_requests[request_id] = {
            "required_capabilities": required_capabilities,
            "callback": callback,
            "timestamp": time.time()
        }
        logger.info(f"注册等待工具请求: {request_id} (需要: {required_capabilities})")
    
    async def get_fresh_tools_for_llm(self, fallback_client=None) -> str:
        """获取最新的工具列表 - 优先从实际MCP服务器动态获取"""
        
        # 🔧 修复P0问题：直接从ToolScore客户端获取实时工具信息，而不是使用静态注册表
        if fallback_client:
            try:
                real_time_description = await self._get_real_time_tools_description(fallback_client)
                if real_time_description and real_time_description != "当前无可用工具":
                    logger.info("✅ 使用实时MCP服务器工具描述")
                    return real_time_description
            except Exception as e:
                logger.warning(f"获取实时工具描述失败，回退到静态注册表: {e}")
        
        # 备选1：使用结构化工具注册表（静态定义）
        structured_description = tool_registry.generate_llm_tools_description()
        if structured_description and structured_description != "当前无可用工具":
            logger.warning("⚠️ 使用静态工具注册表（可能不准确）")
            return structured_description
        
        # 备选2：使用传统方法
        logger.warning("⚠️ 回退到传统工具描述")
        return await self._get_legacy_tools_description(fallback_client)
    
    async def _get_real_time_tools_description(self, fallback_client) -> str:
        """从实际MCP服务器获取实时工具信息 - 修复P0契约不匹配问题"""
        try:
            # 获取当前可用的工具列表
            available_tools = await fallback_client.get_available_tools()
            if not available_tools:
                return "当前无可用工具"
            
            tool_descriptions = ["# 实时可用工具"]
            
            # 对每个工具，尝试通过MCP客户端获取真实的Schema
            for tool_id in available_tools:
                try:
                    # 尝试通过MCP客户端获取工具的真实能力
                    tool_description = await self._get_mcp_tool_schema(tool_id, fallback_client)
                    if tool_description:
                        tool_descriptions.append(tool_description)
                    else:
                        # 如果无法获取详细Schema，使用基本信息
                        tool_descriptions.append(f"- **{tool_id}**: 可用工具 (无法获取详细Schema)")
                        
                except Exception as e:
                    logger.warning(f"获取工具 {tool_id} 的Schema失败: {e}")
                    tool_descriptions.append(f"- **{tool_id}**: 可用工具 (Schema获取失败)")
            
            result = "\n".join(tool_descriptions)
            logger.info(f"🔧 实时工具描述生成完成，包含 {len(available_tools)} 个工具")
            return result
            
        except Exception as e:
            logger.error(f"获取实时工具描述失败: {e}")
            raise
    
    async def _get_mcp_tool_schema(self, tool_id: str, fallback_client) -> Optional[str]:
        """通过MCP客户端获取工具的真实Schema"""
        try:
            # 尝试通过ToolScore的原始工具数据获取更多信息
            raw_tools = await fallback_client.get_available_tools_raw()
            
            tool_info = None
            for tool in raw_tools:
                if isinstance(tool, dict) and tool.get('server_id') == tool_id:
                    tool_info = tool
                    break
            
            if tool_info:
                # 构建基于真实数据的工具描述
                server_name = tool_info.get('server_name', tool_id)
                description = tool_info.get('description', f'{server_name} 工具')
                actions = tool_info.get('available_actions', [])
                
                if actions:
                    action_list = ', '.join(actions)
                    return f"- **{tool_id}** ({server_name}): {description}\n  📋 可用操作: {action_list}"
                else:
                    return f"- **{tool_id}** ({server_name}): {description}\n  📋 可用操作: (未知)"
            
            # 如果无法获取详细信息，返回基本格式
            return f"- **{tool_id}**: 可用工具"
            
        except Exception as e:
            logger.warning(f"获取工具 {tool_id} 的MCP Schema失败: {e}")
            return None
    
    async def _get_legacy_tools_description(self, fallback_client=None) -> str:
        """传统的工具描述获取方法（备选）"""
        tool_descriptions = []
        
        # 获取已注册的工具
        if fallback_client:
            try:
                registered_tools = await fallback_client.get_available_tools()
                # registered_tools 现在是一个工具ID列表
                if registered_tools:
                    tool_descriptions.append("# 已注册的工具")
                    for tool_id in registered_tools:
                        # 提供详细的工具描述，包含参数说明和使用示例
                        desc = self._build_legacy_tool_description(tool_id)
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
    
    def _build_detailed_tool_description(self, tool_id: str) -> str:
        """构建详细的工具描述，包含参数和使用示例 - 使用结构化工具系统"""
        
        # 优先使用结构化工具注册表
        tool_def = tool_registry.get_tool(tool_id)
        if tool_def:
            return tool_def.to_llm_description()
        
        # 备选：使用硬编码描述（逐步迁移）
        return self._build_legacy_tool_description(tool_id)
    
    async def get_available_tool_ids(self) -> List[str]:
        """获取所有可用工具的ID列表"""
        try:
            # 首先从结构化工具注册表获取
            structured_tools = tool_registry.get_all_tool_ids()
            
            # 添加缓存中的实时工具
            cached_tool_ids = list(self.available_tools_cache.keys())
            
            # 合并并去重
            all_tool_ids = list(set(structured_tools + cached_tool_ids))
            
            logger.debug(f"可用工具ID列表: {all_tool_ids}")
            return all_tool_ids
            
        except Exception as e:
            logger.error(f"获取可用工具ID列表失败: {e}")
            return []
    
    def _build_legacy_tool_description(self, tool_id: str) -> str:
        """构建传统的工具描述（备选方案）"""
        
        tool_details = {
            "microsandbox": {
                "name": "MicroSandbox安全代码执行器",
                "description": "在安全隔离环境中执行Python代码和管理包",
                "actions": {
                    "microsandbox_execute": {
                        "desc": "执行Python代码",
                        "params": {"code": "要执行的Python代码(必需)", "session_id": "会话ID(可选)", "timeout": "超时秒数(可选)"},
                        "example": '{"code": "print(\'Hello\'); result = 2 + 3; print(result)"}'
                    },
                    "microsandbox_install_package": {
                        "desc": "安装Python包",
                        "params": {"package_name": "包名(必需)", "version": "版本号(可选)", "session_id": "会话ID(可选)"},
                        "example": '{"package_name": "numpy", "version": "1.21.0"}'
                    },
                    "microsandbox_list_sessions": {"desc": "列出活跃会话", "params": {}, "example": "{}"},
                    "microsandbox_close_session": {"desc": "关闭会话", "params": {"session_id": "要关闭的会话ID(必需)"}, "example": '{"session_id": "my-session"}'},
                    "microsandbox_cleanup_expired": {"desc": "清理过期会话", "params": {"max_age": "最大年龄秒数(可选)"}, "example": "{}"}
                }
            },
            "deepsearch": {
                "name": "网络信息研究工具",
                "description": "专门执行在线信息研究和知识综合分析，不涉及工具安装和项目文件操作",
                "actions": {
                    "research": {
                        "desc": "综合性研究",
                        "params": {"question": "研究查询(必需)", "max_results": "最大结果数(可选)", "depth": "研究深度(可选)"},
                        "example": '{"question": "Python asyncio最佳实践", "max_results": 10}'
                    },
                    "quick_research": {
                        "desc": "快速研究",
                        "params": {"question": "研究查询(必需)", "max_results": "最大结果数(可选)"},
                        "example": '{"question": "机器学习基础概念"}'
                    },
                    "comprehensive_research": {
                        "desc": "全面深入研究",
                        "params": {"question": "研究查询(必需)", "max_results": "最大结果数(可选)", "include_analysis": "是否包含分析(可选)"},
                        "example": '{"question": "区块链技术发展趋势", "include_analysis": true}'
                    }
                }
            },
            "browser_use": {
                "name": "智能浏览器操作工具",
                "description": "自动化网页浏览、交互和内容提取",
                "actions": {
                    "browser_navigate": {
                        "desc": "导航到指定URL",
                        "params": {"url": "目标URL(必需)"},
                        "example": '{"url": "https://python.org"}'
                    },
                    "browser_extract_content": {
                        "desc": "获取页面内容",
                        "params": {"url": "页面URL(可选，使用当前页面)", "selector": "CSS选择器(可选)"},
                        "example": '{"selector": "h1, p"}'
                    },
                    "browser_click_element": {
                        "desc": "点击页面元素",
                        "params": {"index": "元素索引(必需)", "wait_time": "等待时间(可选)"},
                        "example": '{"index": 0}'
                    },
                    "browser_input_text": {
                        "desc": "在页面元素中输入文本",
                        "params": {"index": "元素索引(必需)", "text": "要输入的文本(必需)"},
                        "example": '{"index": 0, "text": "Hello World"}'
                    },
                    "browser_search_google": {
                        "desc": "使用Google搜索",
                        "params": {"query": "搜索查询(必需)"},
                        "example": '{"query": "Python教程"}'
                    },
                    "browser_use_execute_task": {
                        "desc": "执行复杂的浏览器任务",
                        "params": {"task": "任务描述(必需)", "max_steps": "最大步骤数(可选)"},
                        "example": '{"task": "登录网站并查找特定信息"}'
                    }
                }
            },
            "mcp-search-tool": {
                "name": "工具管理和项目文件搜索器",
                "description": "专门负责工具安装管理、项目内文件搜索和代码分析，不涉及在线信息研究",
                "actions": {
                    "search_file_content": {
                        "desc": "搜索文件内容",
                        "params": {"file_path": "文件路径(必需)", "regex_pattern": "正则表达式(必需)"},
                        "example": '{"file_path": "src/main.py", "regex_pattern": "def.*"}'
                    },
                    "list_code_definitions": {
                        "desc": "列出代码定义",
                        "params": {"file_path": "文件路径(可选)", "directory_path": "目录路径(可选)"},
                        "example": '{"directory_path": "src/"}'
                    },
                    "analyze_tool_needs": {
                        "desc": "分析任务的工具需求",
                        "params": {"task_description": "任务描述(必需)"},
                        "example": '{"task_description": "创建数据可视化图表"}'
                    },
                    "search_and_install_tools": {
                        "desc": "搜索并安装新工具",
                        "params": {"task_description": "任务描述(必需)", "reason": "需要原因(可选)"},
                        "example": '{"task_description": "需要处理PDF文件", "reason": "当前工具不支持PDF操作"}'
                    }
                }
            }
        }
        
        if tool_id not in tool_details:
            # 对于未知工具，返回基本描述
            return f"- {tool_id}: 可用工具 (操作: 请参考工具文档)"
        
        tool_info = tool_details[tool_id]
        desc_lines = [f"- **{tool_id}** ({tool_info['name']}): {tool_info['description']}"]
        
        desc_lines.append("  📋 可用操作:")
        for action_name, action_info in tool_info['actions'].items():
            desc_lines.append(f"    • {action_name}: {action_info['desc']}")
            if action_info['params']:
                param_desc = ", ".join([f"{k}: {v}" for k, v in action_info['params'].items()])
                desc_lines.append(f"      参数: {param_desc}")
            desc_lines.append(f"      示例: {action_info['example']}")
        
        return "\n".join(desc_lines)