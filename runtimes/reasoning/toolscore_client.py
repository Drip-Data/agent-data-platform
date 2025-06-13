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
        self.timeout = aiohttp.ClientTimeout(total=30)
        
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
                    return data.get("formatted_tools_description", "")
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
    
    async def request_tool_capability(self, task_description: str, 
                                    required_capabilities: List[str] = None,
                                    auto_install: bool = True) -> Dict[str, Any]:
        """一站式工具能力请求服务 - LLM发现缺少工具时调用"""
        await self._ensure_session()
        
        request_data = {
            "task_description": task_description,
            "auto_install": auto_install
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
    
    async def get_available_tools(self) -> Dict[str, Any]:
        """获取已注册工具列表"""
        await self._ensure_session()
        
        try:
            async with self.session.get(f"{self.endpoint}/api/v1/tools/available") as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.error(f"获取已注册工具列表失败: HTTP {response.status}")
                    return {"available_tools": []}
                    
        except Exception as e:
            logger.error(f"获取已注册工具列表时发生异常: {e}")
            return {"available_tools": []}
    
    async def close(self):
        """关闭HTTP会话"""
        if self.session:
            await self.session.close()
            self.session = None 