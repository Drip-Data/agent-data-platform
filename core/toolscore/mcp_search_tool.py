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
        """分析工具需求，不执行安装"""
        logger.info(f"分析任务的工具需求: {task_description[:100]}...")
        
        try:
            # 使用工具缺口检测器
            analysis = await self.tool_gap_detector.analyze_tool_sufficiency(
                task_description, current_available_tools
            )
            
            # 构建兼容的结果格式
            if hasattr(analysis, 'has_sufficient_tools'):
                has_sufficient = analysis.has_sufficient_tools
                overall_assessment = analysis.overall_assessment
                recommended_action = analysis.recommended_action if hasattr(analysis, 'recommended_action') else None
                
                # 提取工具需求
                tool_requirements = []
                if hasattr(analysis, 'tool_requirements'):
            for req in analysis.tool_requirements:
                        if hasattr(req, 'needed') and req.needed:
                            tool_requirements.append({
                    "description": req.description,
                                "suggested_keywords": req.suggested_search_keywords,
                                "confidence": req.confidence_score
                            })
                
                result = {
                    "has_sufficient_tools": has_sufficient,
                    "overall_assessment": overall_assessment,
                    "recommended_action": recommended_action or ("continue_with_existing_tools" if has_sufficient else "search_for_new_tools"),
                    "tool_requirements": tool_requirements
                }
            else:
                # 兼容字典格式
                result = {
                    "has_sufficient_tools": analysis.get("has_sufficient_tools", False),
                    "overall_assessment": analysis.get("overall_assessment", "Unknown analysis result"),
                    "recommended_action": analysis.get("recommended_action", "search_for_new_tools"),
                    "tool_requirements": analysis.get("tool_requirements", [])
                }
            
            # 添加智能工具推荐
            if not result["has_sufficient_tools"]:
                recommended_tools = await self.find_matching_tools_from_analysis(
                    task_description, 
                    result.get("tool_requirements", [])
                )
                result["recommended_mcp_tools"] = recommended_tools
            
            logger.info(f"工具需求分析完成: 充足性={result['has_sufficient_tools']}, 推荐={result.get('recommended_action')}")
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

    async def find_matching_tools_from_analysis(self, task_description: str, 
                                              tool_requirements: List[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """基于任务需求分析结果，在mcp_tools.json中智能匹配合适的MCP工具"""
        logger.info(f"🔍 基于需求分析在mcp_tools.json中查找匹配工具...")
        
        try:
            # 1. 使用LLM分析任务需求
            from core.llm_client import LLMClient
            llm_client = LLMClient({})
            task_analysis = await llm_client.analyze_task_requirements(task_description)
            
            logger.info(f"📋 任务分析结果: {task_analysis}")
            
            # 2. 在mcp_tools.json中搜索匹配工具
            matching_tools = await self._search_tools_by_capabilities(
                required_capabilities=task_analysis.get("required_capabilities", []),
                tools_needed=task_analysis.get("tools_needed", []),
                key_features=task_analysis.get("key_features", []),
                task_type=task_analysis.get("task_type", "unknown")
            )
            
            # 3. 根据匹配度排序
            ranked_tools = await self._rank_tools_by_relevance(
                matching_tools, 
                task_description, 
                task_analysis
            )
            
            logger.info(f"✅ 找到 {len(ranked_tools)} 个匹配的MCP工具")
            for tool in ranked_tools[:3]:  # 显示前3个最匹配的工具
                logger.info(f"   - {tool['name']}: {tool.get('match_score', 0):.2f} 分")
            
            return ranked_tools
            
        except Exception as e:
            logger.error(f"智能工具匹配失败: {e}")
            return []

    async def _search_tools_by_capabilities(self, required_capabilities: List[str], 
                                          tools_needed: List[str], 
                                          key_features: List[str],
                                          task_type: str) -> List[Dict[str, Any]]:
        """在mcp_tools.json中基于能力需求搜索工具"""
        matching_tools = []
        
        try:
            # 加载mcp_tools.json
            mcp_tools_path = await self._find_mcp_tools_json()
            if not mcp_tools_path:
                logger.error("❌ 无法找到mcp_tools.json文件")
                return []
                
            with open(mcp_tools_path, 'r', encoding='utf-8') as f:
                tools_data = json.load(f)
            
            logger.info(f"📚 加载了 {len(tools_data)} 个MCP工具进行匹配")
            
            # 遍历所有工具进行匹配
            for tool in tools_data:
                match_score = self._calculate_tool_match_score(
                    tool, required_capabilities, tools_needed, key_features, task_type
                )
                
                if match_score > 0.3:  # 只保留匹配度>30%的工具
                    tool_info = {
                        "name": tool.get("name", ""),
                        "description": tool.get("description", ""),
                        "url": tool.get("url", ""),
                        "summary": tool.get("summary", ""),
                        "tools": tool.get("tools", []),
                        "match_score": match_score,
                        "match_reasons": self._get_match_reasons(
                            tool, required_capabilities, tools_needed, key_features
                        )
                    }
                    matching_tools.append(tool_info)
            
            return matching_tools
            
        except Exception as e:
            logger.error(f"搜索工具时出错: {e}")
            return []

    def _calculate_tool_match_score(self, tool: Dict[str, Any], 
                                   required_capabilities: List[str],
                                   tools_needed: List[str], 
                                   key_features: List[str],
                                   task_type: str) -> float:
        """计算工具与需求的匹配分数 (0-1之间)"""
        total_score = 0.0
        max_score = 0.0
        
        tool_name = tool.get("name", "").lower()
        tool_desc = tool.get("description", "").lower()
        tool_summary = tool.get("summary", "").lower()
        tool_tools = tool.get("tools", [])
        
        # 1. 能力匹配 (权重: 40%)
        capability_score = 0.0
        capability_weight = 0.4
        max_score += capability_weight
        
        if required_capabilities:
            matches = 0
            for capability in required_capabilities:
                capability_lower = capability.lower()
                # 检查能力是否在工具名称、描述或工具列表中出现
                if (capability_lower in tool_name or 
                    capability_lower in tool_desc or 
                    capability_lower in tool_summary or
                    any(capability_lower in str(t).lower() for t in tool_tools)):
                    matches += 1
            capability_score = (matches / len(required_capabilities)) * capability_weight
        
        total_score += capability_score
        
        # 2. 工具类型匹配 (权重: 30%)
        tool_type_score = 0.0
        tool_type_weight = 0.3
        max_score += tool_type_weight
        
        if tools_needed:
            matches = 0
            for tool_needed in tools_needed:
                tool_needed_lower = tool_needed.lower()
                if (tool_needed_lower in tool_name or 
                    tool_needed_lower in tool_desc or 
                    tool_needed_lower in tool_summary):
                    matches += 1
            tool_type_score = (matches / len(tools_needed)) * tool_type_weight
        
        total_score += tool_type_score
        
        # 3. 关键特征匹配 (权重: 20%)
        feature_score = 0.0
        feature_weight = 0.2
        max_score += feature_weight
        
        if key_features:
            matches = 0
            for feature in key_features:
                feature_lower = feature.lower()
                if (feature_lower in tool_name or 
                    feature_lower in tool_desc or 
                    feature_lower in tool_summary):
                    matches += 1
            feature_score = (matches / len(key_features)) * feature_weight
        
        total_score += feature_score
        
        # 4. 任务类型匹配 (权重: 10%)
        task_type_score = 0.0
        task_type_weight = 0.1
        max_score += task_type_weight
        
        task_type_keywords = {
            "image": ["image", "picture", "visual", "photo", "graphic", "art", "generate"],
            "web": ["web", "browser", "scraping", "crawl", "http", "api", "search"],
            "code": ["python", "code", "execute", "programming", "script", "development"],
            "data": ["data", "analysis", "statistics", "csv", "excel", "database"],
            "file": ["file", "document", "pdf", "convert", "processing", "format"],
            "communication": ["email", "message", "notification", "send", "api", "webhook"]
        }
        
        if task_type in task_type_keywords:
            keywords = task_type_keywords[task_type]
            matches = sum(1 for keyword in keywords 
                         if keyword in tool_name or keyword in tool_desc or keyword in tool_summary)
            if matches > 0:
                task_type_score = min(matches / len(keywords), 1.0) * task_type_weight
        
        total_score += task_type_score
        
        # 归一化分数
        final_score = total_score / max_score if max_score > 0 else 0.0
        return min(final_score, 1.0)

    def _get_match_reasons(self, tool: Dict[str, Any], 
                          required_capabilities: List[str],
                          tools_needed: List[str], 
                          key_features: List[str]) -> List[str]:
        """获取匹配原因的详细说明"""
        reasons = []
        
        tool_name = tool.get("name", "").lower()
        tool_desc = tool.get("description", "").lower()
        tool_summary = tool.get("summary", "").lower()
        
        # 检查能力匹配
        for capability in required_capabilities:
            if capability.lower() in tool_name or capability.lower() in tool_desc:
                reasons.append(f"支持 {capability} 能力")
        
        # 检查工具类型匹配
        for tool_needed in tools_needed:
            if tool_needed.lower() in tool_name or tool_needed.lower() in tool_desc:
                reasons.append(f"提供 {tool_needed}")
        
        # 检查关键特征匹配
        for feature in key_features:
            if feature.lower() in tool_name or feature.lower() in tool_desc:
                reasons.append(f"匹配特征: {feature}")
        
        return reasons if reasons else ["基础匹配"]

    async def _rank_tools_by_relevance(self, matching_tools: List[Dict[str, Any]], 
                                     task_description: str,
                                     task_analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
        """根据相关度对工具进行排序"""
        # 按匹配分数降序排序
        ranked_tools = sorted(matching_tools, key=lambda x: x.get("match_score", 0), reverse=True)
        
        # 限制返回数量，避免过多结果
        return ranked_tools[:10]

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
    
    async def _find_mcp_tools_json(self) -> Optional[str]:
        """查找mcp_tools.json文件"""
        import os
        
        # 可能的文件位置
        possible_paths = [
            "/app/mcp_tools.json",  # Docker容器内位置
            "mcp_tools.json",  # 当前目录
            "../mcp_tools.json",  # 上级目录
            "/Users/muz1lee/PycharmProjects/DataGenerator/agent-data-platform/mcp_tools.json",  # 项目根目录
            "/Users/muz1lee/Downloads/mcp_tools.json",  # 用户下载目录
            "data/mcp_tools.json",  # 项目data目录
            os.path.expanduser("~/Downloads/mcp_tools.json"),  # 用户下载目录
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                logger.info(f"找到MCP数据库文件: {path}")
                return path
        
        logger.warning("未找到mcp_tools.json文件")
        return None 