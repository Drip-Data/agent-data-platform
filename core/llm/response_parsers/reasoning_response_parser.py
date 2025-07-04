import logging
import re
from typing import Dict, Any, Optional

from core.llm.response_parsers.interfaces import IResponseParser

logger = logging.getLogger(__name__)


class ReasoningResponseParser(IResponseParser):
    """
    一个专注、简单的响应解析器，用于支持多轮“停止并执行”的循环。
    它的唯一目标是从LLM的响应中找到第一个有效动作。
    """

    def parse_response(self, response: str, **kwargs) -> Optional[Dict[str, Any]]:
        """
        解析LLM的响应，查找第一个工具调用或最终答案。
        这是防止幻觉的关键，因为它强制执行一个“停止并执行”的循环。

        Args:
            response: LLM的原始字符串响应。

        Returns:
            一个包含下一个动作信息的字典，如果找不到有效动作则返回None。
        """
        logger.info(f"🔍 Parsing response for next action (length: {len(response)})...")
        
        # 正则表达式，用于查找<think>块和紧随其后的第一个工具或答案标签。
        # 这确保我们捕获与即将执行的动作直接相关的思考过程。
        pattern = re.compile(
            r"(<think>.*?</think>)?\s*(<(microsandbox|deepsearch|browser_use|search_tool|answer)>(.*?)</\3>)",
            re.DOTALL
        )

        match = pattern.search(response)

        if not match:
            logger.warning("No valid tool call or answer tag found in the response.")
            return None

        # 提取思考过程和完整的动作标签
        thinking = (match.group(1) or "").strip()
        full_action_tag = match.group(2)
        tool_name = match.group(3)
        tool_input = (match.group(4) or "").strip()

        logger.info(f"✅ Action found: <{tool_name}>")

        if tool_name == "answer":
            return {
                "type": "answer",
                "thinking": thinking,
                "content": tool_input,
                "full_tag": full_action_tag
            }
        else:
            # 这是一个工具调用
            return {
                "type": "tool_call",
                "thinking": thinking,
                "tool_name": tool_name,
                "tool_input": tool_input,
                "full_tag": full_action_tag
            }

    def set_tool_schema_manager(self, tool_schema_manager):
        """保持与旧接口的兼容性，但在此实现中未使用。"""
        pass
