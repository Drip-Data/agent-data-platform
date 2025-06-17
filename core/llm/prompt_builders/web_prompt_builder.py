import logging
from typing import Dict, Any, List
from core.llm.prompt_builders.interfaces import IPromptBuilder

logger = logging.getLogger(__name__)

class WebPromptBuilder(IPromptBuilder):
    """构建Web操作提示"""
    def build_prompt(self, description: str, page_content: str) -> List[Dict[str, Any]]:
        """构建Web操作提示"""
        prompt_content = f"""请根据以下描述生成Web操作步骤：

任务描述：{description}

当前页面内容：
{page_content[:1000] if page_content else '无'}

请返回JSON格式的操作步骤列表，每个步骤包含：
- action: 操作类型（navigate, click, fill, wait等）
- selector: CSS选择器（如果需要）
- value: 输入值（如果需要）
- description: 操作描述

示例格式：
[
  {{"action": "navigate", "url": "https://example.com", "description": "打开网站"}},
  {{"action": "fill", "selector": "#search", "value": "搜索内容", "description": "填写搜索框"}},
  {{"action": "click", "selector": "button[type=submit]", "description": "点击搜索按钮"}}
]

请只返回JSON数组，不要包含其他文字："""
        return [{"role": "user", "content": prompt_content}]