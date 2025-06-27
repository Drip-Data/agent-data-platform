import logging
from typing import Dict, Any, List
from core.llm.prompt_builders.interfaces import IPromptBuilder

logger = logging.getLogger(__name__)

class WebPromptBuilder(IPromptBuilder):
    """构建Web操作提示"""
    def build_prompt(self, description: str, page_content: str) -> List[Dict[str, Any]]:
        """构建Web操作提示"""
        # 分析任务类型，避免重复操作
        needs_navigation = "访问" in description or "打开" in description or "导航" in description
        needs_extraction = "抓取" in description or "提取" in description or "获取" in description or "md" in description.lower()
        has_page_content = page_content and len(page_content.strip()) > 10
        
        if has_page_content and needs_extraction:
            # 如果已有页面内容且需要提取，直接提取而不重复导航
            prompt_content = f"""基于当前页面内容生成提取操作：

任务描述：{description}
页面状态：已加载，有内容
当前页面内容：
{page_content[:1000]}

⚠️ 重要：页面已经加载，请直接提取内容，不要重复导航！

请返回JSON格式的单个提取操作：
{{
  "thinking": "页面已加载，现在提取所需内容",
  "action": "browser_extract_content",
  "tool_id": "browser_use",
  "parameters": {{
    "format": "markdown"
  }}
}}

请只返回JSON对象，不要包含其他文字："""
        else:
            prompt_content = f"""根据任务描述生成浏览器操作：

任务描述：{description}

⚠️ 必需参数提醒：
- browser_navigate 需要 "url" 参数
- browser_extract_content 可选 "format" 参数
- 避免重复执行相同操作

请返回JSON格式的单个操作：
{{
  "thinking": "分析任务并选择合适的操作",
  "action": "具体操作名称",
  "tool_id": "browser_use", 
  "parameters": {{
    "必需参数": "参数值"
  }}
}}

请只返回JSON对象，不要包含其他文字："""
        return [{"role": "user", "content": prompt_content}]