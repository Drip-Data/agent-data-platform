import json
import logging
from typing import Dict, Any, List

from core.llm.response_parsers.interfaces import IResponseParser

logger = logging.getLogger(__name__)

class WebActionsResponseParser(IResponseParser):
    """
    用于解析LLM生成的Web操作响应的解析器。
    """

    def parse_response(self, response: str, **kwargs) -> List[Dict]:
        """
        从LLM的原始字符串响应中提取Web操作步骤。
        
        Args:
            response (str): LLM的原始字符串响应。
            **kwargs: 额外的参数，例如任务描述，可能用于备用逻辑。

        Returns:
            List[Dict]: 包含Web操作步骤的列表。
        """
        logger.info(f"🔍 从LLM响应中提取Web操作 (长度: {len(response)})")
        
        try:
            # 尝试直接解析JSON数组
            actions = json.loads(response)
            if isinstance(actions, list) and all(isinstance(item, dict) for item in actions):
                logger.info("✅ 成功解析Web操作JSON数组")
                return actions
            else:
                logger.warning("⚠️ 解析的JSON不是有效的Web操作列表，尝试备用方法")
                return self._fallback_web_actions(kwargs.get('description', ''))
        except json.JSONDecodeError as e:
            logger.warning(f"❌ JSON解析失败: {e}, 尝试备用方法")
            return self._fallback_web_actions(kwargs.get('description', ''))
        except Exception as e:
            logger.error(f"❌ 提取Web操作过程中出错: {e}, 尝试备用方法")
            return self._fallback_web_actions(kwargs.get('description', ''))
    
    def _fallback_web_actions(self, description: str) -> List[Dict]:
        """
        生成备用Web操作步骤。
        当LLM未能生成有效Web操作时，提供一个默认或简单的操作。
        """
        logger.info(f"🔄 生成备用Web操作步骤，基于描述: {description[:50]}...")
        # 这里可以根据description生成更智能的备用操作
        # 例如，如果描述包含“搜索”，可以生成一个搜索操作
        if "search" in description.lower():
            return [
                {"action": "fill", "selector": "input[type='search'], #search, .search-box", "value": "default search query", "description": "Fallback: Fill search box"},
                {"action": "click", "selector": "button[type='submit'], .search-button", "description": "Fallback: Click search button"}
            ]
        return [
            {"action": "navigate", "url": "about:blank", "description": "Fallback: Navigate to a blank page due to parsing error"}
        ]