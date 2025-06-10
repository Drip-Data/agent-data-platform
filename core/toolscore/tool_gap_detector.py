"""
智能工具不足检测器
使用LLM语义理解来判断当前工具是否足以完成任务
"""

import logging
import json
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

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

class SmartToolGapDetector:
    """智能工具不足检测器 - 基于LLM语义理解"""
    
    def __init__(self, llm_client):
        self.llm_client = llm_client
        logger.info("Smart Tool Gap Detector initialized with LLM-based analysis")
    
    async def analyze_tool_sufficiency(self, task_description: str, available_tools: List[Dict[str, Any]], 
                                       previous_attempts: List[Dict[str, Any]] = None) -> ToolGapAnalysis:
        """分析现有工具是否足以完成任务"""
        logger.info(f"Analyzing tool sufficiency for task: {task_description[:100]}...")
        
        # 构建分析提示
        analysis_prompt = self._build_analysis_prompt(task_description, available_tools, previous_attempts)
        
        try:
            # 使用LLM进行分析
            response = await self.llm_client._call_api(analysis_prompt)
            
            # 解析LLM响应
            analysis_result = self._parse_analysis_response(response)
            
            logger.info(f"Tool sufficiency analysis completed: {'Sufficient' if analysis_result.has_sufficient_tools else 'Insufficient'}")
            return analysis_result
            
        except Exception as e:
            logger.error(f"Error during tool sufficiency analysis: {e}")
            # 返回保守的结果
            return ToolGapAnalysis(
                has_sufficient_tools=True,  # 保守估计，避免频繁安装
                tool_requirements=[],
                overall_assessment="分析失败，假设工具充足",
                recommended_action="continue_with_existing_tools"
            )
    
    def _build_analysis_prompt(self, task_description: str, available_tools: List[Dict[str, Any]], 
                               previous_attempts: List[Dict[str, Any]] = None) -> str:
        """构建工具充足性分析提示"""
        
        # 格式化当前工具信息
        tools_info = []
        if available_tools:
            for tool in available_tools:
                capabilities = []
                tool_capabilities = tool.get('capabilities', [])
                
                if tool_capabilities:
                    for cap in tool_capabilities:
                        if isinstance(cap, dict):
                            cap_name = cap.get('name', '')
                            cap_desc = cap.get('description', '')
                            if cap_name and cap_desc:
                                capabilities.append(f"  - {cap_name}: {cap_desc}")
                            elif cap_name:
                                capabilities.append(f"  - {cap_name}")
                        else:
                            capabilities.append(f"  - {cap}")
                
                capabilities_str = "\n".join(capabilities) if capabilities else "  - 无详细能力信息"
                
                tool_info = f"""
工具名称: {tool.get('name', '未知')}
描述: {tool.get('description', '无描述')}
具体能力:
{capabilities_str}
"""
                tools_info.append(tool_info)
        
        tools_section = "\n".join(tools_info) if tools_info else "当前没有可用工具"
        
        # 格式化失败尝试信息
        failure_info = ""
        if previous_attempts:
            failures = []
            for attempt in previous_attempts[-3:]:  # 只考虑最近3次失败
                error_msg = attempt.get('error_message', '')
                observation = attempt.get('observation', '')
                action = attempt.get('action', '')
                
                failure = f"- 尝试动作: {action}"
                if error_msg:
                    failure += f"\n  错误: {error_msg}"
                if observation and observation != error_msg:
                    failure += f"\n  观察: {observation[:200]}"
                failures.append(failure)
            
            if failures:
                failure_info = f"""

=== 之前的失败尝试 ===
{chr(10).join(failures)}
"""
        
        # 先构建JSON示例模板，使用双花括号转义
        json_template = """{{
  "has_sufficient_tools": boolean,
  "reasoning": "详细说明你的分析过程：1)任务具体需要什么功能 2)现有工具能否实现 3)如果不能，缺少什么关键能力",
  "overall_assessment": "一句话总结：工具充足/需要XX类型工具",
  "tool_requirements": [
    {{
      "needed": boolean,
      "description": "具体需要什么类型的工具，要明确功能需求",
      "suggested_search_keywords": ["准确的搜索关键词", "相关技术名词"],
      "confidence_score": 0.0-1.0,
      "reasoning": "为什么确实需要这个工具的具体技术原因"
    }}
  ],
  "recommended_action": "continue_with_existing_tools" | "search_for_new_tools" | "task_impossible"
}}"""

        prompt = f"""你是一个专业的工具需求分析师，专门判断AI任务执行是否需要新工具。

你的核心原则：
1. **保守判断**：优先使用现有工具的组合来解决问题
2. **精确识别**：只有在确实缺少关键功能时才建议新工具
3. **实用导向**：优先考虑实际可获得的MCP服务器类型

=== 需要分析的任务 ===
{task_description}

=== 当前可用工具 ===
{tools_section}{failure_info}

=== 分析指导原则 ===

**明确需要新工具的情况：**
- 任务需要特定文件格式处理（如PDF生成、Excel操作、图像处理）
- 需要连接特定外部服务（如数据库、云服务、API）
- 需要专业计算能力（如机器学习、数据分析、科学计算）
- 需要特定协议支持（如SMTP邮件、FTP文件传输）

**不需要新工具的情况：**
- 可以用现有工具组合解决
- 只是参数配置或使用方式问题
- 任务过于模糊或不明确
- 需要的是逻辑优化而非新功能

**常见可用的MCP服务器类型：**
- 文件处理类：PDF操作、Excel处理、图像编辑
- 数据处理类：数据库连接、API调用、数据分析
- 通信类：邮件发送、消息推送、通知服务
- 开发工具类：代码生成、测试工具、部署工具

请严格按照以下JSON格式回答，不要添加任何解释文字：

```json
{json_template}
```

**重要提醒：**
- confidence_score > 0.7 才会触发实际搜索
- 搜索关键词要准确，避免过于宽泛
- 优先推荐经过验证的、流行的工具类型
- 如果任务不明确，选择 continue_with_existing_tools"""
        
        return prompt
    
    def _parse_analysis_response(self, response: str) -> ToolGapAnalysis:
        """增强的LLM分析响应解析器，支持多种解析策略和错误修复"""
        
        # 策略1: 标准JSON解析
        result = self._try_standard_json_parsing(response)
        if result:
            return result
        
        # 策略2: 修复常见JSON错误后解析
        result = self._try_json_repair_parsing(response)
        if result:
            return result
        
        # 策略3: 正则提取关键信息
        result = self._try_regex_extraction(response)
        if result:
            return result
        
        # 所有策略都失败，返回保守结果
        logger.error(f"All JSON parsing strategies failed for response: {response[:200]}...")
        return ToolGapAnalysis(
            has_sufficient_tools=True,
            tool_requirements=[],
            overall_assessment="响应解析失败，假设工具充足",
            recommended_action="continue_with_existing_tools"
        )
    
    def _try_standard_json_parsing(self, response: str) -> Optional[ToolGapAnalysis]:
        """策略1: 标准JSON解析"""
        try:
            response = response.strip()
            
            # 查找JSON代码块
            json_start = response.find('```json')
            if json_start != -1:
                json_start += 7  # 跳过```json
                json_end = response.find('```', json_start)
                if json_end != -1:
                    json_str = response[json_start:json_end].strip()
                else:
                    json_str = response[json_start:].strip()
            else:
                # 尝试查找花括号
                json_start = response.find('{')
                json_end = response.rfind('}')
                if json_start != -1 and json_end != -1:
                    json_str = response[json_start:json_end+1]
                else:
                    return None
            
            # 解析JSON
            data = json.loads(json_str)
            return self._build_analysis_from_data(data)
            
        except Exception as e:
            logger.debug(f"Standard JSON parsing failed: {e}")
            return None
    
    def _try_json_repair_parsing(self, response: str) -> Optional[ToolGapAnalysis]:
        """策略2: 修复常见JSON错误后解析"""
        try:
            import re
            
            # 提取JSON部分
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if not json_match:
                return None
            
            json_str = json_match.group()
            
            # 修复常见JSON错误
            json_str = self._repair_json_string(json_str)
            
            # 尝试解析修复后的JSON
            data = json.loads(json_str)
            return self._build_analysis_from_data(data)
            
        except Exception as e:
            logger.debug(f"JSON repair parsing failed: {e}")
            return None
    
    def _repair_json_string(self, json_str: str) -> str:
        """修复常见的JSON格式错误"""
        import re
        
        # 修复未转义的引号
        json_str = re.sub(r'(?<!\\)"(?=.*".*:)', '\\"', json_str)
        
        # 修复末尾缺少的引号
        json_str = re.sub(r':\s*"([^"]*)\n', r': "\1"', json_str)
        
        # 修复未关闭的字符串
        lines = json_str.split('\n')
        for i, line in enumerate(lines):
            if line.count('"') % 2 == 1 and ':' in line:
                # 如果引号数量是奇数，且包含冒号，可能是未关闭的字符串
                if not line.rstrip().endswith('"') and not line.rstrip().endswith(','):
                    lines[i] = line.rstrip() + '"'
        
        json_str = '\n'.join(lines)
        
        # 修复末尾缺少的花括号
        open_braces = json_str.count('{')
        close_braces = json_str.count('}')
        if open_braces > close_braces:
            json_str += '}' * (open_braces - close_braces)
        
        # 修复末尾缺少的方括号
        open_brackets = json_str.count('[')
        close_brackets = json_str.count(']')
        if open_brackets > close_brackets:
            json_str += ']' * (open_brackets - close_brackets)
        
        return json_str
    
    def _try_regex_extraction(self, response: str) -> Optional[ToolGapAnalysis]:
        """策略3: 使用正则表达式提取关键信息"""
        try:
            import re
            
            # 提取has_sufficient_tools
            has_sufficient_match = re.search(r'"has_sufficient_tools"\s*:\s*(true|false)', response, re.IGNORECASE)
            has_sufficient_tools = has_sufficient_match.group(1).lower() == 'true' if has_sufficient_match else True
            
            # 提取overall_assessment
            assessment_match = re.search(r'"overall_assessment"\s*:\s*"([^"]*)"', response)
            overall_assessment = assessment_match.group(1) if assessment_match else "解析失败"
            
            # 提取recommended_action
            action_match = re.search(r'"recommended_action"\s*:\s*"([^"]*)"', response)
            recommended_action = action_match.group(1) if action_match else "continue_with_existing_tools"
            
            # 修复逻辑：如果检测到工具不足，应该推荐搜索新工具
            if not has_sufficient_tools and recommended_action == "continue_with_existing_tools":
                recommended_action = "search_for_new_tools"
                logger.info("修正推荐动作：工具不足时应该搜索新工具")
            
            # 尝试提取工具需求 (简化版，不使用硬编码关键词)
            tool_requirements = []
            description_matches = re.findall(r'"description"\s*:\s*"([^"]*)"', response)
            if description_matches:
                for desc in description_matches:
                    tool_requirements.append(ToolRequirement(
                        needed=not has_sufficient_tools,
                        description=desc,
                        suggested_search_keywords=[],  # 不使用硬编码关键词，让LLM决定
                        confidence_score=0.8 if not has_sufficient_tools else 0.3,
                        reasoning="正则提取的工具需求"
                    ))
            
            logger.info(f"使用正则表达式提取成功: has_sufficient={has_sufficient_tools}, action={recommended_action}")
            
            return ToolGapAnalysis(
                has_sufficient_tools=has_sufficient_tools,
                tool_requirements=tool_requirements,
                overall_assessment=overall_assessment,
                recommended_action=recommended_action
            )
            
        except Exception as e:
            logger.debug(f"Regex extraction failed: {e}")
            return None
    
    def _extract_from_fallback(self, description: str) -> Tuple[bool, str]:
        """Fallback方法提取分析结果 - 移除硬编码关键词"""
        # 基于常见模式的简单推断，不再使用硬编码关键词
        desc_lower = description.lower()
        
        # 查找明确的充足性指示
        if any(phrase in desc_lower for phrase in ['充足', 'sufficient', '足够', '可以完成']):
            return True, "continue_with_existing_tools"
        elif any(phrase in desc_lower for phrase in ['不足', 'insufficient', '需要', '缺少', '安装']):
            return False, "search_for_new_tools"
        else:
            # 默认保守策略：如果不确定，建议搜索新工具
            return False, "search_for_new_tools"

    def _build_analysis_from_data(self, data: dict) -> ToolGapAnalysis:
        """构建工具分析结果 - 移除硬编码的预设字段"""
        # 动态提取分析数据，不依赖硬编码字段
        requirements = []
        
        # 从分析数据中提取工具需求
        if "tool_requirements" in data:
            for req_data in data["tool_requirements"]:
                requirement = ToolRequirement(
                    needed=req_data.get("needed", True),
                    description=req_data.get("description", ""),
                    suggested_search_keywords=req_data.get("suggested_search_keywords", []),
                    confidence_score=req_data.get("confidence_score", 0.5),
                    reasoning=req_data.get("reasoning", "")
                )
                requirements.append(requirement)
        
        return ToolGapAnalysis(
            has_sufficient_tools=data.get("has_sufficient_tools", False),
            overall_assessment=data.get("overall_assessment", "需要进一步分析"),
            recommended_action=data.get("recommended_action", "search_for_new_tools"),
            tool_requirements=requirements
        )
    
    async def should_trigger_mcp_search(self, task_description: str, available_tools: List[Dict[str, Any]], 
                                        previous_attempts: List[Dict[str, Any]] = None) -> Tuple[bool, ToolGapAnalysis]:
        """判断是否应该触发MCP服务器搜索"""
        
        # 进行工具充足性分析
        analysis = await self.analyze_tool_sufficiency(task_description, available_tools, previous_attempts)
        
        # 根据分析结果决定是否搜索
        should_search = (
            not analysis.has_sufficient_tools and 
            analysis.recommended_action == "search_for_new_tools" and
            len(analysis.tool_requirements) > 0
        )
        
        if should_search:
            # 过滤高置信度的工具需求
            high_confidence_requirements = [
                req for req in analysis.tool_requirements 
                if req.needed and req.confidence_score > 0.6
            ]
            
            if high_confidence_requirements:
                logger.info(f"MCP search triggered: {len(high_confidence_requirements)} high-confidence tool requirements")
                logger.info(f"Analysis: {analysis.overall_assessment}")
                return True, analysis
            else:
                logger.info("Tool requirements detected but confidence too low for MCP search")
                return False, analysis
        
        logger.info(f"MCP search not triggered: {analysis.recommended_action}")
        return False, analysis
    
    async def get_search_strategy(self, analysis: ToolGapAnalysis) -> Optional[Dict[str, Any]]:
        """基于分析结果生成搜索策略"""
        if not analysis.tool_requirements:
            return None
        
        # 选择置信度最高的工具需求
        primary_requirement = max(analysis.tool_requirements, key=lambda x: x.confidence_score)
        
        if primary_requirement.confidence_score < 0.5:
            return None
        
        search_strategy = {
            "query": primary_requirement.suggested_search_keywords[0] if primary_requirement.suggested_search_keywords else primary_requirement.description,
            "keywords": primary_requirement.suggested_search_keywords,
            "description": primary_requirement.description,
            "reasoning": primary_requirement.reasoning,
            "confidence": primary_requirement.confidence_score
        }
        
        return search_strategy


# 为了向后兼容，保留旧的类名但使用新的实现
class ToolGapDetector(SmartToolGapDetector):
    """向后兼容的工具缺口检测器"""
    
    def __init__(self, llm_client=None):
        if llm_client is None:
            # 如果没有提供LLM客户端，尝试创建一个简单的客户端
            logger.warning("No LLM client provided to ToolGapDetector, creating default client")
            from core.llm_client import LLMClient
            import os
            config = {
                'provider': 'gemini',
                'gemini_api_key': os.getenv('GEMINI_API_KEY', ''),
                'gemini_api_url': os.getenv('GEMINI_API_URL', '')
            }
            llm_client = LLMClient(config)
        
        super().__init__(llm_client)
    
    # 提供与旧接口兼容的方法
    def update_available_capabilities(self, available_tools: List[Dict[str, Any]]):
        """兼容性方法 - 新版本不需要手动更新能力"""
        pass
    
    async def detect_tool_gaps(self, task_description: str, previous_attempts: List[Dict[str, Any]] = None):
        """兼容性方法 - 映射到新的分析方法"""
        # 这里需要获取可用工具列表，但旧接口没有提供
        # 返回一个简单的结果结构
        class LegacyResult:
            def __init__(self, has_gaps, suggestion):
                self.has_gaps = has_gaps
                self.suggestion = suggestion
                self.detected_gaps = []
                self.missing_capabilities = []
        
        return LegacyResult(False, "请使用新的analyze_tool_sufficiency方法") 