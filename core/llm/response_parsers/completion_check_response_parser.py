import json
import logging
from typing import Dict, Any

from core.llm.response_parsers.interfaces import IResponseParser

logger = logging.getLogger(__name__)

class CompletionCheckResponseParser(IResponseParser):
    """
    用于解析LLM生成的任务完成检查响应的解析器。
    """

    def parse_response(self, response: str, **kwargs) -> Dict[str, Any]:
        """
        解析LLM的原始字符串响应，并将其转换为任务完成检查结果字典。
        
        Args:
            response (str): LLM的原始字符串响应。
            **kwargs: 额外的参数，目前未使用，但保留以符合接口。

        Returns:
            Dict[str, Any]: 包含任务完成检查结果的字典。
        """
        logger.info(f"🔍 解析LLM响应中的任务完成检查结果 (长度: {len(response)})")
        
        try:
            # 尝试直接解析JSON
            parsed_response = json.loads(response)
            
            # 验证并提取关键字段
            completed = parsed_response.get("completed", False)
            confidence = parsed_response.get("confidence", 0.0)
            reason = parsed_response.get("reason", "No reason provided.")

            # 确保confidence在有效范围内
            if not isinstance(confidence, (int, float)) or not (0.0 <= confidence <= 1.0):
                confidence = 0.0
                logger.warning(f"⚠️ 无效的confidence值: {parsed_response.get('confidence')}, 已重置为0.0")

            logger.info(f"✅ 成功解析任务完成检查结果: completed={completed}, confidence={confidence}")
            return {
                "completed": completed,
                "confidence": confidence,
                "reason": reason
            }
        except json.JSONDecodeError as e:
            logger.warning(f"❌ JSON解析失败: {e}, 返回默认未完成结果")
            return {"completed": False, "confidence": 0.0, "reason": f"JSON parsing error: {e}"}
        except Exception as e:
            logger.error(f"❌ 解析任务完成检查响应过程中出错: {e}, 返回默认未完成结果")
            return {"completed": False, "confidence": 0.0, "reason": f"Error during parsing: {e}"}