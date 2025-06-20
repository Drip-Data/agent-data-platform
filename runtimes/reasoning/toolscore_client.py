"""
ToolScore轻量级客户端 - Enhanced Reasoning Runtime专用
简化的HTTP API调用，专注于工具获取和能力请求
"""

import asyncio
import aiohttp
import json
import logging
import time
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

class ToolScoreClient:
    """ToolScore轻量级客户端 - 纯API调用，无复杂状态管理"""
    
    def __init__(self, toolscore_endpoint: str):
        self.endpoint = toolscore_endpoint.rstrip('/')
        self.session = None
        self.timeout = aiohttp.ClientTimeout(total=120)  # 增加到120秒以支持深度搜索
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession(timeout=self.timeout)
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def _ensure_session(self):
        """确保HTTP会话已初始化"""
        if not self.session:
            self.session = aiohttp.ClientSession(timeout=self.timeout)
    
    async def get_available_tools_for_llm(self) -> str:
        """获取格式化的工具列表，直接用于LLM决策"""
        await self._ensure_session()
        
        try:
            async with self.session.get(f"{self.endpoint}/api/v1/tools/available") as response:
                if response.status == 200:
                    data = await response.json()
                    # 从API实际返回的结构中获取工具列表并格式化
                    if "available_tools" in data:
                        tools = data["available_tools"]
                        formatted_lines = []
                        for tool in tools:
                            if isinstance(tool, dict):
                                name = tool.get("server_name", tool.get("server_id", "Unknown"))
                                desc = tool.get("description", "")
                                formatted_lines.append(f"- {name}: {desc}")
                            else:
                                formatted_lines.append(f"- {tool}")
                        return "\n".join(formatted_lines)
                    return ""
                else:
                    logger.error(f"获取工具列表失败: HTTP {response.status}")
                    return ""
                    
        except Exception as e:
            logger.error(f"获取工具列表时发生异常: {e}")
            return ""
    
    async def get_available_tools_raw(self) -> List[Dict[str, Any]]:
        """获取原始工具列表数据"""
        await self._ensure_session()
        
        try:
            async with self.session.get(f"{self.endpoint}/api/v1/tools/available") as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("tools", [])
                else:
                    logger.error(f"获取原始工具列表失败: HTTP {response.status}")
                    return []
                    
        except Exception as e:
            logger.error(f"获取原始工具列表时发生异常: {e}")
            return []
    
    async def analyze_tool_needs(self, task_description: str) -> Dict[str, Any]:
        """分析工具需求 - 兼容性方法"""
        await self._ensure_session()
        
        try:
            # 调用工具缺口分析API
            gap_result = await self.analyze_tool_gap(task_description=task_description)
            
            if gap_result.get("has_sufficient_tools", True):
                return {
                    "success": True,
                    "analysis": {
                        "needed_tools": [],
                        "recommendations": "现有工具已充足"
                    }
                }
            else:
                missing_caps = gap_result.get("gap_analysis", {}).get("missing_capabilities", [])
                return {
                    "success": True, 
                    "analysis": {
                        "needed_tools": missing_caps,
                        "recommendations": f"需要补充工具以支持: {', '.join(missing_caps)}"
                    }
                }
                
        except Exception as e:
            logger.error(f"工具需求分析时发生异常: {e}")
            return {
                "success": False,
                "analysis": {
                    "needed_tools": [],
                    "recommendations": f"分析失败: {str(e)}"
                }
            }
    
    async def request_tool_capability(self, task_description: str, 
                                    required_capabilities: List[str] = None,
                                    auto_install: bool = True) -> Dict[str, Any]:
        """一站式工具能力请求服务 - LLM发现缺少工具时调用"""
        await self._ensure_session()
        
        # 获取当前可用工具列表
        current_tools = await self.get_available_tools_raw()
        
        request_data = {
            "task_description": task_description,
            "auto_install": auto_install,
            "current_tools": current_tools
        }
        
        if required_capabilities:
            request_data["required_capabilities"] = required_capabilities
        
        try:
            async with self.session.post(
                f"{self.endpoint}/api/v1/tools/request-capability",
                json=request_data
            ) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    error_text = await response.text()
                    logger.error(f"工具能力请求失败: HTTP {response.status}, {error_text}")
                    return {
                        "success": False,
                        "message": f"HTTP {response.status}: {error_text}",
                        "action_taken": "request_failed"
                    }
                    
        except Exception as e:
            logger.error(f"工具能力请求时发生异常: {e}")
            return {
                "success": False,
                "message": f"请求异常: {str(e)}",
                "action_taken": "request_failed"
            }
    
    async def analyze_tool_gap(self, task_description: str, 
                             current_tools: List[Dict[str, Any]] = None) -> Dict[str, Any]:
        """分析工具缺口，不执行安装"""
        await self._ensure_session()
        
        request_data = {
            "task_description": task_description
        }
        
        if current_tools:
            request_data["current_tools"] = current_tools
        
        try:
            async with self.session.post(
                f"{self.endpoint}/api/v1/tools/analyze-gap",
                json=request_data
            ) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    error_text = await response.text()
                    logger.error(f"工具缺口分析失败: HTTP {response.status}, {error_text}")
                    return {
                        "has_sufficient_tools": True,  # 默认假设工具充足
                        "gap_analysis": {
                            "missing_capabilities": [],
                            "confidence_score": 0.0,
                            "reasoning": f"分析失败: {error_text}"
                        }
                    }
                    
        except Exception as e:
            logger.error(f"工具缺口分析时发生异常: {e}")
            return {
                "has_sufficient_tools": True,
                "gap_analysis": {
                    "missing_capabilities": [],
                    "confidence_score": 0.0,
                    "reasoning": f"分析异常: {str(e)}"
                }
            }
    
    async def get_tool_detail(self, tool_id: str) -> Optional[Dict[str, Any]]:
        """获取特定工具的详细信息"""
        await self._ensure_session()
        
        try:
            async with self.session.get(f"{self.endpoint}/api/v1/tools/{tool_id}") as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.error(f"获取工具详情失败: HTTP {response.status}")
                    return None
                    
        except Exception as e:
            logger.error(f"获取工具详情时发生异常: {e}")
            return None
    
    async def execute_tool_via_mcp(self, tool_id: str, action: str, 
                                 parameters: Dict[str, Any]) -> Dict[str, Any]:
        """直接调用MCP服务器执行工具（实际执行逻辑在其他地方）"""
        # 这个方法主要用于获取MCP端点信息
        tool_info = await self.get_tool_detail(tool_id)
        
        if tool_info:
            return {
                "success": True,
                "mcp_endpoint": tool_info.get("mcp_endpoint"),
                "tool_info": tool_info
            }
        else:
            return {
                "success": False,
                "message": f"工具 {tool_id} 未找到"
            }
    
    async def health_check(self) -> bool:
        """检查ToolScore服务健康状态"""
        await self._ensure_session()
        
        try:
            async with self.session.get(f"{self.endpoint}/health") as response:
                return response.status == 200
        except:
            return False
    
    async def wait_for_ready(self, max_wait_seconds: int = 60) -> bool:
        """等待ToolScore服务就绪"""
        start_time = time.time()
        
        while time.time() - start_time < max_wait_seconds:
            if await self.health_check():
                logger.info("✅ ToolScore服务已就绪")
                return True
            await asyncio.sleep(1)
        
        logger.error("❌ ToolScore服务未就绪")
        return False
    
    async def get_available_tools(self) -> List[str]:
        """获取已注册工具列表 - 返回工具ID列表"""
        await self._ensure_session()
        
        try:
            async with self.session.get(f"{self.endpoint}/api/v1/tools/available") as response:
                if response.status == 200:
                    data = await response.json()
                    # 提取工具ID列表
                    tools = data.get("available_tools", [])
                    return [tool.get("tool_id", "") for tool in tools if isinstance(tool, dict) and tool.get("tool_id")]
                else:
                    logger.error(f"获取已注册工具列表失败: HTTP {response.status}")
                    return []
                    
        except Exception as e:
            logger.error(f"获取已注册工具列表时发生异常: {e}")
            return []
    
    async def close(self):
        """关闭HTTP会话"""
        if self.session:
            await self.session.close()
            self.session = None
    
    async def execute_tool(self, tool_id: str, action: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """调用 ToolScore 执行指定工具动作。

        Parameters
        ----------
        tool_id : str
            工具唯一 ID。
        action : str
            需要执行的动作名称（可为空字符串，表示默认动作）。
        parameters : Dict[str, Any]
            传递给工具的参数。

        Returns
        -------
        Dict[str, Any]
            与 ToolScore `/api/v1/tools/execute` 相同结构的 JSON 响应。
        """
        await self._ensure_session()

        payload = {
            "tool_id": tool_id,
            "action": action,
            "parameters": parameters or {}
        }

        try:
            async with self.session.post(f"{self.endpoint}/api/v1/tools/execute", json=payload) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    # 尝试解析错误信息
                    try:
                        err_text = await response.text()
                    except Exception:
                        err_text = "Unknown error"
                    logger.error(f"执行工具失败: HTTP {response.status}, {err_text}")
                    return {
                        "success": False,
                        "message": f"HTTP {response.status}: {err_text}",
                        "status": response.status
                    }
        except Exception as e:
            logger.error(f"执行工具请求异常: {e}")
            return {
                "success": False,
                "message": str(e),
                "status": 500
            }
    
    async def register_external_mcp_server(self, server_spec: Dict[str, Any]) -> Dict[str, Any]:
        """注册已有的 MCP Server 到 ToolScore（管理端点 /admin/mcp/register）。

        server_spec 示例::
            {
              "tool_id": "my-server",
              "name": "My Custom Server",
              "description": "...",
              "endpoint": "ws://host:port/mcp",
              "capabilities": [{"name": "do", "description": "..."}],
              "tags": ["custom"]
            }
        """
        await self._ensure_session()
        try:
            async with self.session.post(f"{self.endpoint}/admin/mcp/register", json={"server_spec": server_spec}) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    txt = await resp.text()
                    return {"success": False, "status": resp.status, "message": txt}
        except Exception as e:
            return {"success": False, "message": str(e)} 