"""
MCP Server搜索和安装工具 - 优化版本
专注LLM智能选择，移除复杂加权打分逻辑
"""

import logging
import json
from typing import Dict, Any, List, Optional
import os

from .tool_gap_detector import ToolGapDetector
from core.toolscore.managers.dynamic_mcp_manager import DynamicMCPManager, MCPSearchResult

logger = logging.getLogger(__name__)

class MCPSearchTool:
    """MCP搜索和安装工具 - 简化版本，专注LLM智能选择"""
    
    def __init__(self, tool_gap_detector: ToolGapDetector, dynamic_mcp_manager: DynamicMCPManager):
        self.tool_gap_detector = tool_gap_detector
        self.dynamic_mcp_manager = dynamic_mcp_manager
        
        # 缓存mcp_tools.json数据，避免重复磁盘I/O
        self._mcp_tools_path: Optional[str] = None
        self._mcp_tools_data: Optional[List[Dict[str, Any]]] = None
        
        logger.info("✅ MCP Search Tool initialized - 优化版本")
    
    async def search_and_install_tools(self, task_description: str, current_available_tools: List[Dict[str, Any]], 
                                       reason: str = "") -> MCPSearchResult:
        """
        搜索并安装适合当前任务的MCP服务器
        优化版本：直接使用LLM从本地JSON中选择工具
        """
        logger.info(f"🔍 开始智能工具搜索: {task_description[:100]}...")
        if reason:
            logger.info(f"搜索原因: {reason}")
        
        try:
            # 1. 快速工具缺口分析
            analysis = await self.tool_gap_detector.analyze_tool_sufficiency(
                task_description, current_available_tools
            )
            
            if analysis.has_sufficient_tools:
                return MCPSearchResult(
                    success=False,
                    message="当前工具已足够完成任务，无需安装新工具",
                    installed_tools=[]
                )
            
            # 2. LLM智能选择工具（核心优化）
            selected_tools = await self.find_matching_tools_from_analysis(
                task_description, 
                getattr(analysis, 'tool_requirements', [])
            )
            
            if not selected_tools:
                return MCPSearchResult(
                    success=False,
                    message="LLM未找到合适的工具候选",
                    installed_tools=[]
                )
            
            logger.info(f"🎯 LLM选择了 {len(selected_tools)} 个工具候选")
            
            # 3. 尝试安装第一个推荐工具
            for i, tool_info in enumerate(selected_tools[:2], 1):  # 最多尝试前2个
                logger.info(f"📦 尝试安装工具 {i}: {tool_info.get('name', 'Unknown')}")
                
                # 构造候选者对象
                candidate = await self._create_candidate_from_tool_info(tool_info)
                if not candidate:
                    continue
                
                # 安装工具
                install_result = await self.dynamic_mcp_manager.install_mcp_server(candidate)
                
                if install_result.success:
                    # 注册到工具库
                    registration_result = await self.dynamic_mcp_manager.register_installed_server(
                        candidate, install_result
                    )
                    
                    if registration_result.success:
                        logger.info(f"✅ 成功安装并注册工具: {candidate.name}")
                        return MCPSearchResult(
                            success=True,
                            message=f"成功安装工具: {candidate.name}",
                            installed_tools=[{
                            "name": candidate.name,
                            "description": candidate.description,
                            "capabilities": candidate.capabilities,
                                "server_id": install_result.server_id,
                                "selection_reason": tool_info.get('reason', 'LLM推荐')
                            }]
                        )
                    else:
                        logger.warning(f"⚠️ 工具安装成功但注册失败: {candidate.name}")
                else:
                    logger.warning(f"❌ 工具安装失败: {tool_info.get('name')} - {install_result.error_message}")
            
                return MCPSearchResult(
                    success=False,
                message="所有推荐工具安装均失败",
                    installed_tools=[]
                )
        
        except Exception as e:
            logger.error(f"❌ MCP搜索安装过程异常: {e}")
            return MCPSearchResult(
                success=False,
                message=f"搜索安装失败: {str(e)}",
                installed_tools=[]
            )
    
    async def analyze_tool_needs(self, task_description: str, current_available_tools: List[Dict[str, Any]]) -> Dict[str, Any]:
        """分析工具需求，返回LLM推荐但不执行安装"""
        logger.info(f"🧠 分析任务工具需求: {task_description[:100]}...")
        
        try:
            # 工具缺口检测
            analysis = await self.tool_gap_detector.analyze_tool_sufficiency(
                task_description, current_available_tools
            )
            
            # 格式化分析结果
            has_sufficient = getattr(analysis, 'has_sufficient_tools', False)
            
            result = {
                "has_sufficient_tools": has_sufficient,
                "overall_assessment": getattr(analysis, 'overall_assessment', '分析完成'),
                "recommended_action": "continue_with_existing_tools" if has_sufficient else "search_for_new_tools"
            }
            
            # 如果工具不足，获取LLM推荐
            if not has_sufficient:
                recommended_tools = await self.find_matching_tools_from_analysis(
                    task_description, 
                    getattr(analysis, 'tool_requirements', [])
                )
                result["recommended_mcp_tools"] = recommended_tools
                result["tool_count"] = len(recommended_tools)
            
            logger.info(f"✅ 工具需求分析完成，推荐工具数: {result.get('tool_count', 0)}")
            return result
            
        except Exception as e:
            logger.error(f"❌ 工具需求分析失败: {e}")
            return {
                "has_sufficient_tools": False,
                "overall_assessment": f"分析失败: {str(e)}",
                "recommended_action": "error",
                "recommended_mcp_tools": [],
                "error": str(e)
            }

    async def find_matching_tools_from_analysis(self, task_description: str, 
                                              tool_requirements: List[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        核心优化：让LLM直接从mcp_tools.json中选择最佳工具
        移除复杂的加权打分，单次磁盘I/O，纯LLM决策
        """
        logger.info("🤖 LLM开始智能工具选择...")
        try:
            # 单次加载工具数据（缓存机制）
            tools_data = await self._load_mcp_tools()
            logger.info(f"📚 加载了 {len(tools_data)} 个工具定义")

            # 截断工具列表避免prompt过大
            MAX_TOOLS_FOR_LLM = 150
            truncated_tools = tools_data[:MAX_TOOLS_FOR_LLM]
            
            # 构造优化的LLM选择prompt
            prompt = self._build_tool_selection_prompt(task_description, truncated_tools)
            
            # 🔍 新增：记录发送给LLM的完整prompt
            logger.info("📤 发送给LLM的prompt:")
            logger.info(f"   任务描述: {task_description}")
            logger.info(f"   可选工具数量: {len(truncated_tools)}")
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"   完整prompt (前500字符): {prompt[:500]}...")
                logger.debug(f"   工具列表示例: {[tool.get('name', 'Unknown') for tool in truncated_tools[:5]]}")

            # 调用LLM进行选择（明确指定gemini提供商）
            from core.llm.llm_client import LLMClient
            llm_client = LLMClient({"provider": "gemini"})
            llm_response = await llm_client._call_api(prompt)
            
            # 🔍 新增：记录LLM的原始响应
            logger.info("📥 LLM响应接收:")
            logger.info(f"   响应长度: {len(llm_response)} 字符")
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"   原始响应 (前300字符): {llm_response[:300]}...")
            
            # 解析LLM返回的JSON
            selected_tools = self._parse_llm_tool_selection(llm_response)
            
            # 🔍 新增：记录解析结果详情
            if selected_tools:
                logger.info(f"✅ LLM成功选择了 {len(selected_tools)} 个工具")
                for i, tool in enumerate(selected_tools, 1):
                    tool_name = tool.get('name', 'Unknown')
                    tool_reason = tool.get('reason', 'No reason')
                    logger.info(f"   {i}. {tool_name}: {tool_reason}")
                    if logger.isEnabledFor(logging.DEBUG):
                        logger.debug(f"      完整工具信息: {tool}")
            else:
                logger.warning("⚠️ LLM未返回有效的工具选择")
                logger.warning(f"   原始响应: {llm_response}")
            
            return selected_tools

        except Exception as e:
            logger.error(f"❌ LLM工具选择失败: {e}")
            logger.error(f"   异常类型: {type(e).__name__}")
            if hasattr(e, 'response'):
                logger.error(f"   API响应: {getattr(e, 'response', 'No response')}")
            return []

    def _build_tool_selection_prompt(self, task_description: str, tools_data: List[Dict[str, Any]]) -> str:
        """构建优化的LLM工具选择prompt"""
        return f"""You are an expert MCP tool selector. Analyze the task and select the most suitable tools.

Task Description:
{task_description}

Instructions:
1. Select up to 5 tools that best match the task requirements
2. Return ONLY a JSON array, no other text
3. Each tool should have: tool_id, name, description, reason

Available Tools:
{json.dumps(tools_data, ensure_ascii=False)}

Return format:
[{{"tool_id": "...", "name": "...", "description": "...", "reason": "why this tool is perfect for the task"}}]"""

    def _parse_llm_tool_selection(self, llm_response: str) -> List[Dict[str, Any]]:
        """解析LLM返回的工具选择结果"""
        try:
            import re
            
            # 提取JSON数组
            json_match = re.search(r'\[.*?\]', llm_response, re.DOTALL)
            if not json_match:
                logger.warning("LLM响应中未找到JSON数组")
                return []

            json_str = json_match.group(0)
            selected_tools = json.loads(json_str)
            
            # 验证格式
            if not isinstance(selected_tools, list):
                logger.warning("LLM返回的不是数组格式")
                return []
            
            # 验证每个工具的必需字段
            valid_tools = []
            for tool in selected_tools:
                if isinstance(tool, dict) and all(key in tool for key in ['tool_id', 'name']):
                    valid_tools.append(tool)
                else:
                    logger.warning(f"工具格式无效，跳过: {tool}")
            
            return valid_tools
            
        except json.JSONDecodeError as e:
            logger.error(f"解析LLM JSON响应失败: {e}")
            return []
        except Exception as e:
            logger.error(f"处理LLM响应异常: {e}")
            return []

    async def _create_candidate_from_tool_info(self, tool_info: Dict[str, Any]):
        """从工具信息创建MCP候选者对象"""
        try:
            # 根据实际的MCPServerCandidate类结构来构建
            from .dynamic_mcp_manager import MCPServerCandidate
            
            return MCPServerCandidate(
                name=tool_info.get('name', 'Unknown Tool'),
                description=tool_info.get('description', ''),
                github_url=tool_info.get('github_url', tool_info.get('repository_url', '')),
                author=tool_info.get('author', 'Unknown'),
                tags=tool_info.get('tags', []),
                install_method=tool_info.get('install_method', 'pip'),
                capabilities=tool_info.get('capabilities', []),
                verified=tool_info.get('verified', False),
                security_score=tool_info.get('security_score', 0.0),
                popularity_score=tool_info.get('popularity_score', 0.0)
            )
        except Exception as e:
            logger.error(f"创建工具候选者失败: {e}")
            return None

    async def _load_mcp_tools(self) -> List[Dict[str, Any]]:
        """
        懒加载并缓存mcp_tools.json数据
        优化：单次磁盘I/O + 内存缓存
        """
        if self._mcp_tools_data is None:
            # 固定相对路径，避免路径查找开销
            self._mcp_tools_path = "mcp_tools.json"
            
            if not os.path.exists(self._mcp_tools_path):
                logger.error(f"❌ 工具定义文件不存在: {self._mcp_tools_path}")
                raise FileNotFoundError(f"mcp_tools.json not found at {self._mcp_tools_path}")
            
            logger.info(f"📖 首次加载工具定义文件: {self._mcp_tools_path}")
            with open(self._mcp_tools_path, 'r', encoding='utf-8') as f:
                self._mcp_tools_data = json.load(f)
            
            logger.info(f"✅ 工具定义已缓存，共 {len(self._mcp_tools_data)} 个工具")
        
        return self._mcp_tools_data 