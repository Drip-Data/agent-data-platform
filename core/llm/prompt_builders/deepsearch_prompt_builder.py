import logging
from typing import Dict, Any, List, Optional
from core.llm.prompt_builders.interfaces import IPromptBuilder

logger = logging.getLogger(__name__)

class DeepSearchPromptBuilder(IPromptBuilder):
    """构建深度搜索提示词，判断何时使用deepsearch工具"""
    
    def build_prompt(self, task_description: str) -> List[Dict[str, Any]]:
        """实现基础build_prompt方法"""
        return self.build_deepsearch_decision_prompt(task_description)
    
    def build_deepsearch_decision_prompt(self, task_description: str, task_analysis: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """构建决定是否需要深度搜索的提示词"""
        
        analysis_context = ""
        if task_analysis:
            analysis_context = f"""
基于任务分析结果：
- 任务类型: {task_analysis.get('task_type', 'unknown')}
- 核心能力需求: {', '.join(task_analysis.get('required_capabilities', []))}
- 工具需求: {', '.join(task_analysis.get('tools_needed', []))}
"""

        prompt_content = f"""你是一个专业的工具选择助手。请分析以下任务是否需要使用专业级深度搜索工具（deepsearch）。

任务描述: {task_description}

{analysis_context}

**Deepsearch工具特点：**
- 基于LangGraph的多轮迭代搜索代理
- 执行专业级深度调研，获取详细、准确的信息
- 适合需要全面分析、对比研究、专业见解的任务
- 会进行多轮搜索优化，提供带引用的专业报告
- 比普通浏览器搜索更深入、更全面

**何时使用Deepsearch：**
✅ 需要详细的行业分析、市场调研
✅ 需要比较多个方案、产品、技术
✅ 需要最新的专业信息和趋势分析
✅ 需要深入了解某个领域的发展现状
✅ 普通搜索无法满足的复杂调研需求
✅ 需要专业级报告和引用来源

**何时不使用Deepsearch：**
❌ 简单的事实性查询（如"今天天气"）
❌ 已知信息的确认
❌ 不需要深度分析的快速问答
❌ 主要是代码、计算、文件处理任务
❌ 实时操作类任务（如网页操作）

请分析这个任务并返回JSON格式的决策：

{{
  "use_deepsearch": true/false,
  "search_type": "comprehensive_research|quick_research|research",
  "reason": "详细说明为什么需要/不需要deepsearch",
  "alternative_tools": ["如果不使用deepsearch，建议的替代工具"],
  "search_query": "如果使用deepsearch，优化后的搜索问题",
  "topic_focus": "可选：如果有特定关注点，在此说明",
  "confidence": 0.9
}}

要求：
- 严格按照JSON格式返回
- 准确判断是否真正需要深度搜索
- 不要过度使用deepsearch工具
- 优化搜索问题以获得最佳结果"""
        
        return [{"role": "user", "content": prompt_content}]
    
    def build_deepsearch_optimization_prompt(self, original_question: str, context: Optional[str] = None) -> List[Dict[str, Any]]:
        """构建优化deepsearch查询的提示词"""
        
        context_section = ""
        if context:
            context_section = f"\n相关上下文：\n{context}\n"

        prompt_content = f"""请优化以下问题，使其更适合专业级深度搜索工具进行调研。

原始问题: {original_question}{context_section}

优化要求：
1. 使问题更加具体和聚焦
2. 明确调研的关键维度和要点
3. 适合多轮搜索和深度分析
4. 有助于获得专业、全面的答案

请返回JSON格式的优化结果：

{{
  "optimized_question": "优化后的问题",
  "key_aspects": ["关键调研维度1", "关键调研维度2", "..."],
  "search_strategy": "建议的搜索策略",
  "expected_depth": "expected_analysis_depth",
  "topic_focus": "可选的特定关注点"
}}

严格按照JSON格式返回，不包含其他文字："""
        
        return [{"role": "user", "content": prompt_content}]
    
    def build_search_result_analysis_prompt(self, search_results: Dict[str, Any], original_task: str) -> List[Dict[str, Any]]:
        """构建分析搜索结果的提示词"""
        
        answer = search_results.get('answer', '')
        sources = search_results.get('sources', [])
        query_count = search_results.get('query_count', 0)
        research_loops = search_results.get('research_loops', 0)
        
        sources_text = ""
        if sources:
            sources_text = "\n参考来源：\n" + "\n".join([f"- {source.get('value', 'N/A')}" for source in sources[:5]])

        prompt_content = f"""请分析以下深度搜索结果，并提供总结和后续建议。

原始任务: {original_task}

搜索结果摘要：
- 执行了 {query_count} 次搜索查询
- 完成了 {research_loops} 轮研究循环
{sources_text}

搜索答案：
{answer}

请提供分析和建议：

{{
  "result_quality": "excellent|good|fair|poor",
  "completeness": "是否完全回答了原始问题",
  "key_insights": ["从搜索结果中提取的关键洞察"],
  "follow_up_actions": ["基于结果建议的后续行动"],
  "additional_research_needed": true/false,
  "additional_research_topics": ["如果需要，建议进一步研究的主题"],
  "summary": "对搜索结果的简洁总结"
}}

严格按照JSON格式返回："""
        
        return [{"role": "user", "content": prompt_content}]