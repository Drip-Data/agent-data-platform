"""
MCP Server搜索和安装工具
让AI主动选择搜索和安装新的MCP服务器
"""

import logging
import json
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
import asyncio

from .tool_gap_detector import ToolGapDetector
from .dynamic_mcp_manager import DynamicMCPManager, MCPSearchResult

logger = logging.getLogger(__name__)

class MCPSearchTool:
    """MCP搜索和安装工具 - 支持AI主动扩展工具能力"""
    
    def __init__(self, tool_gap_detector: ToolGapDetector, dynamic_mcp_manager: DynamicMCPManager):
        self.tool_gap_detector = tool_gap_detector
        self.dynamic_mcp_manager = dynamic_mcp_manager
        logger.info("MCP Search Tool initialized")
    
    async def search_and_install_tools(self, task_description: str, current_available_tools: List[Dict[str, Any]], 
                                       reason: str = "") -> MCPSearchResult:
        """
        搜索并安装适合当前任务的MCP服务器
        
        Args:
            task_description: 当前任务描述
            current_available_tools: 当前可用工具列表
            reason: 为什么需要搜索新工具的原因
        """
        logger.info(f"Starting MCP search for task: {task_description[:100]}...")
        logger.info(f"Reason: {reason}")
        
        try:
            # 使用工具缺口检测器分析
            analysis = await self.tool_gap_detector.analyze_tool_sufficiency(
                task_description, current_available_tools
            )
            
            if analysis.has_sufficient_tools:
                return MCPSearchResult(
                    success=False,
                    message="分析显示当前工具已足够完成任务，无需安装新工具",
                    installed_tools=[]
                )
            
            # 使用LLM生成搜索策略而不是硬编码
            search_strategy = await self._generate_dynamic_search_strategy(
                task_description, analysis
            )
            
            if not search_strategy:
                return MCPSearchResult(
                    success=False,
                    message="无法生成有效的工具搜索策略",
                    installed_tools=[]
                )
            
            logger.info(f"搜索策略: {search_strategy['strategy_type']}")
            logger.info(f"搜索查询: {search_strategy['search_query']}")
            logger.info(f"期望能力: {search_strategy['expected_capabilities']}")
            
            # 使用动态生成的策略搜索MCP服务器
            candidates = await self.dynamic_mcp_manager.search_mcp_servers(
                query=search_strategy['search_query'], 
                capability_tags=search_strategy['expected_capabilities']
            )
            
            if not candidates:
                return MCPSearchResult(
                    success=False,
                    message="未找到符合要求的MCP服务器",
                    installed_tools=[]
                )
            
            logger.info(f"找到 {len(candidates)} 个候选MCP服务器")
            
            # 尝试安装最佳候选者
            installed_tools = []
            for i, candidate in enumerate(candidates[:3], 1):  # 最多尝试前3个
                logger.info(f"尝试安装候选者 {i}: {candidate.name}")
                
                install_result = await self.dynamic_mcp_manager.install_mcp_server(candidate)
                
                if install_result.success:
                    # 安装成功后，必须注册到工具库
                    logger.info(f"安装成功，正在注册到工具库: {candidate.name}")
                    
                    registration_result = await self.dynamic_mcp_manager.register_installed_server(
                        candidate, install_result
                    )
                    
                    if registration_result.success:
                        logger.info(f"成功安装并注册: {candidate.name} (持久化已保存)")
                        installed_tools.append({
                            "name": candidate.name,
                            "description": candidate.description,
                            "capabilities": candidate.capabilities,
                            "tags": candidate.tags,
                            "install_method": candidate.install_method,
                            "server_id": install_result.server_id
                        })
                        break  # 成功安装一个就够了
                    else:
                        logger.error(f"安装成功但注册失败: {candidate.name} - {registration_result.error}")
                        # 继续尝试下一个候选者
                else:
                    logger.warning(f"安装失败: {candidate.name} - {install_result.error_message}")
            
            if installed_tools:
                return MCPSearchResult(
                    success=True,
                    message=f"成功安装 {len(installed_tools)} 个MCP服务器工具",
                    installed_tools=installed_tools
                )
            else:
                return MCPSearchResult(
                    success=False,
                    message="所有候选MCP服务器安装均失败",
                    installed_tools=[]
                )
        
        except Exception as e:
            logger.error(f"MCP搜索和安装过程中发生错误: {e}")
            return MCPSearchResult(
                success=False,
                message=f"搜索安装失败: {str(e)}",
                installed_tools=[]
            )
    
    async def analyze_tool_needs(self, task_description: str, current_available_tools: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        分析当前任务的工具需求，如果检测到工具不足则自动触发安装
        
        Returns:
            分析结果，包括是否需要新工具、需要什么工具等
        """
        logger.info(f"Analyzing tool needs for task: {task_description[:100]}...")
        
        try:
            analysis = await self.tool_gap_detector.analyze_tool_sufficiency(
                task_description, current_available_tools
            )
            
            result = {
                "has_sufficient_tools": analysis.has_sufficient_tools,
                "overall_assessment": analysis.overall_assessment,
                "recommended_action": analysis.recommended_action,
                "tool_requirements": []
            }
            
            for req in analysis.tool_requirements:
                result["tool_requirements"].append({
                    "needed": req.needed,
                    "description": req.description,
                    "suggested_search_keywords": req.suggested_search_keywords,
                    "confidence_score": req.confidence_score,
                    "reasoning": req.reasoning
                })
            
            # 如果检测到工具不足，自动触发安装
            if not analysis.has_sufficient_tools and analysis.recommended_action == "search_for_new_tools":
                logger.info("⚡ 检测到工具不足，自动触发MCP搜索和安装...")
                
                # 自动调用搜索和安装
                install_result = await self.search_and_install_tools(
                    task_description=task_description,
                    current_available_tools=current_available_tools,
                    reason="analyze_tool_needs自动触发"
                )
                
                # 将安装结果添加到分析结果中
                result["auto_install_triggered"] = True
                result["install_result"] = {
                    "success": install_result.success,
                    "message": install_result.message,
                    "installed_tools": install_result.installed_tools
                }
                
                if install_result.success:
                    result["recommended_action"] = "auto_install_completed"
            
            return result
            
        except Exception as e:
            logger.error(f"工具需求分析失败: {e}")
            return {
                "has_sufficient_tools": False,
                "overall_assessment": f"分析失败: {str(e)}",
                "recommended_action": "error",
                "tool_requirements": [],
                "error": str(e)
            }

    async def _generate_dynamic_search_strategy(self, task_description: str, analysis) -> Optional[Dict[str, Any]]:
        """
        使用LLM动态生成搜索策略，而不是硬编码预设
        """
        try:
            # 使用LLM分析任务并生成搜索策略
            strategy_prompt = f"""
请根据以下任务描述和工具分析结果，生成一个MCP服务器搜索策略。

任务描述: {task_description}

工具分析结果:
- 工具充足性: {'足够' if analysis.has_sufficient_tools else '不足'}
- 评估: {analysis.overall_assessment}
- 推荐行动: {analysis.recommended_action}

请生成一个JSON格式的搜索策略，包含以下字段：
{{
    "strategy_type": "策略类型(如图像生成、文档处理、数据分析等)",
    "search_query": "用于搜索的查询词(英文，用空格分隔)",
    "expected_capabilities": ["期望的能力列表"],
    "reasoning": "选择这个策略的原因"
}}

要求：
1. 根据任务内容动态生成，不要使用预设模板
2. search_query应该是通用的搜索词，不要包含具体的产品名称
3. expected_capabilities应该是功能性描述，不是具体工具名称
4. 返回纯JSON格式，不要包含任何其他文字
"""
            
            # 调用LLM生成策略
            from core.llm_client import LLMClient
            llm_client = LLMClient({})
            response = await llm_client._call_api(strategy_prompt)
            
            # 解析LLM响应
            try:
                # 提取JSON部分
                import re
                json_match = re.search(r'\{.*\}', response, re.DOTALL)
                if json_match:
                    strategy_json = json_match.group()
                    strategy = json.loads(strategy_json)
                    
                    # 验证必需字段
                    required_fields = ["strategy_type", "search_query", "expected_capabilities"]
                    if all(field in strategy for field in required_fields):
                        logger.info(f"LLM生成的搜索策略: {strategy['strategy_type']}")
                        return strategy
                
                logger.warning("LLM生成的策略格式不正确，使用fallback方法")
                
            except json.JSONDecodeError:
                logger.warning("无法解析LLM生成的JSON策略，使用fallback方法")
            
            # Fallback: 基于关键词简单推断
            return self._generate_fallback_strategy(task_description)
            
        except Exception as e:
            logger.error(f"生成搜索策略失败: {e}")
            return self._generate_fallback_strategy(task_description)

    def _generate_fallback_strategy(self, task_description: str) -> Dict[str, Any]:
        """
        当LLM生成策略失败时的fallback方法
        """
        desc_lower = task_description.lower()
        
        # 基于任务描述的简单关键词匹配(仅作为fallback)
        if any(word in desc_lower for word in ['图', '图片', '图像', '生成', '画', 'image', 'generate', 'create', 'draw']):
            return {
                "strategy_type": "图像生成",
                "search_query": "image generation AI",
                "expected_capabilities": ["generate_image", "text_to_image"],
                "reasoning": "Fallback策略：检测到图像相关任务"
            }
        elif any(word in desc_lower for word in ['文档', '文件', 'pdf', 'document', 'file']):
            return {
                "strategy_type": "文档处理", 
                "search_query": "document processing",
                "expected_capabilities": ["process_document", "file_handling"],
                "reasoning": "Fallback策略：检测到文档相关任务"
            }
        elif any(word in desc_lower for word in ['数据', '分析', 'data', 'analysis', 'chart']):
            return {
                "strategy_type": "数据分析",
                "search_query": "data analysis",
                "expected_capabilities": ["analyze_data", "visualization"],
                "reasoning": "Fallback策略：检测到数据相关任务"
            }
        else:
            return {
                "strategy_type": "通用工具",
                "search_query": "general purpose tool",
                "expected_capabilities": ["general_processing"],
                "reasoning": "Fallback策略：通用任务处理"
            } 