"""
智能工具缺口检测器 - 精简版
基于LLM语义理解的工具充足性分析，无硬编码规则
"""

import logging
import json
import re
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class ToolRequirement:
    """工具需求分析结果"""
    needed: bool
    description: str
    suggested_search_keywords: List[str]
    confidence_score: float
    reasoning: str

@dataclass
class ToolGapAnalysis:
    """工具缺口分析结果"""
    has_sufficient_tools: bool
    tool_requirements: List[ToolRequirement]
    overall_assessment: str
    recommended_action: str


class ToolGapDetector:
    """智能工具缺口检测器 - 精简统一版本"""
    
    def __init__(self, llm_client=None, cache_manager=None):
        self.llm_client = llm_client
        self.cache_manager = cache_manager
        logger.info("智能工具缺口检测器初始化 - 统一版本")
    
    async def analyze_tool_sufficiency(self, task_description: str, available_tools: List[Dict[str, Any]], 
                                       previous_attempts: List[Dict[str, Any]] = None) -> ToolGapAnalysis:
        """分析工具充足性 - 智能语义分析"""
        
        # 尝试从缓存获取
        if self.cache_manager:
            cache_key = f"tool_gap:{hash(task_description + str(len(available_tools)))}"
            cached_result = await self.cache_manager.get_cached_result(cache_key)
            if cached_result:
                logger.info("使用缓存的工具充足性分析结果")
                return self._build_analysis_from_cached_data(cached_result)
        
        # LLM分析
        if self.llm_client:
            try:
                prompt = self._build_analysis_prompt(task_description, available_tools, previous_attempts)
                # Fix: Convert prompt string to messages format
                messages = [{"role": "user", "content": prompt}]
                response = await self.llm_client._call_api(messages)
                analysis = self._parse_analysis_response(response)
                
                # 缓存结果
                if self.cache_manager and analysis:
                    await self.cache_manager.cache_search_result(cache_key, {
                        "has_sufficient_tools": analysis.has_sufficient_tools,
                        "tool_requirements": [
                            {
                                "needed": req.needed,
                                "description": req.description,
                                "suggested_search_keywords": req.suggested_search_keywords,
                                "confidence_score": req.confidence_score,
                                "reasoning": req.reasoning
                            } for req in analysis.tool_requirements
                        ],
                        "overall_assessment": analysis.overall_assessment,
                        "recommended_action": analysis.recommended_action
                    })
                
                if analysis:
                    return analysis
                    
            except Exception as e:
                logger.warning(f"LLM分析失败，使用备用方法: {e}")
        
        # 备用分析方法
        return await self._rule_based_analysis(task_description, available_tools, previous_attempts)
    
    def _build_analysis_prompt(self, task_description: str, available_tools: List[Dict[str, Any]], 
                               previous_attempts: List[Dict[str, Any]] = None) -> str:
        """构建分析提示词 - 专注语义理解"""
        
        tools_description = "\n".join([
            f"- {tool.get('name', tool.get('tool_id', 'Unknown'))}: {tool.get('description', '')}"
            for tool in available_tools[:20]  # 限制工具数量避免提示词过长
        ]) if available_tools else "无可用工具"
        
        failures_context = ""
        if previous_attempts:
            failures_context = f"\n\n之前的尝试记录：\n" + "\n".join([
                f"- {attempt.get('error', '执行失败')}" for attempt in previous_attempts[-3:]
            ])
        
        prompt = f"""
分析任务是否需要额外工具支持。

任务描述: {task_description}

当前可用工具:
{tools_description}
{failures_context}

请分析是否需要额外工具，返回JSON格式：
{{
    "has_sufficient_tools": boolean,
    "overall_assessment": "详细评估",
    "recommended_action": "continue_with_existing_tools" | "search_for_new_tools",
    "tool_requirements": [
        {{
            "needed": boolean,
            "description": "需要的功能描述",
            "suggested_search_keywords": ["关键词1", "关键词2"],
            "confidence_score": 0.0-1.0,
            "reasoning": "推理过程"
        }}
    ]
}}

重要：只返回JSON，不要其他文字。
"""
        return prompt
    
    async def _rule_based_analysis(self, task_description: str, available_tools: List[Dict[str, Any]], 
                                   previous_attempts: List[Dict[str, Any]] = None) -> ToolGapAnalysis:
        """基于规则的备用分析方法"""
        
        desc_lower = task_description.lower()
        
        # 简单的语义分析
        has_sufficient, action = self._extract_from_fallback(task_description)
        
        # 基于失败历史调整判断
        if previous_attempts and len(previous_attempts) >= 2:
            has_sufficient = False
            action = "search_for_new_tools"
        
        requirements = []
        if not has_sufficient:
            requirements.append(ToolRequirement(
                needed=True,
                description=f"完成任务所需的工具: {task_description[:100]}...",
                suggested_search_keywords=self._extract_keywords_from_description(task_description),
                confidence_score=0.7,
                reasoning="基于规则的分析判断需要额外工具"
            ))
        
        return ToolGapAnalysis(
            has_sufficient_tools=has_sufficient,
            tool_requirements=requirements,
            overall_assessment="基于规则的充足性分析",
            recommended_action=action
        )
    
    def _extract_keywords_from_description(self, description: str) -> List[str]:
        """从描述中提取关键词"""
        # 简单的关键词提取
        words = re.findall(r'\w+', description.lower())
        keywords = [word for word in words if len(word) > 3]
        return keywords[:5]  # 最多5个关键词
    
    def _parse_analysis_response(self, response: str) -> ToolGapAnalysis:
        """解析LLM响应"""
        # 标准JSON解析
        result = self._try_standard_json_parsing(response)
        if result:
            return result
        
        # JSON修复解析
        result = self._try_json_repair_parsing(response)
        if result:
            return result
        
        # 正则表达式提取
        result = self._try_regex_extraction(response)
        if result:
            return result
        
        # 默认响应
        logger.warning("所有解析方法都失败，返回默认分析结果")
        return ToolGapAnalysis(
            has_sufficient_tools=True,
            tool_requirements=[],
            overall_assessment="解析失败，假设工具充足",
            recommended_action="continue_with_existing_tools"
        )
    
    def _try_standard_json_parsing(self, response: str) -> Optional[ToolGapAnalysis]:
        """标准JSON解析"""
        try:
            # 清理响应文本
            cleaned_response = response.strip()
            if cleaned_response.startswith('```json'):
                cleaned_response = cleaned_response[7:]
            if cleaned_response.endswith('```'):
                cleaned_response = cleaned_response[:-3]
            cleaned_response = cleaned_response.strip()
            
            data = json.loads(cleaned_response)
            return self._build_analysis_from_data(data)
            
        except json.JSONDecodeError:
            return None
    
    def _try_json_repair_parsing(self, response: str) -> Optional[ToolGapAnalysis]:
        """JSON修复解析"""
        try:
            repaired = self._repair_json_string(response)
            data = json.loads(repaired)
            return self._build_analysis_from_data(data)
        except:
            return None
    
    def _repair_json_string(self, json_str: str) -> str:
        """简单的JSON修复"""
        # 移除多余的文本
        start_idx = json_str.find('{')
        end_idx = json_str.rfind('}')
        if start_idx != -1 and end_idx != -1:
            json_str = json_str[start_idx:end_idx + 1]
        
        # 基本清理
        json_str = re.sub(r',\s*}', '}', json_str)  # 移除多余逗号
        json_str = re.sub(r',\s*]', ']', json_str)
        
        return json_str
    
    def _try_regex_extraction(self, response: str) -> Optional[ToolGapAnalysis]:
        """正则表达式提取"""
        try:
            # 提取关键信息
            has_sufficient_match = re.search(r'"has_sufficient_tools"\s*:\s*(true|false)', response)
            has_sufficient_tools = has_sufficient_match.group(1) == 'true' if has_sufficient_match else True
            
            action_match = re.search(r'"recommended_action"\s*:\s*"([^"]*)"', response)
            recommended_action = action_match.group(1) if action_match else "continue_with_existing_tools"
            
            assessment_match = re.search(r'"overall_assessment"\s*:\s*"([^"]*)"', response)
            overall_assessment = assessment_match.group(1) if assessment_match else "正则提取的分析结果"
            
            return ToolGapAnalysis(
                has_sufficient_tools=has_sufficient_tools,
                tool_requirements=[],
                overall_assessment=overall_assessment,
                recommended_action=recommended_action
            )
            
        except Exception:
            return None
    
    def _extract_from_fallback(self, description: str) -> Tuple[bool, str]:
        """语义分析备用方法 - 改进版本以减少误报"""
        desc_lower = description.lower()
        
        # 基础计算任务 - 通常可以用现有工具完成
        basic_compute_indicators = [
            '计算', '1+1', '2+2', '3*3', '求和', '乘积', '算术', '数学运算', 
            'print(', 'execute', 'microsandbox', 'python', '代码执行'
        ]
        
        # 复杂需求指示器 - 可能需要新工具
        complex_need_indicators = [
            '网络爬虫', '数据库', '图像处理', '机器学习', '自然语言处理',
            '文件上传', 'api调用', '第三方服务', '专业软件'
        ]
        
        # 检查是否是基础计算任务
        is_basic_compute = any(indicator in desc_lower for indicator in basic_compute_indicators)
        has_complex_needs = any(indicator in desc_lower for indicator in complex_need_indicators)
        
        # 如果是基础计算任务，认为工具充足
        if is_basic_compute and not has_complex_needs:
            return True, "continue_with_existing_tools"
        
        # 如果有复杂需求，可能需要新工具
        if has_complex_needs:
            return False, "search_for_new_tools"
        
        # 默认情况下，认为现有工具足够
        return True, "continue_with_existing_tools"
    
    def _build_analysis_from_data(self, data: dict) -> ToolGapAnalysis:
        """从数据构建分析结果"""
        requirements = []
        
        if "tool_requirements" in data:
            for req_data in data["tool_requirements"]:
                requirement = ToolRequirement(
                    needed=req_data.get("needed", False),
                    description=req_data.get("description", ""),
                    suggested_search_keywords=req_data.get("suggested_search_keywords", []),
                    confidence_score=req_data.get("confidence_score", 0.0),
                    reasoning=req_data.get("reasoning", "")
                )
                requirements.append(requirement)
        
        has_sufficient = data.get("has_sufficient_tools", True)
        assessment = data.get("overall_assessment", "分析完成")
        action = data.get("recommended_action", "continue_with_existing_tools")
        
        return ToolGapAnalysis(
            has_sufficient_tools=has_sufficient,
            overall_assessment=assessment,
            recommended_action=action,
            tool_requirements=requirements
        )
    
    def _build_analysis_from_cached_data(self, cached_data: dict) -> ToolGapAnalysis:
        """从缓存数据构建分析结果"""
        return self._build_analysis_from_data(cached_data)
    
    async def should_trigger_mcp_search(self, task_description: str, available_tools: List[Dict[str, Any]], 
                                        previous_attempts: List[Dict[str, Any]] = None) -> Tuple[bool, ToolGapAnalysis]:
        """判断是否应该触发MCP服务器搜索"""
        
        analysis = await self.analyze_tool_sufficiency(task_description, available_tools, previous_attempts)
        
        should_search = (
            not analysis.has_sufficient_tools and 
            analysis.recommended_action == "search_for_new_tools" and
            len(analysis.tool_requirements) > 0
        )
        
        if should_search:
            high_confidence_requirements = [
                req for req in analysis.tool_requirements 
                if req.needed and req.confidence_score > 0.6
            ]
            
            if high_confidence_requirements:
                logger.info(f"MCP搜索触发: {len(high_confidence_requirements)} 个高置信度需求")
                return True, analysis
            else:
                logger.info("检测到工具需求但置信度不足")
                return False, analysis
        
        return False, analysis
    
    async def get_search_strategy(self, analysis: ToolGapAnalysis) -> Optional[Dict[str, Any]]:
        """基于分析结果生成搜索策略"""
        if not analysis.tool_requirements:
            return None
        
        primary_requirement = max(analysis.tool_requirements, key=lambda x: x.confidence_score)
        
        if primary_requirement.confidence_score < 0.5:
            return None
        
        return {
            "query": primary_requirement.suggested_search_keywords[0] if primary_requirement.suggested_search_keywords else primary_requirement.description,
            "keywords": primary_requirement.suggested_search_keywords,
            "description": primary_requirement.description,
            "reasoning": primary_requirement.reasoning,
            "confidence": primary_requirement.confidence_score
        } 