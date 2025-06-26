import logging
from typing import Dict, Any

from core.llm.response_parsers.interfaces import IResponseParser

logger = logging.getLogger(__name__)

class CodeResponseParser(IResponseParser):
    """
    用于解析LLM生成的代码响应的解析器。
    """

    def parse_response(self, response: str, **kwargs) -> Dict[str, Any]:
        """
        从LLM的原始字符串响应中提取代码。
        
        Args:
            response (str): LLM的原始字符串响应。
            **kwargs: 额外的参数，例如语言，可能用于特定解析逻辑。

        Returns:
            Dict[str, Any]: 包含提取代码的字典，键为 'code'。
        """
        language = kwargs.get('language', 'python')
        logger.info(f"🔍 从LLM响应中提取 {language} 代码 (长度: {len(response)})")
        
        # 这里需要实现从响应中提取代码的逻辑
        # 假设LLM直接返回代码字符串，或者代码被markdown代码块包裹
        
        # 尝试从markdown代码块中提取
        code_match = None
        if language:
            code_match = re.search(rf'```{language}\s*\n(.*?)\n```', response, re.DOTALL)
        if not code_match:
            code_match = re.search(r'```(?:\w+)?\s*\n(.*?)\n```', response, re.DOTALL)
        
        if code_match:
            code = code_match.group(1).strip()
            logger.info("✅ 成功从代码块中提取代码")
        else:
            code = response.strip()
            logger.warning("⚠️ 未能从代码块中提取代码，将整个响应作为代码返回")

        # 提取思考过程
        thinking_match = re.search(r'==== 思考过程 ====\s*\n(.*?)\n==== 代码实现 ====', response, re.DOTALL)
        thinking = ""
        if thinking_match:
            thinking = thinking_match.group(1).strip()
            logger.info("✅ 成功提取思考过程")
        else:
            logger.warning("⚠️ 未能提取思考过程")

        return {
            "code": code,
            "thinking": thinking,
            "success": True
        }

# 导入re模块，因为在类内部使用
import re