"""
自动注册预置MCP服务器
在ToolScore启动时自动发现和注册运行中的MCP服务器
"""

import asyncio
import logging
import websockets
import json
from typing import List, Dict, Any, Optional
from .interfaces import MCPServerSpec, ToolCapability, ToolType
from .unified_tool_library import UnifiedToolLibrary

logger = logging.getLogger(__name__)

class AutoMCPRegistrar:
    """自动MCP服务器注册器"""
    
    def __init__(self, tool_library: UnifiedToolLibrary):
        self.tool_library = tool_library
        
        # 预置MCP服务器配置
        self.predefined_servers = [
            {
                "tool_id": "python-executor-server",
                "name": "Python Executor",
                "description": "Execute Python code and scripts with full programming capabilities",
                "endpoint": "ws://python-executor-server:8081/mcp",
                "capabilities": [
                    {
                        "name": "python_execute",
                        "description": "Execute Python code and return results",
                        "parameters": {
                            "code": {
                                "type": "string",
                                "description": "Python code to execute",
                                "required": True
                            }
                        }
                    },
                    {
                        "name": "python_install_package",
                        "description": "Install Python packages using pip",
                        "parameters": {
                            "package": {
                                "type": "string", 
                                "description": "Package name to install",
                                "required": True
                            }
                        }
                    }
                ],
                "tags": ["python", "code", "execution", "programming"]
            },
            {
                "tool_id": "browser-navigator-server", 
                "name": "Browser Navigator",
                "description": "Navigate web pages, extract content, and perform browser automation",
                "endpoint": "ws://browser-navigator-server:8082/mcp",
                "capabilities": [
                    {
                        "name": "navigate_to_url",
                        "description": "Navigate to a specific URL",
                        "parameters": {
                            "url": {
                                "type": "string",
                                "description": "URL to navigate to",
                                "required": True
                            }
                        }
                    },
                    {
                        "name": "extract_page_content",
                        "description": "Extract text content from current page",
                        "parameters": {}
                    },
                    {
                        "name": "click_element",
                        "description": "Click on a page element",
                        "parameters": {
                            "selector": {
                                "type": "string",
                                "description": "CSS selector for the element",
                                "required": True
                            }
                        }
                    }
                ],
                "tags": ["browser", "web", "navigation", "automation"]
            }
        ]
    
    async def auto_register_predefined_servers(self) -> Dict[str, Any]:
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
                    # 注册服务器
                    result = await self._register_server(server_config)
                    
                    if result["success"]:
                        registration_results["success_count"] += 1
                        logger.info(f"✅ 成功注册: {server_config['name']}")
                    else:
                        registration_results["failed_count"] += 1
                        logger.error(f"❌ 注册失败: {server_config['name']} - {result['error']}")
                    
                    registration_results["results"].append(result)
                else:
                    registration_results["failed_count"] += 1
                    error_msg = f"服务器不可达: {server_config['endpoint']}"
                    logger.warning(f"⚠️ {server_config['name']}: {error_msg}")
                    
                    registration_results["results"].append({
                        "tool_id": server_config["tool_id"],
                        "success": False,
                        "error": error_msg
                    })
            
            except Exception as e:
                registration_results["failed_count"] += 1
                error_msg = f"注册异常: {str(e)}"
                logger.error(f"❌ {server_config['name']}: {error_msg}")
                
                registration_results["results"].append({
                    "tool_id": server_config["tool_id"],
                    "success": False,
                    "error": error_msg
                })
        
        logger.info(f"🎯 自动注册完成: {registration_results['success_count']} 成功, {registration_results['failed_count']} 失败")
        return registration_results
    
    async def _check_server_availability(self, endpoint: str, timeout: float = 5.0) -> bool:
        """检查MCP服务器是否可达"""
        try:
            # 尝试建立WebSocket连接
            async with websockets.connect(endpoint, timeout=timeout) as websocket:
                # 发送简单的ping消息
                ping_message = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "ping"
                }
                
                await websocket.send(json.dumps(ping_message))
                
                # 等待响应（可能是pong或者错误，只要有响应就说明服务器活着）
                try:
                    response = await asyncio.wait_for(websocket.recv(), timeout=2.0)
                    logger.debug(f"服务器 {endpoint} 响应: {response[:100]}...")
                    return True
                except asyncio.TimeoutError:
                    # 超时也算可达，可能服务器不支持ping
                    logger.debug(f"服务器 {endpoint} 连接成功但无响应，认为可达")
                    return True
                    
        except Exception as e:
            logger.debug(f"服务器 {endpoint} 不可达: {e}")
            return False
    
    async def _register_server(self, server_config: Dict[str, Any]) -> Dict[str, Any]:
        """注册单个MCP服务器"""
        try:
            # 创建工具能力列表
            capabilities = []
            for cap_config in server_config["capabilities"]:
                capability = ToolCapability(
                    name=cap_config["name"],
                    description=cap_config["description"],
                    parameters=cap_config["parameters"]
                )
                capabilities.append(capability)
            
            # 创建MCP服务器规范
            server_spec = MCPServerSpec(
                tool_id=server_config["tool_id"],
                name=server_config["name"],
                description=server_config["description"],
                tool_type=ToolType.MCP_SERVER,
                capabilities=capabilities,
                tags=server_config["tags"],
                enabled=True,
                endpoint=server_config["endpoint"]
            )
            
            # 注册到工具库
            registration_result = await self.tool_library.register_external_mcp_server(server_spec)
            
            return {
                "tool_id": server_config["tool_id"],
                "success": registration_result.success,
                "error": registration_result.error if not registration_result.success else None
            }
            
        except Exception as e:
            return {
                "tool_id": server_config["tool_id"],
                "success": False,
                "error": str(e)
            }
    
    async def discover_and_register_dynamic_servers(self, port_range: tuple = (8100, 8200)) -> Dict[str, Any]:
        """发现并注册动态MCP服务器（在指定端口范围内）"""
        logger.info(f"🔍 开始发现动态MCP服务器 (端口范围: {port_range[0]}-{port_range[1]})...")
        
        discovery_results = {
            "discovered_count": 0,
            "registered_count": 0,
            "servers": []
        }
        
        # 在端口范围内扫描
        for port in range(port_range[0], port_range[1] + 1):
            endpoint = f"ws://localhost:{port}/mcp"
            
            try:
                is_available = await self._check_server_availability(endpoint, timeout=1.0)
                
                if is_available:
                    discovery_results["discovered_count"] += 1
                    logger.info(f"🎯 发现动态MCP服务器: {endpoint}")
                    
                    # 尝试获取服务器信息并注册
                    server_info = await self._discover_server_info(endpoint)
                    if server_info:
                        # 注册服务器
                        register_result = await self._register_discovered_server(server_info, endpoint)
                        if register_result["success"]:
                            discovery_results["registered_count"] += 1
                        
                        discovery_results["servers"].append(register_result)
                    
            except Exception as e:
                logger.debug(f"扫描端口 {port} 时出错: {e}")
                continue
        
        logger.info(f"🎯 动态发现完成: 发现 {discovery_results['discovered_count']} 个，注册 {discovery_results['registered_count']} 个")
        return discovery_results
    
    async def _discover_server_info(self, endpoint: str) -> Optional[Dict[str, Any]]:
        """通过连接获取服务器信息"""
        try:
            async with websockets.connect(endpoint, timeout=3.0) as websocket:
                # 尝试获取服务器信息
                info_request = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/list"
                }
                
                await websocket.send(json.dumps(info_request))
                response = await asyncio.wait_for(websocket.recv(), timeout=2.0)
                
                # 解析响应获取工具信息
                data = json.loads(response)
                if "result" in data and "tools" in data["result"]:
                    return {
                        "tools": data["result"]["tools"],
                        "server_name": f"Dynamic MCP Server ({endpoint.split(':')[-2]})"
                    }
                    
        except Exception as e:
            logger.debug(f"无法获取服务器 {endpoint} 的信息: {e}")
            
        return None
    
    async def _register_discovered_server(self, server_info: Dict[str, Any], endpoint: str) -> Dict[str, Any]:
        """注册发现的动态服务器"""
        try:
            port = endpoint.split(":")[-2]
            tool_id = f"dynamic-mcp-server-{port}"
            
            # 从工具信息推断能力
            capabilities = []
            tools = server_info.get("tools", [])
            
            for tool in tools:
                capability = ToolCapability(
                    name=tool.get("name", "unknown"),
                    description=tool.get("description", "Dynamic tool"),
                    parameters=tool.get("inputSchema", {}).get("properties", {})
                )
                capabilities.append(capability)
            
            # 创建服务器规范
            server_spec = MCPServerSpec(
                tool_id=tool_id,
                name=server_info["server_name"],
                description=f"Dynamically discovered MCP server on {endpoint}",
                tool_type=ToolType.MCP_SERVER,
                capabilities=capabilities,
                tags=["dynamic", "discovered"],
                enabled=True,
                endpoint=endpoint
            )
            
            # 注册服务器
            registration_result = await self.tool_library.register_external_mcp_server(server_spec)
            
            return {
                "tool_id": tool_id,
                "endpoint": endpoint,
                "success": registration_result.success,
                "error": registration_result.error if not registration_result.success else None,
                "tools_count": len(tools)
            }
            
        except Exception as e:
            return {
                "tool_id": f"dynamic-{endpoint.split(':')[-2]}",
                "endpoint": endpoint,
                "success": False,
                "error": str(e),
                "tools_count": 0
            } 